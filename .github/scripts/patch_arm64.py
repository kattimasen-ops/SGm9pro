#!/usr/bin/env python3
import os, sys, re

def diagnostic_dump():
    print("========== MAKEFILE DIAGNOSTIC DUMP ==========")
    for fname in ["Makefile", "Makefile.local", "Makefile.smokinguns"]:
        if os.path.exists(fname):
            print(f"\n--- {fname} ---")
            with open(fname, "r", encoding="utf-8", errors="ignore") as f:
                for i, line in enumerate(f):
                    # Dump variable definitions (top 150 lines) and any relevant target paths
                    if i < 150 or 'ui' in line.lower() or 'DIR' in line or 'OBJ' in line:
                        print(f"{i+1:04d}: {line.rstrip()}")
        else:
            print(f"\n--- {fname} (NOT FOUND) ---")
    print("==============================================\n")

def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Apply valid compiler fixes without destroying path variables
    old_lib = 'else ifeq ($(ARCH),s390x) LIB=lib64 endif endif endif endif'
    new_lib = (
        'else ifeq ($(ARCH),s390x) LIB=lib64 '
        'else ifeq ($(ARCH),aarch64) LIB=lib64 endif '
        'endif endif endif endif'
    )
    if old_lib in content:
        content = content.replace(old_lib, new_lib)
        print("[PATCHED] LIB=lib64 fuer aarch64 hinzugefuegt.")

    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: rm -f, python3, Werror flags removed.")

def patch_q_platform():
    path = "code/qcommon/q_platform.h"
    if not os.path.exists(path):
        print(f"[ERROR] {path} not found!")
        sys.exit(1)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    if re.search(r'ARCH_STRING\s+"aarch64"', content):
        return

    pattern = r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)'
    replacement = r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n'
    content, count = re.subn(pattern, replacement, content)
    
    if count == 0:
        aarch64_override = (
            "/* [PATCHED] ARM64 ARCH_STRING Override */\n"
            "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
            "#ifdef ARCH_STRING\n#undef ARCH_STRING\n#endif\n"
            "#define ARCH_STRING \"aarch64\"\n"
            "#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n"
            "#endif\n\n"
        )
        content = aarch64_override + content

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] q_platform.h ARM64 architecture string injected.")

if __name__ == "__main__":
    diagnostic_dump()
    patch_makefile()
    patch_q_platform()
    print("[DONE] Alle Patches angewendet (toxische Overrides entfernt).")
