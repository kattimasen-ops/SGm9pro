#!/usr/bin/env python3
"""
Patch Smokin' Guns for ARM64 (aarch64) cross-compilation.
Run this script from the SmokinGuns root directory.
"""

import os
import sys

def patch_makefile():
    """Add global architecture overrides to the Makefile."""
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r") as f:
        content = f.read()

    # Force CFLAGS, renderer selections, and Q3LCC flags
    patch = """
override CFLAGS += -I/usr/include/SDL -DARCH_STRING=\\"aarch64\\" -DQ3_LITTLE_ENDIAN -D__aarch64__=1
override BUILD_RENDERER_OPENGL1=1
override BUILD_RENDERER_OPENGL2=0
Q3LCC_CFLAGS += -DARCH_STRING=\\"aarch64\\" -DQ3_LITTLE_ENDIAN -D__aarch64__=1
override ARCH_STRING = aarch64
"""

    # Insert at the top (after shebang/comments) – simpler: prepend
    content = patch + content
    with open(makefile, "w") as f:
        f.write(content)

    print("[PATCHED] Makefile")

def patch_q_platform():
    """Patch all q_platform.h files to support aarch64."""
    patched = 0
    for root, dirs, files in os.walk("code"):
        for file in files:
            if file != "q_platform.h":
                continue
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # 1. Ensure __aarch64__ is defined at the top if not present
            if "#ifndef __aarch64__" not in content:
                content = "#ifndef __aarch64__\n#define __aarch64__ 1\n#endif\n" + content

            # 2. Replace the #error "Architecture not supported" block with an aarch64 case
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
                # Fallback: replace just the #error line
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
    # Ensure we are in the SmokinGuns directory (the script expects to be run from there)
    if not os.path.exists("Makefile"):
        print("[ERROR] Must run this script from the SmokinGuns source root.")
        sys.exit(1)

    patch_makefile()
    patch_q_platform()
    print("[DONE] All patches applied successfully.")