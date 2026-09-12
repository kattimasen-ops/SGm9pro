#!/usr/bin/env python3
"""
ARM64 Build-Patch fuer Smokin' Guns (ioquake3-basiert)
"""

import os
import sys
import re


def create_makefile_local():
    """Erstellt Makefile.local. UNVERIFIZIERT: ob die echte Makefile diese
    Datei per -include einliest, konnte nicht bestaetigt werden. Wird trotzdem
    geschrieben (schadet nicht, falls ungenutzt), aber verlasst euch nicht
    darauf - prueft im Build-Log, ob MOUNT_DIR/Q3UIDIR tatsaechlich ankommen."""
    content = """# [PATCHED] ARM64 Build-Konfiguration - siehe Hinweis oben im Skript
MOUNT_DIR := code
Q3UIDIR := $(MOUNT_DIR)/ui
ARCH := aarch64
COMPILE_ARCH := aarch64
"""
    with open("Makefile.local", "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile.local erstellt (Wirkung unverifiziert, siehe Kommentar).")


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # --- Diagnose statt Blindflug: zeigt im Log, ob "s390x"/"lib64" ueberhaupt
    # in der echten Makefile vorkommen, bevor wir versuchen, dort etwas zu
    # patchen. Der alte Ansatz suchte nach einem einzeiligen String mit
    # Leerzeichen statt echten Zeilenumbruechen und konnte so nie treffen.
    print("[DIAGNOSE] Zeilen mit 's390x' in der Makefile:")
    for i, line in enumerate(content.splitlines(), 1):
        if 's390x' in line:
            print(f"  Zeile {i}: {line.strip()}")
    print("[DIAGNOSE] --- Ende ---")
    print("[INFO] Falls oben Zeilen erschienen: prueft von Hand, ob aarch64/LIB=lib64")
    print("[INFO] dort noetig ist. Automatisches Patchen dieser Stelle wurde entfernt,")
    print("[INFO] da der bisherige String-Match nie zuverlaessig funktioniert hat.")

    # --- rm -f (sicher: nur "rm " am Wortanfang, kein doppeltes -f) ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- python3 statt python/python2 ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- Strikte Warn-Flags entfernen ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    # --- REND2-Renderer deaktivieren: NUR ueber die verifizierte Makefile-
    # Variable (bestaetigt im echten Makefile.smokinguns), keine Textzeilen
    # auskommentieren und kein Verzeichnis umbenennen - beides unnoetig und
    # riskant (siehe vorherige "extraneous endif"-Panne durch zu aggressive
    # Regex-Eingriffe in Conditional-Bloecke).
    patch = """
override CFLAGS += -w -fcommon
override BUILD_RENDERER_REND2=0
"""
    content = patch + content

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: BUILD_RENDERER_REND2=0, rm -f, python3, Warn-Flags entfernt.")


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
        aarch64_override = (
            "/* [PATCHED] ARM64 ARCH_STRING Override (Fallback) */\n"
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
    if not os.path.exists("Makefile"):
        print("[ERROR] Makefile not present in current working directory.")
        sys.exit(1)
    create_makefile_local()
    patch_makefile()
    patch_q_platform()
    print("[DONE] Alle Patches erfolgreich angewendet.")
