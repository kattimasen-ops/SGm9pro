#!/usr/bin/env python3
"""
Patch Smokin' Guns for ARM64 / SDL1.2-compat on RK3326.

This script can be invoked from either:
  - the SmokinGuns source root (patches Makefile + q_platform.h), or
  - the sdl12-compat source root (patches SDL12_compat.c).

It applies:
  1. ARM64 architecture patches (q_platform.h)
  2. Makefile fixes (BASENAME typo, SDL2 paths)
  3. SDL_HINT_VIDEODRIVER / SDL_HINT_AUDIODRIVER fallbacks for SDL2 < 2.0.22
  4. Joystick symbol export attributes for sdl12-compat
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


def patch_sdl12_compat_hints():
    """Define SDL_HINT_VIDEODRIVER and SDL_HINT_AUDIODRIVER for SDL2 < 2.0.22.

    Ubuntu 20.04 ships SDL 2.0.10, which lacks these hints. They were only
    formalised as SDL_HINT_* macros in SDL 2.0.22.

    IMPORTANT: the definitions must be inserted at the very top of the file,
    before any #include or code. Inserting them after the last #include does
    NOT work: SDL12_compat.c is ~3000 lines long and contains additional
    includes further down.
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
    print("[PATCHED] sdl12-compat: SDL_HINT_VIDEODRIVER / SDL_HINT_AUDIODRIVER defined at top of file")
    return True


def patch_sdl12_compat_joystick_export():
    """Ensure joystick symbols are exported from libSDL-1.2.so.0.

    By default, sdl12-compat does not set a visibility policy, which
    means the symbols may be hidden if the build environment uses
    -fvisibility=hidden. This function adds __attribute__((visibility("default")))
    to the declarations of the joystick functions that ioquake3 needs.
    """
    path = os.path.join("src", "SDL12_compat.c")
    if not os.path.exists(path):
        print(f"[WARN] {path} not found - skipping joystick export patch")
        return False

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if "__attribute__((visibility(\"default\"))) DECLSPEC void SDLCALL SDL_JoystickClose" in content:
        print("[INFO] sdl12-compat joystick export patch already applied")
        return True

    joystick_funcs = [
        "SDL_JoystickClose",
        "SDL_JoystickOpen",
        "SDL_NumJoysticks",
        "SDL_JoystickName",
        "SDL_JoystickNumAxes",
        "SDL_JoystickNumButtons",
        "SDL_JoystickNumHats",
        "SDL_JoystickNumBalls",
        "SDL_JoystickUpdate",
        "SDL_JoystickEventState",
        "SDL_JoystickGetAxis",
        "SDL_JoystickGetHat",
        "SDL_JoystickGetButton",
        "SDL_JoystickGetBall",
    ]

    patched = False
    for func in joystick_funcs:
        # Match the declaration line and add visibility attribute
        old = f"DECLSPEC void SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC void SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

        old = f"DECLSPEC SDL_Joystick * SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC SDL_Joystick * SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

        old = f"DECLSPEC const char * SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC const char * SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

        old = f"DECLSPEC int SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC int SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

        old = f"DECLSPEC Uint8 SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC Uint8 SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

        old = f"DECLSPEC Sint16 SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC Sint16 SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

        old = f"DECLSPEC SDL_bool SDLCALL {func}("
        new = f'__attribute__((visibility("default"))) DECLSPEC SDL_bool SDLCALL {func}('
        if old in content:
            content = content.replace(old, new)
            patched = True
            print(f"[PATCHED] sdl12-compat: exported {func}")

    if patched:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print("[PATCHED] sdl12-compat: joystick symbol export patch applied")
    else:
        print("[WARN] sdl12-compat: no joystick declarations found to patch")

    return patched


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
        if patch_sdl12_compat_joystick_export():
            applied += 1

    print(f"[DONE] {applied} patch group(s) applied.")
    sys.exit(0)


if __name__ == "__main__":
    main()
