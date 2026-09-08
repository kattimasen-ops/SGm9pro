#!/usr/bin/env python3
"""
Patch Smokin' Guns for ARM64 (aarch64) cross-compilation with the correct build flags.
Run this script from the SmokinGuns source root.
"""

import os
import sys

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r") as f:
        content = f.read()

    # 1. Force -fcommon (fixes GCC 10+ linker errors).
    # 2. Disable renderergl2 (the correct variable is BUILD_RENDERER_REND2).
    # 3. Correct include path for SDL1.2-compat headers.
    patch = """
override CFLAGS += -fcommon -I/usr/include/SDL
override BUILD_RENDERER_REND2=0
"""

    content = patch + content
    with open(makefile, "w") as f:
        f.write(content)

    print("[PATCHED] Makefile (Added -fcommon and correct renderer variable)")

def patch_q_platform():
    patched = 0
    for root, dirs, files in os.walk("code"):
        for file in files:
            if file != "q_platform.h":
                continue
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # Ensure aarch64 is defined.
            if "#ifndef __aarch64__" not in content:
                content = "#ifndef __aarch64__\n#define __aarch64__ 1\n#endif\n" + content

            # Replace the #error block with a proper #elif for aarch64.
            old = '#else\n#error "Architecture not supported"'
            new = (
                '#elif defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n'
                '#ifndef ARCH_STRING\n#define ARCH_STRING "aarch64"\n#endif\n'
                '#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n'
                '#else\n#error "Architecture not supported"'
            )
            if old in content:
                content = content.replace(old, new)
            else:
                content = content.replace(
                    '#error "Architecture not supported"',
                    '#elif defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n'
                    '#ifndef ARCH_STRING\n#define ARCH_STRING "aarch64"\n#endif\n'
                    '#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n'
                    '#else\n#error "Architecture not supported"'
                )

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            patched += 1
            print(f"[PATCHED] {path}")

    if patched == 0:
        print("[WARNING] No q_platform.h files found!")
    else:
        print(f"[INFO] Patched {patched} q_platform.h files")

if __name__ == "__main__":
    if not os.path.exists("Makefile"):
        print("[ERROR] Must run this script from the SmokinGuns source root.")
        sys.exit(1)
    patch_makefile()
    patch_q_platform()
    print("[DONE] All patches applied successfully.")
