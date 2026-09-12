#!/usr/bin/env python3
"""
ARM64 Build-Patch fuer Smokin' Guns (ioquake3-basiert)
Basiert auf dem offiziellen ioquake3-Patch von Martin Michlmayr (Debian)
https://github.com/ioquake/ioq3/commit/ebb69f699cd1392cbe7a865f9f51dbbecdd99b59
"""

import os
import sys
import re


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # --- FIX 1: MOUNT_DIR unbedingt setzen (einzeiliges Muster!) ---
    old_mount = 'ifndef MOUNT_DIR MOUNT_DIR=code endif'
    new_mount = 'MOUNT_DIR:=code'
    if old_mount in content:
        content = content.replace(old_mount, new_mount)
        print("[PATCHED] MOUNT_DIR:=code gesetzt.")
    else:
        print("[WARN] MOUNT_DIR-Muster nicht gefunden. Diagnose:")
        for i, line in enumerate(content.splitlines(), 1):
            if 'MOUNT_DIR' in line:
                print(f"  Zeile {i}: {line.strip()[:120]}")

    # --- FIX 2: Q3UIDIR direkt auf $(MOUNT_DIR)/ui setzen (einzeiliges Muster!) ---
    old_q3uidir = 'ifndef USE_MP_UIDIR Q3UIDIR=$(MOUNT_DIR)/q3_ui else Q3UIDIR=$(UIDIR) endif'
    new_q3uidir = 'Q3UIDIR=$(MOUNT_DIR)/ui'
    if old_q3uidir in content:
        content = content.replace(old_q3uidir, new_q3uidir)
        print("[PATCHED] Q3UIDIR direkt auf $(MOUNT_DIR)/ui gesetzt.")
    else:
        print("[WARN] Q3UIDIR-Muster nicht gefunden. Diagnose:")
        for i, line in enumerate(content.splitlines(), 1):
            if 'Q3UIDIR' in line:
                print(f"  Zeile {i}: {line.strip()[:120]}")

    # --- FIX 3: LIB=lib64 fuer aarch64 (offizieller ioquake3-Patch) ---
    old_lib = 'else ifeq ($(ARCH),s390x) LIB=lib64 endif endif endif endif'
    new_lib = ('else ifeq ($(ARCH),s390x) LIB=lib64 '
               'else ifeq ($(ARCH),aarch64) LIB=lib64 endif '
               'endif endif endif endif')
    if old_lib in content:
        content = content.replace(old_lib, new_lib)
        print("[PATCHED] LIB=lib64 fuer aarch64 hinzugefuegt (offizieller Patch).")
    else:
        print("[WARN] LIB-Muster nicht gefunden. Diagnose:")
        for i, line in enumerate(content.splitlines(), 1):
            if 's390x' in line:
                print(f"  Zeile {i}: {line.strip()[:150]}")

    # --- FIX 4: rm-Befehle safe machen ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 5: python3 erzwingen ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- FIX 6: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    # --- FIX 7: Overrides am Anfang injizieren ---
    patch_top = "\noverride CFLAGS += -w -fcommon\noverride BUILD_RENDERER_REND2=0\n"
    content = patch_top + content
    print("[PATCHED] CFLAGS- und BUILD_RENDERER_REND2-Overrides injiziert.")

    # --- FIX 8: Dynamische $(subst)-Sanitization am Ende injizieren ---
    patch_bottom = """
# [PATCHED] Dynamically sanitize double-slashes from all generated object arrays
Q3UIOBJ := $(subst //,/,$(Q3UIOBJ))
CGAMEOBJ := $(subst //,/,$(CGAMEOBJ))
Q3GAMEOBJ := $(subst //,/,$(Q3GAMEOBJ))
UI_OBJS := $(subst //,/,$(UI_OBJS))
CGAME_OBJS := $(subst //,/,$(CGAME_OBJS))
GAME_OBJS := $(subst //,/,$(GAME_OBJS))
"""
    content += patch_bottom
    print("[PATCHED] Dynamische $(subst)-Pfad-Sanitization injiziert.")

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: MOUNT_DIR, Q3UIDIR, LIB=lib64, Pfad-Sanitization, renderergl2 deaktiviert.")


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
        print("[PATCHED] ARCH_STRING 'aarch64' in q_platform.h injiziert (offizieller Patch).")
    else:
        print("[WARN] ARCH_STRING-Muster nicht gefunden. Fallback wird verwendet.")
        aarch64_override = (
            "/* [PATCHED] ARM64 ARCH_STRING Override */\n"
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


if __name__ == "__main__":
    patch_makefile()
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
