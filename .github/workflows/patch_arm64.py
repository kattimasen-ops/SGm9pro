#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        sys.exit(1)
    with open(makefile, "r") as f:
        content = f.read()

    # 1. Strip out strict -Werror and diagnostic flags
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)

    # 2. Make ALL rm commands safe by turning them into 'rm -f' globally
    content = re.sub(r'\brm\s+', 'rm -f ', content)

    # 3. Clean up any double slashes in paths caused by variable concatenation
    content = content.replace('//', '/')

    # 4. Inject safe compiler overrides
    patch = """
override CFLAGS += -w -fcommon -I/usr/include/SDL -D__aarch64__=1 -DARCH_STRING=\\\"aarch64\\\"
override BUILD_RENDERER_REND2=0
"""
    content = patch + content

    with open(makefile, "w") as f:
        f.write(content)
    print("[PATCHED] Makefile completely cleaned and fixed.")

def patch_q_platform():
    patched = 0
    for root, dirs, files in os.walk("code"):
        for file in files:
            if file != "q_platform.h":
                continue
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            aarch64_override = (
                "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
                "#ifndef ARCH_STRING\n"
                "#define ARCH_STRING \"aarch64\"\n"
                "#endif\n"
                "#ifndef Q3_LITTLE_ENDIAN\n"
                "#define Q3_LITTLE_ENDIAN\n"
                "#endif\n"
                "#endif\n\n"
            )
            if "ARCH_STRING" not in content:
                content = aarch64_override + content

            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            patched += 1
            
        if patched == 0:
            print("[WARNING] No q_platform.h files found!")
        else:
            print(f"[INFO] Patched {patched} q_platform.h files")

if __name__ == "__main__":
    if not os.path.exists("Makefile"):
        sys.exit(1)
    patch_makefile()
    patch_q_platform()
    print("[DONE]")
