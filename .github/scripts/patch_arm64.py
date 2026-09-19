#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

[EXTENDED] Handheld aim assist v4 (GPtk Maus-Emulation):
  - S-Curve + Target Friction on cl.mouseDx/cl.mouseDy (CL_MouseMove)
  - Rotational Aim Magnetism + Fire-Assist on cl.viewangles
    (CL_CreateCmd, after CL_JoystickMove)
  - Line-of-sight check via CM_BoxTrace -> no aim through walls
  - Stronger magnetism, wider cone, extra pull while firing
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
# [EXTENDED] Handheld Aim Assist v4 - staerker + Fire-Assist
# =====================================================================
def patch_aim_assist():
    """Injiziert zwei Hooks plus Zielsuchfunktion mit LOS-Check.

    Verbesserungen gegenueber v3:
      * Staerkerer Grund-Magnetismus (0.24 / 0.15 statt 0.16 / 0.09)
      * Groesserer Kegel (15 Grad statt 12 Grad)
      * Fire-Assist: waehrend BUTTON_ATTACK wird der Sog verdoppelt,
        damit das Crosshair im Moment des Schusses exakt auf dem
        Ziel liegt - ohne Snap, ohne Aimbot.
      * Zielpunkt hoeher (32 Units, naeher an Brustmitte)
      * Laengeres Sticky-Target (10 Frames)
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

    if "CL_HandheldInputCurve" in content:
        print(f"[SKIP] Aim assist already present in {target_file}")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED] Handheld Aim Assist v4
 * ============================================================
 *  Auf einem RK3326-Handheld wird der rechte Stick von GPtk als
 *  Mausbewegung an die Engine gegeben (cl.mouseDx/cl.mouseDy).
 *
 *  Version 4:
 *    - Staerkerer Grund-Magnetismus
 *    - Groesserer Kegel (15 Grad)
 *    - Fire-Assist: extra Sog waehrend BUTTON_ATTACK
 *    - Line-of-Sight-Check via CM_BoxTrace
 *    - Always-on Magnetismus (kein Active-Aim-Gate)
 *
 *  Bewusst KEIN Snap-to-Target: das Crosshair wird sanft gezogen,
 *  auch im Fire-Assist-Fenster.
 * ============================================================ */
#include <math.h>

#ifndef ET_PLAYER
#define ET_PLAYER 1
#endif

#ifndef EF_DEAD
#define EF_DEAD 0x00000001
#endif

/* --- Tuning ------------------------------------------------- */
#define HHA_PI                3.14159265358979323846f
#define HHA_MAX_ANGLE        15.0f    /* aeusserer Magnet-Kegel (Grad)    */
#define HHA_FALLOFF_ANGLE     7.0f    /* voller Magnet bis zu diesem Winkel */
#define HHA_MAGNETISM_YAW     0.24f   /* normaler horizontaler Sog        */
#define HHA_MAGNETISM_PITCH   0.15f   /* normaler vertikaler Sog          */
#define HHA_FIRE_YAW          0.45f   /* Sog waehrend Schuss (horizontal) */
#define HHA_FIRE_PITCH        0.28f   /* Sog waehrend Schuss (vertikal)   */
#define HHA_FRICTION          0.75f   /* Input-Daempfung bei Zielnaehe    */
#define HHA_FRICTION_MAX_MAG 40.0f    /* Friction nur unter diesem Delta  */
#define HHA_CURVE_EXP         1.05f   /* fast linear                      */
#define HHA_CURVE_REF        32.0f
#define HHA_STICKY_FRAMES    10
#define HHA_MAX_DIST         4096.0f
#define HHA_MIN_DIST           48.0f
#define HHA_CHEST_HEIGHT     32.0f    /* hoeher als v3, Richtung Brustmitte */
#define HHA_LOS_LENGTH     32768.0f
/* ------------------------------------------------------------ */

static int hha_lastTargetNum = -1;
static int hha_lastTargetAge = 0;

/* Zwischenspeicher: pro Frame einmal bestimmen, in beiden Hooks nutzen */
static int      hha_cachedTarget   = -1;
static float    hha_cachedAngle    = 999.0f;
static vec3_t   hha_cachedDir      = { 0, 0, 0 };
static qboolean hha_cachedValid    = qfalse;

/* ---- Sichtlinien-Check zwischen Auge und Ziel-Torso -------- */
static qboolean HHA_HasLineOfSight( const vec3_t fromFeet, const vec3_t toFeet ) {
    trace_t tr;
    vec3_t  eye, chest;

    eye[0] = fromFeet[0];
    eye[1] = fromFeet[1];
    eye[2] = fromFeet[2] + cl.snap.ps.viewheight;

    chest[0] = toFeet[0];
    chest[1] = toFeet[1];
    chest[2] = toFeet[2] + HHA_CHEST_HEIGHT;

    CM_BoxTrace( &tr, eye, chest, NULL, NULL, 0, CONTENTS_SOLID );

    return ( tr.fraction >= 0.999f );
}

/* ---- Zielerkennung mit LOS ------------------------------- */
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

        /* Sticky-Bonus: vorheriges Ziel bleibt bevorzugt */
        if ( ent->number == hha_lastTargetNum && angle < HHA_MAX_ANGLE + 5.0f ) {
            angle *= 0.65f;
        }

        if ( angle < bestAngle ) {
            if ( !HHA_HasLineOfSight( cl.snap.ps.origin, ent->pos.trBase ) ) {
                continue;
            }
            bestAngle = angle;
            best      = ent->number;
            VectorCopy( toEnt, bestDir );
        }
    }

    *bestAngleOut = bestAngle;
    return best;
}

/* ---- Ziel pro Frame einmal bestimmen ---------------------- */
static void HHA_UpdateCachedTarget( void ) {
    hha_cachedTarget = HHA_FindTarget( hha_cachedDir, &hha_cachedAngle );
    hha_cachedValid  = qtrue;

    if ( hha_cachedTarget >= 0 ) {
        hha_lastTargetNum = hha_cachedTarget;
        hha_lastTargetAge = 0;
    } else if ( ++hha_lastTargetAge > HHA_STICKY_FRAMES ) {
        hha_lastTargetNum = -1;
    }
}

/* ---- Hook 1: Input-Kurve + Friction ----------------------- */
static void CL_HandheldInputCurve( void ) {
    int   *mx_raw = &cl.mouseDx[cl.mouseIndex];
    int   *my_raw = &cl.mouseDy[cl.mouseIndex];
    float  mag;
    float  friction = 1.0f;

    HHA_UpdateCachedTarget();

    mag = sqrtf( (float)(*mx_raw * *mx_raw) + (float)(*my_raw * *my_raw) );

    if ( hha_cachedTarget >= 0 && mag > 0.0f && mag < HHA_FRICTION_MAX_MAG ) {
        friction = HHA_FRICTION;
    }

    if ( *mx_raw != 0 ) {
        float s = ( *mx_raw < 0 ) ? -1.0f : 1.0f;
        float a = fabsf( (float)*mx_raw );
        float curved = powf( a, HHA_CURVE_EXP ) /
                       powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
        *mx_raw = (int)( s * curved * friction );
    }
    if ( *my_raw != 0 ) {
        float s = ( *my_raw < 0 ) ? -1.0f : 1.0f;
        float a = fabsf( (float)*my_raw );
        float curved = powf( a, HHA_CURVE_EXP ) /
                       powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
        *my_raw = (int)( s * curved * friction );
    }
}

/* ---- Hook 2: Magnetismus + Fire-Assist ------------------- */
static void CL_HandheldAimMagnetism( usercmd_t *cmd ) {
    vec3_t forward, targetAngles;
    float  dot, currentAngle, yawDiff, pitchDiff, strength;
    float  magYaw, magPitch;
    qboolean firing;

    if ( clc.state != CA_ACTIVE )
        return;
    if ( !hha_cachedValid || hha_cachedTarget < 0 )
        return;

    /* Aktueller Winkel zwischen Blick und Ziel */
    AngleVectors( cl.viewangles, forward, NULL, NULL );
    dot = DotProduct( forward, hha_cachedDir );
    if ( dot >  1.0f ) dot =  1.0f;
    if ( dot < -1.0f ) dot = -1.0f;
    currentAngle = acosf( dot ) * ( 180.0f / HHA_PI );

    if ( currentAngle > HHA_MAX_ANGLE )
        return;

    /* Fire-Assist: waehrend Schuss staerkerer Sog */
    firing = ( cmd && ( cmd->buttons & BUTTON_ATTACK ) );
    magYaw   = firing ? HHA_FIRE_YAW   : HHA_MAGNETISM_YAW;
    magPitch = firing ? HHA_FIRE_PITCH : HHA_MAGNETISM_PITCH;

    vectoangles( hha_cachedDir, targetAngles );

    yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
    pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];

    while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
    while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
    while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
    while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

    if ( currentAngle <= HHA_FALLOFF_ANGLE ) {
        strength = 1.0f;
    } else {
        strength = 1.0f - ( currentAngle - HHA_FALLOFF_ANGLE ) /
                          ( HHA_MAX_ANGLE - HHA_FALLOFF_ANGLE );
        if ( strength < 0.0f ) strength = 0.0f;
    }

    cl.viewangles[YAW]   += yawDiff   * magYaw   * strength;
    cl.viewangles[PITCH] += pitchDiff * magPitch * strength;
}
/* ============================================================ */
"""

    mouse_body_pat = re.compile(
        r'(void\s+CL_MouseMove\s*\(\s*usercmd_t\s*\*\s*cmd\s*\)\s*\{)'
    )
    if not mouse_body_pat.search(content):
        print("[WARN] CL_MouseMove not found - skipping aim assist")
        return False

    content = mouse_body_pat.sub(
        lambda m: (helper_code
                   + "\n" + m.group(1)
                   + "\n\tCL_HandheldInputCurve();"),
        content, count=1
    )

    # Magnetismus-Hook wird NACH CL_JoystickMove eingefuegt und erhaelt
    # den cmd-Zeiger, damit der Fire-Assist BUTTON_ATTACK auslesen kann.
    joy_pat = re.compile(
        r'(\n[ \t]*CL_JoystickMove\s*\(\s*&\s*cmd\s*\)\s*;)'
    )
    if not joy_pat.search(content):
        print("[WARN] CL_JoystickMove call not found - skipping magnetism hook")
        return False

    content = joy_pat.sub(
        lambda m: m.group(1) + "\n\n\tCL_HandheldAimMagnetism( &cmd );",
        content, count=1
    )

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist v4 injected into {target_file} "
          f"(LOS + always-on magnetism + fire assist)")
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
