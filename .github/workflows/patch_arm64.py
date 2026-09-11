#!/usr/bin/env python3
"""
ARM64 Build-Patch fuer Smokin' Guns (ioquake3-basiert) - MAXIMUM PERFORMANCE
- Entfernt renderergl2 (nicht ARM64-kompatibel)
- Erzwingt ARCH_STRING "aarch64"
- Macht rm-Befehle safe
- Korrigiert Pfad-Expansion
- Stellt sicher, dass python3 verwendet wird
- Erzwingt -O3 und -fno-plt
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

    # --- FIX 1: renderergl2 komplett deaktivieren ---
    content = re.sub(r'RENDERER_GL2\s*=\s*[^\n]*\n', 'RENDERER_GL2 =\n', content)

    lines = content.splitlines(keepends=True)
    new_lines = []
    for line in lines:
        if 'renderergl2' in line and ('BUILD_' in line or 'TARGET' in line or 'RENDERER' in line):
            new_lines.append('# [PATCHED] Disabled renderergl2: ' + line)
            continue
        new_lines.append(line)
    content = "".join(new_lines)

    content = re.sub(r'^\$\(B\)/renderergl2/[^\n]*\n', '', content, flags=re.MULTILINE)

    # --- FIX 2: Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    # --- FIX 3: rm-Befehle safe machen ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 4: Doppelte Slashes korrigieren ---
    content = content.replace('//ui/', '/ui/')
    content = content.replace('//game/', '/game/')
    content = content.replace('//cgame/', '/cgame/')

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

    # --- FIX 8: -fno-plt hinzufuegen, falls nicht vorhanden ---
    if '-fno-plt' not in content:
        content = re.sub(
            r'(OPTIMIZE\s*=\s*[^\n]*)',
            r'\1 -fno-plt',
            content,
            count=1
        )

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: renderergl2 deaktiviert, rm -f, python3, O3, fno-plt.")


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
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
