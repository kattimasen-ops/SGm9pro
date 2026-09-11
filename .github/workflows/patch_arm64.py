#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)
        
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 1. Strip out strict warning/error flags globally
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)
    
    # 2. Make rm commands safe
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # 3. Disable sdl12-compat tests in inline cmake commands
    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if 'cmake ' in line and 'SDL12TESTS' not in line:
            parts = line.split('#', 1)
            code_part = parts[0].rstrip()
            line = code_part + ' -DSDL12TESTS=OFF' + (' #' + parts[1] if len(parts) > 1 else '\n')
        new_lines.append(line)
    content = "".join(new_lines)

    # 4. Fix double-slash path expansion bugs in Makefile rules (e.g., //ui/ -> /ui/)
    content = content.replace('//ui/', '/ui/').replace('//game/', '/game/').replace('//cgame/', '/cgame/')

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile path expansions and warning flags cleaned.")

def patch_q_platform():
    path = "code/qcommon/q_platform.h"
    if not os.path.exists(path):
        print(f"[ERROR] {path} not found!")
        sys.exit(1)
        
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    if 'ARCH_STRING "aarch64"' in content:
        print("[INFO] q_platform.h already patched.")
        return

    aarch64_override = (
        "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
        "#ifdef ARCH_STRING\n"
        "#undef ARCH_STRING\n"
        "#endif\n"
        "#define ARCH_STRING \"aarch64\"\n"
        "#ifndef Q3_LITTLE_ENDIAN\n"
        "#define Q3_LITTLE_ENDIAN\n"
        "#endif\n"
        "#endif\n\n"
    )
    
    content = aarch64_override + content

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Successfully injected ARCH_STRING override into code/qcommon/q_platform.h.")

if __name__ == "__main__":
    patch_makefile()
    patch_q_platform()
    print("[DONE] All local source patches applied successfully.")
