#!/usr/bin/env python3
"""
Patch Smokin' Guns for ARM64 (aarch64) cross-compilation.
Run from the SmokinGuns source root.
"""

import os
import re
import sys


def diagnostic_dump():
    """Print the top of each Makefile and any line mentioning ui/DIR/OBJ.

    Useful for future debugging if the BASENAME typo reappears in a different
    form after an upstream sync.
    """
    print("========== MAKEFILE DIAGNOSTIC DUMP ==========")
    for fname in ["Makefile", "Makefile.local", "Makefile.smokinguns"]:
        if not os.path.exists(fname):
            print(f"\n--- {fname} (NOT FOUND) ---")
            continue
        print(f"\n--- {fname} ---")
        with open(fname, "r", encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i < 150 or "ui" in line.lower() or "DIR" in line or "OBJ" in line:
                    print(f"{i+1:04d}: {line.rstrip()}")
    print("==============================================\n")


def patch_makefile():
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # ------------------------------------------------------------------
    # CRITICAL: the upstream Makefile uses $(BASENAME) instead of
    # $(BASEGAME) in the SDK-UI object list.  BASENAME is never defined,
    # so the path becomes "build/release-linux-aarch64//ui/ui_syscalls.o"
    # and make aborts with:
    #     No rule to make target '.../release-linux-aarch64//ui/ui_syscalls.o'
    #
    # Evidence: Makefile line 2531, seen in the build log:
    #     Q3UIOBJ = $(Q3UIOBJ_) $(B)/$(BASENAME)/ui/ui_syscalls.o
    # The neighbouring GAME and CGAME lines use $(BASEGAME) correctly.
    # ------------------------------------------------------------------
    before = content
    content = content.replace(
        "$(B)/$(BASENAME)/ui/ui_syscalls.o",
        "$(B)/$(BASEGAME)/ui/ui_syscalls.o",
    )
    if content != before:
        print("[PATCHED] Makefile: $(BASENAME) -> $(BASEGAME) in Q3UIOBJ")
    else:
        print("[INFO] Makefile: BASENAME typo not present (already patched?)")

    # ------------------------------------------------------------------
    # Generic hygiene (unchanged from previous working version)
    # ------------------------------------------------------------------
    content = re.sub(r"\brm\s+(?!-)", "rm -f ", content)
    content = content.replace("python ", "python3 ")
    content = content.replace("python2 ", "python3 ")
    content = re.sub(r"-Werror[a-zA-Z0-9=-]*", "", content)
    content = re.sub(r"-Wmaybe-uninitialized", "", content)
    content = re.sub(r"-Wuninitialized", "", content)
    content = re.sub(r"-Wstrict-overflow", "", content)

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: hygiene (rm -f, python3, -Werror removed)")


def patch_q_platform():
    """Walk code/ and patch every q_platform.h we find.

    The tree contains exactly one authoritative copy at code/qcommon/, but
    we walk the whole tree so a future upstream reorganisation does not
    silently break the ARM64 build.
    """
    patched = 0
    for root, _dirs, files in os.walk("code"):
        for name in files:
            if name != "q_platform.h":
                continue
            path = os.path.join(root, name)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if re.search(r'ARCH_STRING\s+"aarch64"', content):
                # Already patched in this copy — skip.
                continue

            changed = False

            # Preferred form: add an #elif right after the ARM32 branch,
            # matching the existing style of the file.
            pattern = re.compile(
                r'(#elif defined __arm__\s*\n#define ARCH_STRING "arm"\s*\n)'
            )
            new_content, n = pattern.subn(
                r'\1#elif defined __aarch64__\n#define ARCH_STRING "aarch64"\n',
                content,
            )
            if n > 0:
                content = new_content
                changed = True
            else:
                # Fallback: prepend a hard override block.
                override = (
                    "/* [PATCHED] ARM64 ARCH_STRING override */\n"
                    "#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)\n"
                    "#ifdef ARCH_STRING\n#undef ARCH_STRING\n#endif\n"
                    "#define ARCH_STRING \"aarch64\"\n"
                    "#ifndef Q3_LITTLE_ENDIAN\n#define Q3_LITTLE_ENDIAN\n#endif\n"
                    "#endif\n\n"
                )
                content = override + content
                changed = True

            if changed:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                patched += 1
                print(f"[PATCHED] {path}")

    if patched == 0:
        print("[INFO] q_platform.h already patched (no change)")
    else:
        print(f"[INFO] {patched} q_platform.h file(s) patched")


if __name__ == "__main__":
    if not os.path.exists("Makefile"):
        print("[ERROR] Must be run from the SmokinGuns source root.")
        sys.exit(1)

    diagnostic_dump()
    patch_makefile()
    patch_q_platform()
    print("[DONE] All patches applied.")
