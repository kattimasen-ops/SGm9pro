#!/usr/bin/env python3
"""
Patch Smokin' Guns and sdl12-compat for ARM64 build.

Can be invoked from:
  - the SmokinGuns source root (patches Makefile + q_platform.h)
  - the sdl12-compat source root (patches SDL_HINT_* fallbacks)

The Smokin' Guns game source is NOT patched for SDL2. It stays on the
SDL 1.2 API and is compiled against the real SDL 1.2 headers from
libsdl1.2-dev. At runtime, sdl12-compat (built from source) provides
the SDL 1.2 API on top of SDL2 / KMSDRM via LD_PRELOAD.
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
    """Patch the Smokin' Guns Makefile.

    - Fix the BASENAME -> BASEGAME typo in Q3UIOBJ.
    - Add -I/usr/include/SDL to CFLAGS. The Makefile does not add this
      path on its own for the Linux platform (verified against earlier
      build logs).
    - Remove the upstream rm/python/-Werror hygiene issues.
    """
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[WARN] {makefile} not found - skipping")
        return False

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # ---- Fix upstream typo: BASENAME -> BASEGAME in Q3UIOBJ ----------
    if "$(B)/$(BASENAME)/ui/ui_syscalls.o" in content:
        content = content.replace(
            "$(B)/$(BASENAME)/ui/ui_syscalls.o",
            "$(B)/$(BASEGAME)/ui/ui_syscalls.o",
        )
        print("[PATCHED] Makefile: BASENAME -> BASEGAME in Q3UIOBJ")
    else:
        print("[INFO] Makefile: BASENAME typo not present")

    # ---- Inject the SDL 1.2 include path as a global override --------
    sdl_include_line = "override CFLAGS += -I/usr/include/SDL\n"
    if "override CFLAGS += -I/usr/include/SDL" not in content:
        content = sdl_include_line + content
        print("[PATCHED] Makefile: added -I/usr/include/SDL to global CFLAGS")
    else:
        print("[INFO] Makefile: SDL include override already present")

    # ---- Hygiene -----------------------------------------------------
    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    content = re.sub(r"-Werror[a-zA-Z0-9=-]*", "", content)
    content = re.sub(r"-Wmaybe-uninitialized", "", content)
    content = re.sub(r"-Wuninitialized", "", content)
    content = re.sub(r"-Wstrict-overflow", "", content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: hygiene applied")
    return True


def patch_q_platform():
    """Patch every q_platform.h under code/ so aarch64 is recognised."""
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

            # Preferred: add an #elif right after the ARM32 branch.
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
                # Fallback: prepend a hard override block.
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

    print(f"[INFO] {patched} q_platform.h file(s) patched")
    return patched


def patch_sdl12_compat_hints():
    """Prepend SDL_HINT_* fallbacks to sdl12-compat/src/SDL12_compat.c.

    Ubuntu 20.04 ships SDL 2.0.10, which does not yet define
    SDL_HINT_VIDEODRIVER or SDL_HINT_AUDIODRIVER. These were added as
    formal macros in SDL 2.0.22. The definitions must be inserted at
    the very top of the file so they are visible before the first use
    in SDL_InitSubSystem.
    """
    path = os.path.join("src", "SDL12_compat.c")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found - skipping sdl12-compat hint patch")
        return False

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "#ifndef SDL_HINT_VIDEODRIVER" in content:
        print("[INFO] sdl12-compat hint patch already applied")
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

    if is_sdl12_compat:
        print("==> Patching sdl12-compat")
        if patch_sdl12_compat_hints():
            applied += 1

    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()
