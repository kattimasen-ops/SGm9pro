#!/usr/bin/env python3
"""
ARM64 Build-Patch fuer Smokin' Guns (ioquake3-basiert) - MAXIMUM PERFORMANCE
- Entfernt renderergl2 aus der TARGETS-Variable der Makefile
- Benennt das renderergl2-Verzeichnis um, falls vorhanden
- Erzwingt ARCH_STRING "aarch64"
- Macht rm-Befehle safe
- Korrigiert Pfad-Expansion
- Stellt sicher, dass python3 verwendet wird
- Erzwingt -O3 und -fno-plt
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

    # --- FIX 1: renderergl2 aus der TARGETS-Variable entfernen ---
    # Die Makefile fuegt renderer_opengl2 ueber eine Zeile wie
    # "TARGETS += $(B)/renderer_opengl2_$(SHLIBNAME)" hinzu.
    # Wir suchen nach Zeilen, die "renderer_opengl2" enthalten, und
    # kommentieren sie aus.
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

    # --- FIX 3: Doppelte Slashes korrigieren ---
    content = content.replace('//ui/', '/ui/')
    content = content.replace('//game/', '/game/')
    content = content.replace('//cgame/', '/cgame/')

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

    # --- FIX 7: -fno-plt hinzufuegen, falls nicht vorhanden ---
    if '-fno-plt' not in content:
        content = re.sub(
            r'(OPTIMIZE\s*=\s*[^\n]*)',
            r'\1 -fno-plt',
            content,
            count=1
        )

    # --- FIX 8: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: renderergl2 aus TARGETS entfernt, rm -f, python3, O3, fno-plt.")


def rename_renderergl2_dir():
    """Benennt das renderergl2-Verzeichnis um, falls es existiert, damit der Build es nicht findet."""
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
