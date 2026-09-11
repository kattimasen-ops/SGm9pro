#!/usr/bin/env python3
import os, sys

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        sys.exit(1)
    with open(makefile, "r") as f:
        content = f.read()
    patch = """
override CFLAGS += -fcommon -I/usr/include/SDL -DARCH_STRING=\\"aarch64\\" -D__aarch64__=1 -Wno-error
override BUILD_RENDERER_REND2=0
"""
    content = patch + content
    with open(makefile, "w") as f:
        f.write(content)
    print("[PATCHED] Makefile")

def patch_q_platform():
    patched = 0
    for root, dirs, files in os.walk("code"):
        for file in files:
            if file != "q_platform.h":
                continue
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if "#ifndef __aarch64__" not in content:
                content = "#ifndef __aarch64__\n#define __aarch64__ 1\n#endif\n" + content
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
    if patched == 0:
        print("[WARNING] No q_platform.h files found!")
    else:
        print(f"[INFO] Patched {patched} files")

if __name__ == "__main__":
    if not os.path.exists("Makefile"):
        sys.exit(1)
    patch_makefile()
    patch_q_platform()
    print("[DONE]")
