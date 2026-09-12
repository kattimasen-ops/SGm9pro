#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)
    
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    print("[DIAGNOSE] Zeilen mit 's390x' in der Makefile:")
    for i, line in enumerate(content.splitlines(), 1):
        if 's390x' in line:
            print("  Zeile " + str(i) + ": " + line.strip())
    print("[DIAGNOSE] --- Ende ---")

    # Bug 2 Fix: Sanitize path expansion double-slashes that break Make targets
    content = content.replace('//ui/', '/ui/')
    content = content.replace('//game/', '/game/')
    content = content.replace('//cgame/', '/cgame/')
    content = content.replace('//qagame/', '/qagame/')

    # Standard fixes
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    patch = "\noverride CFLAGS += -w -fcommon\noverride BUILD_RENDERER_REND2=0\n"
    content = patch + content

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: Path expansion bugs fixed, BUILD_RENDERER_REND2=0, rm -f, python3.")

def patch_q_platform():
    path = "code/qcommon/q_platform.h"
    if not os.path.exists(path):
        print(f"[ERROR] {path} not found!")
        sys.exit(1)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    
    if re.search(r'ARCH_STRING\s+"aarch64"', content):
        print("[INFO] q_platform.h bereits gepatcht.")
        return
        
    pattern = r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)'
    replacement = r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n'
    content, count = re.subn(pattern, replacement, content)
    
    if count > 0:
        print("[PATCHED] ARCH_STRING 'aarch64' injiziert (offizieller Patch).")
    else:
        aarch64_override = (
            "/* [PATCHED] ARM64 ARCH_STRING Override (Fallback) */\n"
            "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
            "#ifdef ARCH_STRING\n#undef ARCH_STRING\n#endif\n"
            "#define ARCH_STRING \"aarch64\"\n"
            "#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n"
            "#endif\n\n"
        )
        content = aarch64_override + content
        print("[PATCHED] ARCH_STRING 'aarch64' injiziert (Fallback).")
        
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

if __name__ == "__main__":
    if not os.path.exists("Makefile"):
        print("[ERROR] Makefile not present.")
        sys.exit(1)
    # create_makefile_local() explicitly disabled to fix variable evaluation order
    patch_makefile()
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
