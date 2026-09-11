#!/usr/bin/env python3
"""
ARM64 Build-Patch fuer Smokin' Guns (ioquake3-basiert) - MAXIMUM PERFORMANCE
- Entfernt renderergl2 aus der TARGETS-Variable der Makefile
- Benennt das renderergl2-Verzeichnis um, falls vorhanden
- Erzwingt ARCH_STRING "aarch64"
- Macht rm-Befehle safe
- Bereinigt doppelte Slashes SICHER (ohne gueltige Pfade zu zerstoeren)
- Stellt sicher, dass python3 verwendet wird
- Erzwingt -O3 und -fno-plt
"""

import os
import sys
import re
import shutil


def sanitize_slashes(content):
    """
    Entfernt doppelte Slashes sicher, ohne gueltige Pfade zu zerstoeren.

    Die Makefile verwendet Pfade wie '$(B)/code/ui'. Ein Patch, der
    '//ui/' durch '/ui/' ersetzt, entfernt 'code/' und erzeugt '$(B)//ui'.

    Diese Funktion normalisiert Slash-Sequenzen auf Slash-Ebene, ohne
    Pfadbestandteile zu entfernen. Sie schuetzt URLs (://) und entfernt
    nur redundante Slashes.
    """
    # Schuetze URLs: :// darf nicht zu :/ werden
    content = re.sub(r'(?<=:)//+', '//', content)

    # Entferne mehrfache Slashes, aber nur wenn sie nicht Teil einer URL sind
    # Wir ersetzen '///' oder mehr durch '/', aber nicht '://'
    content = re.sub(r'(?<!:)//+', '/', content)

    return content


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # --- FIX 1: renderergl2 aus der TARGETS-Variable entfernen ---
    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if 'renderer_opengl2' in line or 'renderergl2' in line:
            new_lines.append('# [PATCHED] Disabled renderergl2: ' + line)
            continue
        new_lines.append(line)
    content = "".join(new_lines)

    # --- FIX 2: rm-Befehle safe machen ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 3: python3 erzwingen ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- FIX 4: ARCH_STRING-Konsistenz ---
    if not re.search(r'ARCH_STRING\s*=', content):
        content = re.sub(
            r'(ARCH\s*=\s*[^\n]*\n)',
            r'\1ARCH_STRING = aarch64\n',
            content,
            count=1
        )

    # --- FIX 5: -O2 durch -O3 ersetzen ---
    content = re.sub(r'(?<!\w)-O2(?!\w)', '-O3', content)

    # --- FIX 6: -fno-plt hinzufuegen ---
    if '-fno-plt' not in content:
        content = re.sub(
            r'(OPTIMIZE\s*=\s*[^\n]*)',
            r'\1 -fno-plt',
            content,
            count=1
        )

    # --- FIX 7: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    # --- FIX 8: Doppelte Slashes SICHER bereinigen ---
    content = sanitize_slashes(content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: renderergl2 deaktiviert, rm -f, python3, O3, fno-plt, Slashes bereinigt.")


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

    if '__aarch64__' in content and 'ARCH_STRING' in content:
        if re.search(r'__aarch64__.*?ARCH_STRING', content, re.DOTALL):
            print("[INFO] q_platform.h behandelt __aarch64__ bereits.")
            return

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
    print("[PATCHED] ARCH_STRING 'aarch64' in q_platform.h injiziert.")


if __name__ == "__main__":
    patch_makefile()
    rename_renderergl2_dir()
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
