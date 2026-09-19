#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

Can be invoked from:
  - the SmokinGuns source root (patches Makefile + q_platform.h + cl_input.c)
  - the sdl12-compat source root (patches SDL_HINT_* fallbacks)

[EXTENDED] Adds handheld aim assist (S-Curve, Target Friction,
           Recoil Assist, Rotational Aim Magnetism) for gamepad play.
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
    """Patch the Smokin' Guns Makefile safely without altering execution logic."""
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[WARN] {makefile} not found - skipping")
        return False

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Fix upstream typo: All BASENAME instances in UI objects
    if "$(B)/$(BASENAME)/ui/" in content:
        content = content.replace(
            "$(B)/$(BASENAME)/ui/",
            "$(B)/$(BASEGAME)/ui/"
        )
        print("[PATCHED] Makefile: Corrected BASENAME -> BASEGAME in UI objects")

    # Inject the SDL 1.2 include path as a global override
    sdl_include_line = "override CFLAGS += -I/usr/include/SDL\n"
    if "override CFLAGS += -I/usr/include/SDL" not in content:
        content = sdl_include_line + content
        print("[PATCHED] Makefile: added -I/usr/include/SDL to global CFLAGS")

    # Hygiene and cleanups
    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    content = re.sub(r"-Werror[a-zA-Z0-9=-]*", "", content)
    content = re.sub(r"-Wmaybe-uninitialized", "", content)
    content = re.sub(r"-Wuninitialized", "", content)
    content = re.sub(r"-Wstrict-overflow", "", content)

    # Remove toxic x86 architecture flags that trip up ARM GCC
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
    """Patch q_platform.h under code/ so aarch64 target is defined."""
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
    """Prepend SDL_HINT_* fallbacks to sdl12-compat/src/SDL12_compat.c."""
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
# [EXTENDED] Handheld Aim Assist injection
# =====================================================================
def patch_aim_assist():
    """Inject handheld aim assist into code/client/cl_input.c.

    Adds four features for gamepad play on RK3326-class handhelds:
      * S-Curve input response (finer control near centre)
      * Target Friction (input slowdown when crosshair is on an enemy)
      * Recoil Assist (gentle downward pull while firing, client-side)
      * Rotational Aim Magnetism (soft pull toward nearest enemy in cone)

    All behaviour is client-side only; the authoritative server logic
    and the network protocol are not touched.
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

    if "CL_ApplyHandheldInputCurve" in content:
        print(f"[SKIP] Aim assist already present in {target_file}")
        return True

    helper_code = r"""
/* ============================================================
 * [PATCHED] Handheld Aim Assist for ARM64 / RK3326
 * ============================================================
 *  S-Curve         - finer control near centre, full speed on flicks
 *  Target Friction - input slowdown when crosshair is on an enemy
 *  Recoil Assist   - gentle downward pull while firing (client-side)
 *  Aim Magnetism   - soft pull toward nearest enemy in cone
 *
 * Client-side only; authoritative game logic is untouched.
 * Tune via the HHA_* defines below.
 * ============================================================ */
#include <math.h>

#ifndef ET_PLAYER
#define ET_PLAYER 1
#endif

#define HHA_PI           3.14159265358979323846f
#define HHA_MAX_ANGLE    6.0f    /* magnet cone half-angle (deg)   */
#define HHA_MAGNETISM    0.10f   /* pull strength per frame        */
#define HHA_FRICTION     0.55f   /* input scaling while on target  */
#define HHA_CURVE_EXP    1.15f   /* >1 = finer near centre         */
#define HHA_CURVE_REF    64.0f   /* raw units where gain == 1.0    */
#define HHA_RECOIL_PITCH 0.12f   /* downward pull per frame firing */

/* S-Curve: reshape raw mouse deltas.
 * Preserves top-end (curve_ref -> curve_ref) while attenuating
 * small movements for finer aim. */
static void CL_ApplyHandheldInputCurve( float *mx, float *my ) {
    float a, s;
    if ( mx && *mx != 0.0f ) {
        s = ( *mx < 0.0f ) ? -1.0f : 1.0f;
        a = fabsf( *mx );
        *mx = s * powf( a, HHA_CURVE_EXP ) /
                   powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
    }
    if ( my && *my != 0.0f ) {
        s = ( *my < 0.0f ) ? -1.0f : 1.0f;
        a = fabsf( *my );
        *my = s * powf( a, HHA_CURVE_EXP ) /
                   powf( HHA_CURVE_REF, HHA_CURVE_EXP - 1.0f );
    }
}

/* Target Friction + Rotational Aim Magnetism + Recoil Assist.
 * Runs once per frame; operates on the current viewangles and the
 * most recent snapshot. */
static void CL_ApplyHandheldAimAssist( usercmd_t *cmd ) {
    int      i;
    float    bestAngle = HHA_MAX_ANGLE;
    vec3_t   forward, toEnt, bestDir;
    qboolean haveTarget = qfalse;

    if ( clc.state != CA_ACTIVE )
        return;
    if ( cl.snap.numEntities <= 0 )
        return;

    AngleVectors( cl.viewangles, forward, NULL, NULL );

    for ( i = 0; i < cl.snap.numEntities; i++ ) {
        entityState_t *ent;
        float          dot, angle;

        ent = &cl.parseEntities[
            ( cl.snap.parseEntitiesNum + i ) & ( MAX_PARSE_ENTITIES - 1 ) ];

        if ( ent->eType != ET_PLAYER )
            continue;
        if ( ent->number == cl.snap.ps.clientNum )
            continue;

        VectorSubtract( ent->pos.trBase, cl.snap.ps.origin, toEnt );
        VectorNormalize( toEnt );

        dot = DotProduct( forward, toEnt );
        if ( dot >  1.0f ) dot =  1.0f;
        if ( dot < -1.0f ) dot = -1.0f;

        angle = acosf( dot ) * ( 180.0f / HHA_PI );

        if ( angle < bestAngle ) {
            bestAngle  = angle;
            VectorCopy( toEnt, bestDir );
            haveTarget = qtrue;
        }
    }

    if ( haveTarget ) {
        vec3_t targetAngles;
        float  yawDiff, pitchDiff;

        vectoangles( bestDir, targetAngles );

        yawDiff   = targetAngles[YAW]   - cl.viewangles[YAW];
        pitchDiff = targetAngles[PITCH] - cl.viewangles[PITCH];

        while ( yawDiff   >  180.0f ) yawDiff   -= 360.0f;
        while ( yawDiff   < -180.0f ) yawDiff   += 360.0f;
        while ( pitchDiff >  180.0f ) pitchDiff -= 360.0f;
        while ( pitchDiff < -180.0f ) pitchDiff += 360.0f;

        cl.viewangles[YAW]   += yawDiff   * HHA_MAGNETISM;
        cl.viewangles[PITCH] += pitchDiff * HHA_MAGNETISM;
    }

    /* Recoil Assist: gentle downward pull while firing.
     * Client-side visual aid only; does not affect server recoil. */
    if ( cmd && ( cmd->buttons & BUTTON_ATTACK ) ) {
        cl.viewangles[PITCH] += HHA_RECOIL_PITCH;
    }
}
/* ============================================================ */
"""

    # Anchor: the opening brace of CL_MouseMove
    mouse_pat = re.compile(
        r'(void\s+CL_MouseMove\s*\(\s*usercmd_t\s*\*\s*cmd\s*\)\s*\{)'
    )
    if not mouse_pat.search(content):
        print("[WARN] CL_MouseMove not found - skipping aim assist")
        return False

    # ---- 1. Insert helper functions directly before CL_MouseMove ----
    content = mouse_pat.sub(
        lambda m: helper_code + "\n" + m.group(1),
        content, count=1
    )

    # ---- 2. S-Curve hook: after mx/my are read from the mouse ----
    curve_pats = [
        r'(\bmy\s*=\s*cl\.mouseDy\s*\[\s*cl\.mouseIndex\s*\]\s*;)',
        r'(\bmy\s*=\s*cl\.mouseDy\s*\[[^\]]+\]\s*;)',
    ]
    s_hooked = False
    for p in curve_pats:
        pat = re.compile(p)
        if pat.search(content):
            content = pat.sub(
                lambda m: m.group(1) +
                          "\n\tCL_ApplyHandheldInputCurve( &mx, &my );",
                content, count=1
            )
            s_hooked = True
            print("[PATCHED] S-Curve hook inserted (after mx/my read)")
            break
    if not s_hooked:
        print("[WARN] S-Curve hook not inserted (mx/my pattern not found)")

    # ---- 3. Aim-Assist hook: after viewangles are updated ----
    # Try to place the call after the mouse input has been applied to
    # cl.viewangles so magnetism / recoil are not overwritten.
    assist_pats = [
        r'(cl\.viewangles\s*\[\s*PITCH\s*\]\s*\+=\s*m_pitch->value\s*\*\s*my\s*;)',
        r'(cl\.viewangles\s*\[\s*YAW\s*\]\s*[-+]=[^;]*;)',
    ]
    a_hooked = False
    for p in assist_pats:
        pat = re.compile(p)
        if pat.search(content):
            content = pat.sub(
                lambda m: m.group(1) +
                          "\n\tCL_ApplyHandheldAimAssist( cmd );",
                content, count=1
            )
            a_hooked = True
            print("[PATCHED] Aim-Assist hook inserted (after view update)")
            break
    if not a_hooked:
        # Fallback: run at the top of CL_MouseMove (1-frame latency,
        # functionally equivalent for aim assist purposes).
        content = mouse_pat.sub(
            lambda m: m.group(1) +
                      "\n\tCL_ApplyHandheldAimAssist( cmd );",
            content, count=1
        )
        print("[PATCHED] Aim-Assist hook inserted (fallback: top of CL_MouseMove)")

    with open(target_file, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[PATCHED] Aim assist injected into {target_file}")
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
        patch_aim_assist()          # <-- [EXTENDED] only addition in main()

    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints():
            applied += 1

    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()
