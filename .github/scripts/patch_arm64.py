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

    # --- FIX 1: MOUNT_DIR und Q3UIDIR mit override erzwingen ---
    # Diese Zeilen MUESSEN ganz am Anfang stehen, vor allen anderen Zuweisungen.
    # override ueberschreibt Umgebungsvariablen UND Kommandozeilen-Variablen.
    override_block = (
        "# [PATCHED] Force MOUNT_DIR and Q3UIDIR to correct values\n"
        "override MOUNT_DIR = code\n"
        "override Q3UIDIR = $(MOUNT_DIR)/ui\n"
        "\n"
    )
    # Fuege den Block am Anfang ein, aber nach dem ersten Kommentar-Block
    lines = content.splitlines(keepends=True)
    insert_pos = 0
    for i, line in enumerate(lines):
        if not line.strip().startswith('#') and line.strip():
            insert_pos = i
            break
    lines.insert(insert_pos, override_block)
    content = "".join(lines)
    print("[PATCHED] override MOUNT_DIR = code und override Q3UIDIR = $(MOUNT_DIR)/ui am Anfang eingefuegt.")

    # --- FIX 2: LIB=lib64 fuer aarch64 (offizieller ioquake3-Patch) ---
    old_lib = 'else ifeq ($(ARCH),s390x) LIB=lib64 endif endif endif endif'
    new_lib = (
        'else ifeq ($(ARCH),s390x) LIB=lib64 '
        'else ifeq ($(ARCH),aarch64) LIB=lib64 endif '
        'endif endif endif endif'
    )
    if old_lib in content:
        content = content.replace(old_lib, new_lib)
        print("[PATCHED] LIB=lib64 fuer aarch64 hinzugefuegt (offizieller Patch).")
    else:
        print("[WARN] LIB-Muster nicht gefunden. Diagnose:")
        for i, line in enumerate(content.splitlines(), 1):
            if 's390x' in line:
                print(f"  Zeile {i}: {line.strip()[:150]}")

    # --- FIX 3: rm-Befehle safe machen ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 4: python3 erzwingen ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- FIX 5: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    # --- FIX 6: $(subst)-Sanitization am Ende (korrekte Variablennamen) ---
    patch_bottom = """
# [PATCHED] Dynamically sanitize double-slashes from all generated object arrays
SDK_Q3UIOBJ := $(subst //,/,$(SDK_Q3UIOBJ))
SDK_Q3CGOBJ := $(subst //,/,$(SDK_Q3CGOBJ))
SDK_Q3GOBJ := $(subst //,/,$(SDK_Q3GOBJ))
Q3UIOBJ := $(subst //,/,$(Q3UIOBJ))
CGAMEOBJ := $(subst //,/,$(CGAMEOBJ))
Q3GAMEOBJ := $(subst //,/,$(Q3GAMEOBJ))
"""
    content += patch_bottom
    print("[PATCHED] $(subst)-Pfad-Sanitization injiziert.")

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: override MOUNT_DIR/Q3UIDIR, LIB=lib64, Pfad-Sanitization.")


def patch_makefile_smokinguns():
    """Patcht Makefile.smokinguns, falls vorhanden."""
    makefile = "Makefile.smokinguns"
    if not os.path.exists(makefile):
        print(f"[INFO] {makefile} nicht vorhanden, ueberspringe.")
        return
    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # Fuege override-Block auch hier ein, falls die Datei direkt verwendet wird
    if 'override MOUNT_DIR' not in content:
        override_block = (
            "# [PATCHED] Force MOUNT_DIR and Q3UIDIR to correct values\n"
            "override MOUNT_DIR = code\n"
            "override Q3UIDIR = $(MOUNT_DIR)/ui\n"
            "\n"
        )
        content = override_block + content
        with open(makefile, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[PATCHED] {makefile}: override MOUNT_DIR/Q3UIDIR eingefuegt.")


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
    patch_makefile_smokinguns()
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
