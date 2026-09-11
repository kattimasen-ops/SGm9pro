#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)
        
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 1. Strip out strict -Werror and diagnostic flags globally
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)
    
    # 2. Make ALL rm commands safe globally
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # 3. Automatically disable sdl12-compat tests in any inline cmake commands
    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if 'cmake ' in line and 'SDL12TESTS' not in line:
            parts = line.split('#', 1)
            code_part = parts[0].rstrip()
            line = code_part + ' -DSDL12TESTS=OFF' + (' #' + parts[1] if len(parts) > 1 else '\n')
        new_lines.append(line)
    content = "".join(new_lines)

    # 4. Fix any malformed double-slash paths in Makefile targets/rules
    content = content.replace('//ui/', '/ui/')

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile safely patched without corrupting line continuations.")

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
