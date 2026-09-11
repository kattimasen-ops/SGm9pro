#!/usr/bin/env python3
import os

def patch_q_platform():
    path = "code/qcommon/q_platform.h"
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return False
    
    with open(path, "r") as f:
        content = f.read()
    
    if "ARCH_STRING \"aarch64\"" in content:
        print("q_platform.h already patched.")
        return True

    patch_code = """
#if defined(__aarch64__) || defined(__arm64__) || defined(aarch64)
#ifdef ARCH_STRING
#undef ARCH_STRING
#endif
#define ARCH_STRING "aarch64"
#ifndef Q3_LITTLE_ENDIAN
#define Q3_LITTLE_ENDIAN
#endif
#endif
"""
    with open(path, "w") as f:
        f.write(patch_code + "\n" + content)
    print("Successfully patched code/qcommon/q_platform.h for ARM64.")
    return True

def patch_makefile():
    path = "Makefile"
    if not os.path.exists(path):
        print(f"Error: {path} not found.")
        return False
    
    with open(path, "r") as f:
        content = f.read()
    
    # Fix Makefile path expansion bugs resulting in double slashes
    updated = content.replace("//ui/", "/ui/").replace("//game/", "/game/").replace("//cgame/", "/cgame/")
    if updated != content:
        with open(path, "w") as f:
            f.write(updated)
        print("Successfully patched Makefile path double-slashes.")
    else:
        print("Makefile path patterns already clean.")
    return True

if __name__ == "__main__":
    patch_q_platform()
    patch_makefile()
