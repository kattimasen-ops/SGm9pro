#!/usr/bin/env python3
import os, sys, re

def patch_makefile():
    """Patch the Smokin' Guns Makefile to:
    1. Skip renderergl2 entirely (not supported on ARM64/GL4ES)
    2. Fix rm commands to be safe
    3. Fix path expansion bugs
    4. Ensure ARCH_STRING matches ARCH
    """
    makefile = "Makefile"
    if not os.path.exists(makefile):
        print(f"[ERROR] {makefile} not found!")
        sys.exit(1)

    with open(makefile, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # --- FIX 1: Remove renderergl2 from build entirely ---
    # The Makefile includes renderergl2 via a wildcard or explicit list.
    # We need to find and remove those references.

    # Remove renderergl2 from the RENDERER_* variables
    content = re.sub(
        r'RENDERER_GL2\s*=\s*[^\n]*\n',
        'RENDERER_GL2 =\n',
        content
    )

    # Remove any line that adds renderergl2 to the build
    # Pattern: lines containing 'renderergl2' in a build variable
    lines = content.splitlines(keepends=True)
    new_lines = []
    skip_renderergl2 = False
    for line in lines:
        # Skip lines that reference renderergl2 in build contexts
        if 'renderergl2' in line and ('BUILD_' in line or 'TARGET' in line or 'RENDERER' in line):
            # Comment out instead of removing to preserve structure
            new_lines.append('# [PATCHED] Disabled renderergl2: ' + line)
            continue
        new_lines.append(line)
    content = "".join(new_lines)

    # Also remove the renderergl2 build target if it exists
    # Pattern: a target line like "$(B)/renderergl2/..." 
    content = re.sub(
        r'^\$\(B\)/renderergl2/[^\n]*\n',
        '',
        content,
        flags=re.MULTILINE
    )

    # --- FIX 2: Strip strict warning/error flags ---
    content = re.sub(r'-Werror[a-zA-Z0-9=-]*', '', content)
    content = re.sub(r'-Wmaybe-uninitialized', '', content)
    content = re.sub(r'-Wuninitialized', '', content)
    content = re.sub(r'-Wstrict-overflow', '', content)

    # --- FIX 3: Make ALL rm commands safe ---
    content = re.sub(r'\brm\s+(?!-)', 'rm -f ', content)

    # --- FIX 4: Fix double-slash path bugs ---
    content = content.replace('//ui/', '/ui/')
    content = content.replace('//game/', '/game/')
    content = content.replace('//cgame/', '/cgame/')

    # --- FIX 5: Ensure python3 is used ---
    content = content.replace('python ', 'python3 ')
    content = content.replace('python2 ', 'python3 ')

    # --- FIX 6: Force ARCH_STRING consistency by setting it as a make variable ---
    # If the Makefile sets ARCH, ensure ARCH_STRING is also set consistently
    if not re.search(r'ARCH_STRING\s*=', content):
        # Insert ARCH_STRING after ARCH definition
        content = re.sub(
            r'(ARCH\s*=\s*[^\n]*\n)',
            r'\1ARCH_STRING = aarch64\n',
            content,
            count=1
        )

    with open(makefile, "w", encoding="utf-8") as f:
        f.write(content)
    print("[PATCHED] Makefile: renderergl2 disabled, rm -f, python3, path fixes.")

def patch_q_platform():
    """Ensure ARCH_STRING is defined as 'aarch64' for ARM64 builds."""
    path = "code/qcommon/q_platform.h"
    if not os.path.exists(path):
        print(f"[ERROR] {path} not found!")
        sys.exit(1)

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Check if aarch64 ARCH_STRING is already defined
    if re.search(r'ARCH_STRING\s+"aarch64"', content):
        print("[INFO] q_platform.h already has ARCH_STRING aarch64.")
        return

    # Check if __aarch64__ is already handled
    if '__aarch64__' in content and 'ARCH_STRING' in content:
        if re.search(r'__aarch64__.*?ARCH_STRING', content, re.DOTALL):
            print("[INFO] q_platform.h already handles __aarch64__ for ARCH_STRING.")
            return

    # Inject aarch64 override at the top of the file
    aarch64_override = (
        "/* [PATCHED] ARM64 ARCH_STRING override for Smokin' Guns */\n"
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
    print("[PATCHED] Injected ARCH_STRING 'aarch64' override into q_platform.h.")

def patch_sdl_headers():
    """Ensure SDL 1.2 headers are found correctly."""
    # Check if SDL 1.2 headers exist
    sdl_paths = [
        "/usr/include/SDL",
        "/usr/include/SDL12",
        "/usr/local/include/SDL",
    ]
    found = False
    for path in sdl_paths:
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "SDL.h")):
            print(f"[INFO] Found SDL 1.2 headers at {path}")
            found = True
            break
    if not found:
        print("[WARN] SDL 1.2 headers not found in standard locations.")
        print("[WARN] Ensure libsdl1.2-dev is installed in the build container.")

if __name__ == "__main__":
    patch_makefile()
    patch_q_platform()
    patch_sdl_headers()
    print("[DONE] All patches applied successfully.")
