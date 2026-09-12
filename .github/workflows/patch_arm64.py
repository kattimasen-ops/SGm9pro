#!/usr/bin/env python3
"""
ARM64 Build-Patch fuer Smokin' Guns (ioquake3-basiert)
Basiert auf dem offiziellen ioquake3-Patch von Martin Michlmayr (Debian)
https://github.com/ioquake/ioq3/commit/ebb69f699cd1392cbe7a865f9f51dbbecdd99b59
"""

import os
import sys
import re
import shutil


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # --- FIX 0: MOUNT_DIR unbedingt auf code setzen ---
    # Die Makefile definiert MOUNT_DIR nur, wenn es NICHT definiert ist.
    # In der Docker-Umgebung ist MOUNT_DIR als leere Umgebungsvariable vorhanden,
    # wodurch ifndef fehlschlaegt und MOUNT_DIR leer bleibt.
    # Wir ersetzen 'MOUNT_DIR=code' durch 'MOUNT_DIR:=code' (sofortige Zuweisung).
    content = content.replace('MOUNT_DIR=code', 'MOUNT_DIR:=code')
    print("[PATCHED] MOUNT_DIR:=code gesetzt (sofortige Zuweisung).")

    # --- FIX 1: Q3UIDIR explizit auf $(MOUNT_DIR)/ui setzen ---
    # Die Makefile definiert Q3UIDIR ueber eine ifndef/else-Verzweigung.
    # Wir umgehen diese Verzweigung, um //ui-Pfade zu vermeiden.
    old_q3uidir = 'ifndef USE_MP_UIDIR Q3UIDIR=$(MOUNT_DIR)/q3_ui else Q3UIDIR=$(UIDIR) endif'
    if old_q3uidir in content:
        content = content.replace(old_q3uidir, 'Q3UIDIR=$(MOUNT_DIR)/ui')
        print("[PATCHED] Q3UIDIR explizit auf $(MOUNT_DIR)/ui gesetzt.")
    else:
        print("[INFO] Q3UIDIR-Verzweigung nicht gefunden, keine Aenderung noetig.")

    # --- FIX 2: LIB=lib64 fuer ARCH=aarch64 (offizieller ioquake3-Patch) ---
    # Die Makefile hat den LIB-Block in einer einzigen Zeile:
    # else ifeq ($(ARCH),s390x) LIB=lib64 endif endif endif endif
    # Der offizielle Patch fuegt else ifeq ($(ARCH),aarch64) LIB=lib64
    # direkt nach dem s390x-Block ein und ein weiteres endif am Ende.
    if 'ARCH,aarch64' not in content:
        old_lib = 'else ifeq ($(ARCH),s390x) LIB=lib64 endif endif endif endif'
        new_lib = ('else ifeq ($(ARCH),s390x) LIB=lib64 '
                   'else ifeq ($(ARCH),aarch64) LIB=lib64 endif '
                   'endif endif endif endif')
        if old_lib in content:
            content = content.replace(old_lib, new_lib)
            print("[PATCHED] LIB=lib64 fuer aarch64 hinzugefuegt (offizieller Patch).")
        else:
            print("[WARN] LIB=lib64 fuer aarch64 konnte nicht eingefuegt werden.")
    else:
        print("[INFO] LIB=lib64 fuer aarch64 bereits vorhanden.")

    # --- FIX 3: renderergl2 aus der TARGETS-Variable entfernen ---
    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if 'renderer_opengl2' in line or 'renderergl2' in line:
            new_lines.append('# [PATCHED] Disabled renderergl2: ' + line)
            continue
        new_lines.append(line)
    content = "".join(new_lines)

    # --- FIX 4: rm-Befehle safe machen ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 5: python3 erzwingen ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- FIX 6: ARCH_STRING-Konsistenz ---
    if not re.search(r'ARCH_STRING\s*=', content):
        content = re.sub(
            r'(ARCH\s*=\s*[^\n]*\n)',
            r'\1ARCH_STRING = aarch64\n',
            content,
            count=1
        )

    # --- FIX 7: -O2 durch -O3 ersetzen ---
    content = re.sub(r'(?<!\w)-O2(?!\w)', '-O3', content)

    # --- FIX 8: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: MOUNT_DIR, Q3UIDIR, LIB=lib64, renderergl2 deaktiviert.")


def rename_renderergl2_dir():
    """Benennt das renderergl2-Verzeichnis um, falls es existiert."""
    renderergl2_dir = "code/renderergl2"
    if os.path.isdir(renderergl2_dir):
        backup_dir = "code/renderergl2.disabled"
        if os.path.isdir(backup_dir):
            shutil.rmtree(backup_dir)
        os.rename(renderergl2_dir, backup_dir)
        print(f"[PATCHED] {renderergl2_dir} -> {backup_dir} umbenannt.")
    else:
        print(f"[INFO] {renderergl2_dir} existiert nicht, kein Umbenennen noetig.")


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

    # Offizieller ioquake3-Patch: Fuege aarch64 zur ARCH_STRING-Kette hinzu.
    pattern = r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)'
    replacement = r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n'
    content, count = re.subn(pattern, replacement, content)
    if count > 0:
        print("[PATCHED] ARCH_STRING 'aarch64' in q_platform.h injiziert (offizieller Patch).")
    else:
        # Fallback: Fuege den Override-Block am Anfang ein
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
        print("[PATCHED] ARCH_STRING 'aarch64' in q_platform.h injiziert (Fallback).")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    patch_makefile()
    rename_renderergl2_dir()
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
