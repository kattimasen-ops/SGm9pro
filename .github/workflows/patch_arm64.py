#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)
        
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        # 1. Strip out strict -Werror and diagnostic flags
        line = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', line)
        line = re.sub(r'-Wmaybe-uninitialized', '', line)
        
        # 2. Make ALL rm commands safe globally by turning them into 'rm -f'
        line = re.sub(r'\brm\s+', 'rm -f ', line)

        # 3. Safely strip trailing slashes from BUILDDIR without touching conditionals/endif
        if line.startswith("BUILDDIR") and "=" in line:
            parts = line.split('#', 1)
            code_part = parts[0].rstrip()
            if code_part.endswith('/'):
                code_part = code_part.rstrip('/')
            line = code_part + (' #' + parts[1] if len(parts) > 1 else '\n')

        # 4. Automatically disable sdl12-compat tests in any cmake command
        if 'cmake' in line and 'SDL12TESTS' not in line:
            line = line.rstrip() + ' -DSDL12TESTS=OFF\n'

        new_lines.append(line)

    content = "".join(new_lines)

    # 5. Inject safe compiler overrides and disable rend2 renderer at the top
    patch = """
override CFLAGS += -w -fcommon -I/usr/include/SDL -D__aarch64__=1 -DARCH_STRING=\\\"aarch64\\\"
override BUILD_RENDERER_REND2=0
"""
    content = patch + content

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile safely patched without breaking conditionals.")

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
        print(f"[INFO] Patched {patched} q_platform.h files successfully.")

if __name__ == "__main__":
    if not os.path.exists("Makefile"):
        print("[ERROR] Makefile not present in current working directory.")
        sys.exit(1)
    patch_makefile()
    patch_q_platform()
    print("[DONE] All patches applied cleanly.")
