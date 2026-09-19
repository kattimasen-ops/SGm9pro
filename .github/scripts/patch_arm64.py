#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build (RK3326 / Cortex-A35).

Can be invoked from:
  - the SmokinGuns source root (patches Makefile + q_platform.h + cl_input.c + SDL headers)
  - the sdl12-compat source root (patches SDL_HINT_* fallbacks)
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

    # Inject SDL2 & SDL include paths as global overrides
    sdl_include_line = "override CFLAGS += -I/usr/include/SDL2 -I/usr/include/SDL\n"
    if "override CFLAGS += -I/usr/include/SDL2" not in content:
        content = sdl_include_line + content
        print("[PATCHED] Makefile: added -I/usr/include/SDL2 to global CFLAGS")

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


def patch_sdl_headers():
    """Ensure SDL2 header includes resolve correctly."""
    if not os.path.isdir("code"):
        return 0
    patched = 0
    for root, _dirs, files in os.walk("code"):
        for name in files:
            if name.endswith(".h") or name.endswith(".c"):
                path = os.path.join(root, name)
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                if '#  include "SDL.h"' in content or '#include "SDL.h"' in content:
                    content = content.replace('#  include "SDL.h"', '#include <SDL2/SDL.h>')
                    content = content.replace('#include "SDL.h"', '#include <SDL2/SDL.h>')
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                    patched += 1
                    print(f"[PATCHED] SDL header path in {path}")
    return patched


def patch_aim_assist():
    """Inject Target Friction, S-Curve, and Recoil Assist safely using delta pointers into CL_MouseMove in code/client/cl_input.c."""
    target_file = None
    for root, _dirs, files in os.walk("code"):
        if "cl_input.c" in files:
            target_file = os.path.join(root, "cl_input.c")
            break

    if not target_file or not os.path.exists(target_file):
        print("[WARN] cl_input.c not found - skipping Aim Assist patch")
        return False

    with open(target_file, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "CL_ApplyHandheldAimAssist" in content:
        print("[INFO] Aim Assist is already patched in cl_input.c")
        return True

    c_patch = """
/* [PATCHED] Handheld Aim Assist & Input Curve for ARM64 */
#include <math.h>

static void CL_ApplyHandheldAimAssist(int *mx, int *my, usercmd_t *cmd) {
    int i;
    entityState_t *ent;
    vec3_t dir, forward;
    float dot, angleDelta;
    float frictionFactor = 0.5f;
    float maxAngle = 4.0f;
    qboolean targetFound = qfalse;

    // Schutz: Nur im laufenden Spiel ausfuehren (nicht im Menue/Ladebildschirm)
    if (clc.state != CA_ACTIVE) {
        return;
    }

    // 1. S-Kurve fuer Analogstick-Praezision (p = 1.8)
    if (mx && *mx != 0) {
        float signX = (*mx < 0) ? -1.0f : 1.0f;
        *mx = (int)(signX * powf(fabsf((float)*mx), 1.8f) * 0.1f);
    }
    if (my && *my != 0) {
        float signY = (*my < 0) ? -1.0f : 1.0f;
        *my = (int)(signY * powf(fabsf((float)*my), 1.8f) * 0.065f);
    }

    // 2. Target Friction (Verlangsamung bei Zielkontakt)
    AngleVectors(cl.viewangles, forward, NULL, NULL);

    for (i = 0; i < cl.snap.numEntities; i++) {
        ent = &cl.parseEntities[(cl.snap.parseEntitiesNum + i) & (MAX_PARSE_ENTITIES - 1)];
        if (ent->eType != ET_PLAYER || ent->number == cl.snap.ps.clientNum) {
            continue;
        }

        VectorSubtract(ent->pos.trBase, cl.snap.ps.origin, dir);
        VectorNormalize(dir);

        dot = DotProduct(forward, dir);
        if (dot > 1.0f) dot = 1.0f;
        if (dot < -1.0f) dot = -1.0f;

        angleDelta = acosf(dot) * (180.0f / 3.14159265358979323846f);

        if (angleDelta < maxAngle) {
            targetFound = qtrue;
            break;
        }
    }

    if (targetFound) {
        if (mx) *mx = (int)(*mx * frictionFactor);
        if (my) *my = (int)(*my * frictionFactor);
    }

    // 3. Rueckstoss-Daempfung bei Dauerfeuer
    if (cmd && (cmd->buttons & BUTTON_ATTACK)) {
        cl.viewangles[PITCH] += 0.35f;
    }
}
"""

    if "void CL_MouseMove(" in content:
        content = content.replace("void CL_MouseMove(", c_patch + "\nvoid CL_MouseMove(")

        if "cl.mouseDy[cl.executeIndex] = 0;" in content:
            content = content.replace(
                "cl.mouseDy[cl.executeIndex] = 0;",
                "cl.mouseDy[cl.executeIndex] = 0;\n    CL_ApplyHandheldAimAssist(&mx, &my, cmd);"
            )
        elif "CL_GetMouseDelta" in content:
            content = re.sub(
                r"(CL_GetMouseDelta\s*\([^;]+\);)",
                r"\1\n    CL_ApplyHandheldAimAssist(&mx, &my, cmd);",
                content
            )
        else:
            content = re.sub(
                r"(void\s+CL_MouseMove\s*\(\s*usercmd_t\s*\*cmd\s*\)\s*\{)",
                r"\1\n    CL_ApplyHandheldAimAssist(&mx, &my, cmd);",
                content
            )

        with open(target_file, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[PATCHED] {target_file}: Aim Assist safely injected into CL_MouseMove")
        return True
    else:
        print("[WARN] Could not find 'CL_MouseMove' in cl_input.c")
        return False


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
        patch_sdl_headers()
        if patch_aim_assist():
            applied += 1

    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints():
            applied += 1

    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()
