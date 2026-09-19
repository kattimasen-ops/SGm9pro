#!/usr/bin/env python3
import os
import re

def patch_makefile(filepath="Makefile"):
    if not os.path.exists(filepath):
        print(f"Fehler: {filepath} wurde im aktuellen Verzeichnis nicht gefunden.")
        return False

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 1. USE_SDL2 strikt auf 0 setzen
    if re.search(r"^\s*USE_SDL2\s*[:?]?=", content, flags=re.MULTILINE):
        content = re.sub(r"^\s*USE_SDL2\s*[:?]?=.*$", "USE_SDL2 := 0", content, flags=re.MULTILINE)
    else:
        content = "USE_SDL2 := 0\n" + content

    # 2. Entferne harte -I/usr/include/SDL2 Referenzen aus allen Flags
    content = content.replace("-I/usr/include/SDL2", "")

    # 3. Falls sdl2-config verwendet wird, auf sdl-config (SDL 1.2) umschalten
    content = content.replace("sdl2-config", "sdl-config")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print("SUCCESS: Makefile wurde erfolgreich für SDL 1.2 gepatcht (USE_SDL2 := 0 erzwungen).")
    return True

if __name__ == "__main__":
    patch_makefile()
