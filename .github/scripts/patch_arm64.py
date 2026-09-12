#!/usr/bin/env python3
"""
Patch Smokin' Guns for ARM64 (aarch64) cross-compilation,
and patch sdl12-compat for older SDL2 headers.

Can be invoked from either:
  - the SmokinGuns source root (patches Makefile + q_platform.h), or
  - the sdl12-compat source root (patches SDL12_compat.c).
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

    before = content
    content = content.replace(
        "$(B)/$(BASENAME)/ui/ui_syscalls.o",
        "$(B)/$(BASEGAME)/ui/ui_syscalls.o",
    )
    if content != before:
        print("[PATCHED] Makefile: $(BASENAME) -> $(BASEGAME) in Q3UIOBJ")
    else:
        print("[INFO] Makefile: BASENAME typo not present")

    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    content = re.sub(r"-Werror[a-zA-Z0-9=-]*", "", content)
    content = re.sub(r"-Wmaybe-uninitialized", "", content)
    content = re.sub(r"-Wuninitialized", "", content)
    content = re.sub(r"-Wstrict-overflow", "", content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: hygiene")
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

    print(f"[INFO] {patched} q_platform.h file(s) patched")
    return patched


def patch_sdl12_compat():
    """Define SDL_HINT_VIDEODRIVER and SDL_HINT_AUDIODRIVER for SDL2 < 2.0.22.
    Ubuntu 20.04 ships SDL 2.0.10, which lacks these hints.
    """
    path = os.path.join("src", "SDL12_compat.c")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found - skipping sdl12-compat patch")
        return False

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "#ifndef SDL_HINT_VIDEODRIVER" in content:
        print("[INFO] sdl12-compat already patched")
        return True

    includes = list(re.finditer(r'^#include\s+.*$', content, re.MULTILINE))
    if not includes:
        print("[WARN] no #include found in SDL12_compat.c")
        return False

    insert_pos = includes[-1].end()
    patch = (
        "\n\n"
        "/* [PATCHED] Define SDL_HINT_VIDEODRIVER and SDL_HINT_AUDIODRIVER\n"
        " * for SDL2 versions older than 2.0.22 where these hints were not\n"
        " * yet formalised.  They were introduced as full hints in SDL 2.0.22.\n"
        " */\n"
        "#ifndef SDL_HINT_VIDEODRIVER\n"
        "#define SDL_HINT_VIDEODRIVER \"SDL_VIDEODRIVER\"\n"
        "#endif\n"
        "#ifndef SDL_HINT_AUDIODRIVER\n"
        "#define SDL_HINT_AUDIODRIVER \"SDL_AUDIODRIVER\"\n"
        "#endif\n"
    )
    content = content[:insert_pos] + patch + content[insert_pos:]

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] sdl12-compat: SDL_HINT_VIDEODRIVER / SDL_HINT_AUDIODRIVER defined")
    return True


if __name__ == "__main__":
    # Detect which source tree we're in and act accordingly.  Do not fail
    # just because the other tree's files aren't present.
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
        if patch_sdl12_compat():
            applied += 1

    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)
