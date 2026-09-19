#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

[EXTENDED] Handheld aim assist: S-Curve, Target Friction, Sticky Target,
           Rotational Aim Magnetism. Injected as a SINGLE call at the top
           of CL_MouseMove so the upstream if/else flow is never broken.
"""

import os
import re
import sys


def diagnostic_dump():
    print("========== MAKEFILE DIAGNOSTIC DUMP ==========")
    for fname in ["Makefile", "Makefile.local", "Makefile.smokinguns"]:
        if not os.path.exists(fname):
            print(f"\n--- {fname} (NOT FOUND) ---")
            continue
        print(f"\n--- {fname} ---")
        with open(fname, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i < 150 or "ui" in line.lower() or "DIR" in line or "OBJ" in line:
                    print(f"{i+1:04d}: {line.rstrip()}")
    print("==============================================\n")


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[WARN] {makefile} not found - skipping")
        return False

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "$(B)/$(BASENAME)/ui/" in content:
        content = content.replace(
            "$(B)/$(BASENAME)/ui/",
            "$(B)/$(BASEGAME)/ui/"
        )
        print("[PATCHED] Makefile: Corrected BASENAME -> BASEGAME in UI objects")

    sdl_include_line = "override CFLAGS += -I/usr/include/SDL\n"
    if "override CFLAGS += -I/usr/include/SDL" not in content:
        content = sdl_include_line + content
        print("[PATCHED] Makefile: added -I/usr/include/SDL to global CFLAGS")

    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    content = re.sub(r"-Werror[a-zA-Z0-9=-]*", "", content)
    content = re.sub(r"-Wmaybe-uninitialized", "", content)
    content = re.sub(r"-Wuninitialized", "", content)
    content = re.sub(r"-Wstrict-overflow", "", content)

    toxic_flags = [
        "-m32", "-m64",
        "-march=native", "march=native",
        "-msse", "-msse2", "-msse3", "-mfpmath=sse"
    ]
    for flag in toxic_flags:
        content = content.replace(flag, "")
    print("[PATCHED] Makefile: toxic x86 architecture flags removed")

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def patch_q_platform():
    patched = 0
    if not os.path.isdir("code"):
        print("[WARN] code/ not found - skipping q_platform.h patches")
        return 0

    for root, _dirs, files in os.walk("code"):
        for name in files:
            if name != "q_platform.h":
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if re.search(r'ARCH_STRING\s+"aarch64"', content):
                continue

            changed = False
            pattern = re.compile(
                r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)'
            )
            new_content, n = pattern.subn(
                r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n',
                content,
            )
            if n > 0:
                content = new_content
                changed = True
            else:
                override = (
                    "/* [PATCHED] ARM64 ARCH_STRING override */\n"
                    "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
                    "#ifdef ARCH_STRING\n#undef ARCH_STRING\n#endif\n"
                    "#define ARCH_STRING \"aarch64\"\n"
                    "#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n"
                    "#endif\n\n"
                )
                content = override + content
                changed = True

            if changed:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                patched += 1
                print(f"[PATCHED] {path}")

    return patched


def patch_sdl12_compat_hints():
    path = os.path.join("src", "SDL12_compat.c")
    if not os.path.exists(path):
        return False

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "#ifndef SDL_HINT_VIDEODRIVER" in content:
        return True

    patch = (
        "/* [PATCHED] Define SDL_HINT_VIDEODRIVER and SDL_HINT_AUDIODRIVER\n"
        " * for SDL2 versions older than 2.0.22 where these hints were not\n"
        " * yet formalised as macros.\n"
        " */\n"
        "#ifndef SDL_HINT_VIDEODRIVER\n"
        "#define SDL_HINT_VIDEODRIVER \"SDL_VIDEODRIVER\"\n"
        "#endif\n"
        "#ifndef SDL_HINT_AUDIODRIVER\n"
        "#define SDL_HINT_AUDIODRIVER \"SDL_AUDIODRIVER\"\n"
        "#endif\n"
        "\n"
    )

    content = patch + content

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] sdl12-compat: SDL_HINT_* fallbacks inserted at top of file")
    return True


# =====================================================================
# [EXTENDED] Handheld Aim Assist - single safe injection, no aimbot
# =====================================================================
def patch_aim_assist():
    """Inject handheld aim assist into code/client/cl_input.c.

    Features (all client-side, no server-side or protocol impact):
      * S-Curve            - finer control near centre on the analog stick
      * Target Friction    - slows down small stick movements when on target
      * Sticky Target      - holds the same target for ~200 ms to prevent
                             jitter when two enemies are close together
      * Aim Magnetism      - soft pull toward nearest enemy inside an 8-deg
                             cone, ramped down toward the cone edge
      * Active-Aim Gate    - magnetism only runs while the player is actively
                             moving the stick, so the crosshair never drifts
                             on its own (this is what separates this from
                             an aimbot)

    Not implemented on purpose:
      * Snap-to-target, prediction, auto-fire, wall-piercing check.
    """
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cl_input.c" in files:
            target_file = os.path.join(root, "cl_input.c")
            break

    if not target_file or not os.path.exists(target_file):
        print("[WARN] cl_input.c not found - skipping aim assist patch")
        return False

    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "CL_ApplyHandheldAimAssist" in content:
        print(f"[SKIP] Aim assist already present in {target_file}")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED] Handheld Aim Assist for ARM64 / RK3326
 * ============================================================
 *  S-Curve          - finer control near centre, full speed on flicks
 *  Target Friction  - slows small stick movements when on target
 *  Sticky Target    - keeps last target for a few frames
 *  Aim Magnetism    - soft pull toward nearest enemy in cone
 *  Active-Aim Gate  - magnet only runs while the player is aiming
 *
 * Called once per frame from the top of CL_MouseMove. Client-side only.
 * Tune via the HHA_* defines below.
 *
 * Recoil Assist intentionally omitted: in the Quake 3 engine positive
 * PITCH pitches the view DOWN, so adding pitch while firing pulls the
 * crosshair down and makes aiming harder, not easier.
 * ============================================================ */
#include <math.h>

#ifndef ET_PLAYER
#define ET_PLAYER 1
#endif

#ifndef EF_DEAD
#define EF_DEAD 0x00000001
#endif

/* --- Tuning knobs ------------------------------------------- */
#define HHA_PI               3.14159265358979323846f
#define HHA_MAX_ANGLE        8.0f    /* outer cone half-angle (deg)      */
#define HHA_FALLOFF_ANGLE    3.0f    /* full magnet strength inside this */
#define HHA_MAGNETISM_YAW    0.14f   /* horizontal pull per frame        */
#define HHA_MAGNETISM_PITCH  0.08f   /* vertical pull per frame          */
#define HHA_FRICTION         0.65f   /* input scale when on target       */
#define HHA_FRICTION_MAX_MAG 40.0f   /* friction only for inputs below   */
#define HHA_CURVE_EXP        1.20f   /* >1 = finer near centre           */
#define HHA_CURVE_REF        64.0f   /* raw units where gain == 1.0      */
#define HHA_STICKY_FRAMES    12      /* ~200 ms at 60 fps                */
#define HHA_AIM_ACTIVE_FRAMES 8      /* magnet stays alive this long     */
#define HHA_AIM_THRESHOLD    3.0f    /* raw units to count as "aiming"   */
#define HHA_MAX_DIST         4096.0f /* skip enemies beyond this         */
#define HHA_MIN_DIST         48.0f   /* skip enemies inside melee range  */
/* ------------------------------------------------------------ */

/* Persistent per-session state */
static int hha_lastTargetNum    = -1;
static int hha_lastTargetAge    = 0;
static int hha_recentAimFrames  = 0;

/* Find the best enemy inside the cone. Returns clientNum or -1.
 * Also returns the unit vector toward that enemy and its angle. */
static int HHA_FindTarget( vec3_t bestDir, float *bestAngleOut ) {
    int    i, best = -1;
    float  bestAngle = HHA_MAX_ANGLE;
    vec3_t forward, toEnt;

    *bestAngleOut = 999.0f;

    if ( clc.state != CA_ACTIVE )
        return -1;
    if ( cl.snap.numEntities <= 0 )
        return -1;

    AngleVectors( cl.viewangles, forward, NULL, NULL );

    for ( i = 0; i < cl.snap.numEntities; i++ ) {
        entityState_t *ent = &cl.parseEntities[
            ( cl.snap.parseEntitiesNum + i ) & ( MAX_PARSE_ENTITIES - 1 ) ];
        float dx, dy, dz, distSq, dot, angle;

        if ( ent->eType != ET_PLAYER )
            continue;
        if ( ent->number == cl.snap.ps.clientNum )
            continue;
        if ( ent->eFlags & EF_DEAD )
            continue;

        dx = ent->pos.trBase[0] - cl.snap.ps.origin[0];
        dy = ent->pos.trBase[1] - cl.snap.ps.origin[1];
        dz = ent->pos.trBase[2] - cl.snap.ps.origin[2];
        distSq = dx*dx + dy*dy + dz*dz;

        if ( distSq < HHA_MIN_DIST * HHA_MIN_DIST ) continue;
        if ( distSq > HHA_MAX_DIST * HHA_MAX_DIST ) continue;

        toEnt[0] = dx; toEnt[1] = dy; toEnt[2] = dz;
        VectorNormalize( toEnt );

        dot = DotProduct( forward, toEnt );
        if ( dot >  1.0f ) dot =  1.0f;
        if ( dot < -1.0f ) dot = -1.0f;
        angle = acosf( dot ) * ( 180.0f / HHA_PI );

        /* Sticky bonus: previously targeted enemy gets a slightly wider
         * effective cone, preventing flip-flop when two enemies are close. */
        if ( ent->number == hha_lastTargetNum && angle < HHA_MAX_ANGLE + 3.0f ) {
            angle *= 0.75f;
        }

        if ( angle < bestAngle ) {
            bestAngle = angle;
            best      = ent->number;
            VectorCopy( toEnt, bestDir );
        }
    }

    *bestAngleOut = bestAngle;
    return best;
}

static void CL_ApplyHandheldAimAssist( usercmd_t *cmd ) {
    vec3_t bestDir;
    float  bestAngle;
    int    target;
    int   *mx_raw;
    int   *my_raw;
    float  rawMag = 0.0f;
    float  friction = 1.0f;

    (void)cmd;

    if ( clc.state != CA_ACTIVE )
        return;

    /* --- 1. Find target BEFORE touching input ----------------- */
    target = HHA_FindTarget( bestDir, &bestAngle );

    /* --- 2. Read raw deltas (still unmodified by us) ---------- */
    mx_raw = &cl.mouseDx[cl.mouseIndex];
    my_raw = &cl.mouseDy[cl.mouseIndex];

    rawMag = sqrtf( (float)(*mx_raw * *mx_raw) +
                    (float)(*my_raw * *my_raw) );

    /* Track "player is aiming" so magnet only fires on active input. */
    if ( rawMag >= HHA_AIM_THRESHOLD ) {
        hha_recentAimFrames = HHA_AIM_ACTIVE_FRAMES;
    } else if ( hha_recentAimFrames > 0 ) {
        hha_recentAimFrames--;
    }

    /* --- 3. Target Friction: only for fine adjustments -------- */
    if ( target >= 0 && rawMag > 0.0f && rawMag < HHA_FRICTION_MAX_MAG ) {
        friction = HHA_FRICTION;
    }

    /* --- 4. S-Curve + friction on raw deltas ------------------ */
    if ( *mx_raw != 0 ) {
        float s = ( *mx_raw < 0 ) ? -1.0f : 1.0f;
        float a = fabsf( (float)*mx_raw );
        float curved = s * powf( a, HHA_CURVE_EXP ) /
                           powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
        *mx_raw = (int)( curved * friction );
    }
    if ( *my_raw != 0 ) {
        float s = ( *my_raw < 0 ) ? -1.0f : 1.0f;
        float a = fabsf( (float)*my_raw );
        float curved = s * powf( a, HHA_CURVE_EXP ) /
                           powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
        *my_raw = (int)( curved * friction );
    }

    /* --- 5. Update sticky target bookkeeping ------------------ */
    if ( target >= 0 ) {
        hha_lastTargetNum = target;
        hha_lastTargetAge = 0;
    } else if ( ++hha_lastTargetAge > HHA_STICKY_FRAMES ) {
        hha_lastTargetNum = -1;
    }

    /* --- 6. Magnetism: only while player is actively aiming --- */
    if ( target >= 0 && hha_recentAimFrames > 0 ) {
        vec3_t targetAngles;
        float  yawDiff, pitchDiff, strength;

        vectoangles( bestDir, targetAngles );

        yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
        pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];

        while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
        while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
        while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
        while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

        /* Ramp: full strength inside falloff, tapering to zero at edge. */
        if ( bestAngle <= HHA_FALLOFF_ANGLE ) {
            strength = 1.0f;
        } else {
            strength = 1.0f - ( bestAngle - HHA_FALLOFF_ANGLE ) /
                              ( HHA_MAX_ANGLE - HHA_FALLOFF_ANGLE );
            if ( strength < 0.0f ) strength = 0.0f;
        }

        cl.viewangles[YAW]   += yawDiff   * HHA_MAGNETISM_YAW   * strength;
        cl.viewangles[PITCH] += pitchDiff * HHA_MAGNETISM_PITCH * strength;
    }
}
/* ============================================================ */
"""

    pattern = re.compile(
        r'(void\s+CL_MouseMove\s*\(\s*usercmd_t\s*\*\s*cmd\s*\)\s*\{)'
    )
    if not pattern.search(content):
        print("[WARN] CL_MouseMove signature not found - skipping aim assist")
        return False

    content = pattern.sub(
        lambda m: helper_code
                  + "\n" + m.group(1)
                  + "\n\tCL_ApplyHandheldAimAssist( cmd );",
        content, count=1
    )

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist injected into {target_file} (single safe hook)")
    return True
# =====================================================================


def main():
    is_smokinguns = os.path.exists("Makefile")
    is_sdl12_compat = os.path.exists(os.path.join("src", "SDL12_compat.c"))

    if not is_smokinguns and not is_sdl12_compat:
        print("[ERROR] Not in SmokinGuns or sdl12-compat source tree.")
        sys.exit(1)

    applied = 0

    if is_smokinguns:
        print("==> Patching SmokinGuns")
        diagnostic_dump()
        if patch_makefile():
            applied += 1
        patch_q_platform()
        patch_aim_assist()

    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints():
            applied += 1

    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()
