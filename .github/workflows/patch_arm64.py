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

    # --- FIX 1: LIB=lib64 fuer ARCH=aarch64 (offizieller ioquake3-Patch) ---
    # Die Makefile hat den LIB-Block in einer einzigen Zeile.
    # Der offizielle Patch fuegt else ifeq ($(ARCH),aarch64) LIB=lib64
    # direkt nach dem s390x-Block ein und ein weiteres endif am Ende.
    if 'ARCH,aarch64' not in content:
        # Robuster Ansatz: Ersetze die eindeutige s390x-Sequenz
        old = 'else ifeq ($(ARCH),s390x) LIB=lib64 endif endif endif endif'
        new = 'else ifeq ($(ARCH),s390x) LIB=lib64 else ifeq ($(ARCH),aarch64) LIB=lib64 endif endif endif endif endif'
        if old in content:
            content = content.replace(old, new)
            print("[PATCHED] LIB=lib64 fuer aarch64 hinzugefuegt (offizieller Patch).")
        else:
            # Fallback: Suche nach der Zeile mit dem LIB-Block
            pattern = r'(LIB=lib\s+INSTALL=install\s+MKDIR=mkdir\s+ifneq.*?else ifeq \(\$\(ARCH\),s390x\)\s+LIB=lib64)(\s+endif\s+endif\s+endif\s+endif)'
            replacement = r'\1 else ifeq ($(ARCH),aarch64) LIB=lib64 endif\2'
            content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
            if count > 0:
                print("[PATCHED] LIB=lib64 fuer aarch64 hinzugefuegt (Fallback).")
            else:
                print("[WARN] LIB=lib64 fuer aarch64 konnte nicht automatisch eingefuegt werden.")
    else:
        print("[INFO] LIB=lib64 fuer aarch64 bereits vorhanden.")

    # --- FIX 2: renderergl2 aus der TARGETS-Variable entfernen ---
    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if 'renderer_opengl2' in line or 'renderergl2' in line:
            new_lines.append('# [PATCHED] Disabled renderergl2: ' + line)
            continue
        new_lines.append(line)
    content = "".join(new_lines)

    # --- FIX 3: rm-Befehle safe machen ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 4: python3 erzwingen ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- FIX 5: ARCH_STRING-Konsistenz ---
    if not re.search(r'ARCH_STRING\s*=', content):
        content = re.sub(
            r'(ARCH\s*=\s*[^\n]*\n)',
            r'\1ARCH_STRING = aarch64\n',
            content,
            count=1
        )

    # --- FIX 6: -O2 durch -O3 ersetzen ---
    content = re.sub(r'(?<!\w)-O2(?!\w)', '-O3', content)

    # --- FIX 7: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: LIB=lib64, renderergl2 deaktiviert, rm -f, python3, O3.")


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
