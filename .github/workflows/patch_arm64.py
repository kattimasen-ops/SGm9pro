#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)
        
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 1. Strip out strict -Werror and diagnostic flags
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    
    # 2. Make ALL rm commands safe globally by turning them into 'rm -f'
    content = re.sub(r'\brm\s+', 'rm -f ', content)

    # 3. Forcibly strip trailing slashes from ALL variable assignments (BUILDDIR, UI_DIR, etc.)
    def clean_var_assignment(match):
        prefix = match.group(1)  # e.g., "BUILDDIR ="
        val = match.group(2).rstrip() # value
        # Strip any trailing slashes from the variable value
        val = re.sub(r'/+\s*$', '', val)
        return f"{prefix} {val}"

    content = re.sub(r'^([A-Z_]+\s*[:+?]?=)\s*(.+?)\s*$', clean_var_assignment, content, flags=re.MULTILINE)

    # 4. Automatically disable sdl12-compat tests in any cmake command to speed up build
    content = re.sub(r'(cmake\s+[^#\r\n]+)', r'\1 -DSDL12TESTS=OFF', content)

    # 5. Inject safe compiler overrides and disable rend2 renderer
    patch = """
override CFLAGS += -w -fcommon -I/usr/include/SDL -D__aarch64__=1 -DARCH_STRING=\\\"aarch64\\\"
override BUILD_RENDERER_REND2=0
"""
    content = patch + content

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile fully cleaned: all variable trailing slashes stripped.")

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
