#!/usr/bin/env python3
"""
Smokin' Guns ARM64 (RK3326 / Cortex-A35) build patcher.
Fixes ARCH_STRING, injects NEON math, OpenMP SIMD, builds mimalloc,
mirrors game assets, and writes a performance autoexec.cfg.
"""

import os
import re
import subprocess
import urllib.request
import urllib.parse
import html.parser
import shutil


class DirectoryParser(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.files = []
        self.subdirs = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for attr, value in attrs:
                if attr == 'href':
                    if '?' in value or value == '/' or value.startswith('http') or '..' in value:
                        continue
                    if value.endswith('/'):
                        self.subdirs.append(value)
                    elif value.lower().endswith(('.pk3', '.cfg', '.dat', '.txt', '.wad')):
                        self.files.append(value)


def patch_makefile(filepath="Makefile"):
    """
    Patch Makefile to:
      1. Set ARCH ?= aarch64
      2. Enable BUILD_GAME_SO
      3. Disable QVM tools
      4. Fix fmt width issue
      5. Ensure FILE_ARCH is set for aarch64
    """
    if not os.path.exists(filepath):
        print(f"Error: Makefile not found at {filepath}")
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = re.sub(r'ARCH\s*\?=\s*.*', 'ARCH ?= aarch64', content)
    content = re.sub(r'BUILD_GAME_SO\s*\?=\s*.*', 'BUILD_GAME_SO ?= 1', content)
    content = re.sub(r'BUILD_GAME_QVM\s*\?=\s*.*', 'BUILD_GAME_QVM ?= 0', content)

    # Fix fmt width fallback
    if 'FALLBACK_WIDTH' not in content:
        content = re.sub(
            r'(WIDTH\s*:=\s*).*?\n',
            r'\1$(shell tput cols 2>/dev/null || echo 80)\n',
            content, count=1
        )
        content = content.replace(
            'WIDTH := $(shell tput cols 2>/dev/null || echo 80)',
            'WIDTH := $(shell tput cols 2>/dev/null)\n'
            'ifeq ($(WIDTH),)\n'
            '  WIDTH := 80\n'
            'endif'
        )

    # Ensure FILE_ARCH is defined for aarch64
    if 'FILE_ARCH' not in content:
        content = content.replace(
            'ifeq ($(ARCH),aarch64)',
            'ifeq ($(ARCH),aarch64)\n'
            '  FILE_ARCH = aarch64'
        )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[PATCHED] Makefile: ARCH=aarch64, BUILD_GAME_SO=1, BUILD_GAME_QVM=0, fmt fallback added")
    return True


def patch_q_platform(filepath="code/qcommon/q_platform.h"):
    """
    Add AArch64 architecture support to q_platform.h.
    The real fix: ensure ARCH_STRING is defined for __aarch64__ as a fallback,
    while the Makefile also passes -DARCH_STRING.
    """
    if not os.path.exists(filepath):
        print(f"Error: {filepath} not found")
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if '__aarch64__' in content:
        print("[SKIP] q_platform.h already has AArch64 support.")
        return False

    aarch64_block = (
        "#elif defined(__aarch64__) || defined(_M_ARM64)\n"
        "#define ARCH_STRING \"aarch64\"\n"
        "#define CPUSTRING \"aarch64\"\n"
        "#define ID_LITTLE_ENDIAN 1\n"
        "#define id386 0\n"
    )

    pattern = r'(#else\s*\n\s*#error\s+"Architecture not supported")'
    if re.search(pattern, content):
        content = re.sub(pattern, aarch64_block + r'\n\1', content, count=1)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[PATCHED] AArch64 support added to q_platform.h.")
        return True

    error_line = '#error "Architecture not supported"'
    if error_line in content:
        lines = content.splitlines(keepends=True)
        for i, line in enumerate(lines):
            if error_line in line:
                for j in range(i - 1, -1, -1):
                    if lines[j].strip() == '#else':
                        lines.insert(j, aarch64_block + '\n')
                        break
                break
        content = ''.join(lines)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[PATCHED] AArch64 support added to q_platform.h (fallback insertion).")
        return True

    print("[WARN] Could not find insertion point for AArch64 in q_platform.h")
    return False


def inject_neon_math(filepath="code/qcommon/q_math.c"):
    """
    Replace Q_rsqrt with a NEON-accelerated version for AArch64.
    Uses vrsqrteq_f32 + one Newton-Raphson step.
    """
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found")
        return
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if "arm_neon.h" in content:
        print("[SKIP] NEON math already injected.")
        return

    neon_code = (
        "#if defined(__aarch64__)\n"
        "#include <arm_neon.h>\n"
        "/* NEON-accelerated Q_rsqrt for AArch64 Cortex-A35 */\n"
        "float Q_rsqrt(float number) {\n"
        "    float32x4_t v = vdupq_n_f32(number);\n"
        "    float32x4_t vr = vrsqrteq_f32(v);\n"
        "    /* One Newton-Raphson iteration for ~23-bit precision */\n"
        "    vr = vmulq_f32(vr, vrsqrtsq_f32(vmulq_f32(v, vr), vr));\n"
        "    return vgetq_lane_f32(vr, 0);\n"
        "}\n"
        "#else\n"
    )

    new_content, n = re.subn(
        r'(float\s+Q_rsqrt\s*\(\s*float\s+number\s*\)\s*\{)',
        neon_code + r'\1', content, count=1
    )
    if n == 0:
        print("[WARN] Q_rsqrt signature not found - NEON injection skipped.")
        return

    pattern = r'(float\s+Q_rsqrt\s*\(.*?return.*?\n\})'
    match = re.search(pattern, new_content, flags=re.DOTALL)
    if not match:
        print("[WARN] Could not find end of Q_rsqrt - #endif missing.")
        return
    end_pos = match.end()
    new_content = new_content[:end_pos] + "\n#endif\n" + new_content[end_pos:]

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("[PATCHED] NEON-accelerated Q_rsqrt injected into q_math.c.")


def inject_openmp_simd(filepath, target_string, alignment_var="vertices"):
    """
    Inject `#pragma omp simd aligned(...)` before heavy loops.
    """
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found")
        return
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if "#pragma omp simd" in content:
        print(f"[SKIP] OpenMP SIMD already present in {filepath}")
        return

    if target_string not in content:
        print(f"[WARN] Target loop not found in {filepath}: {target_string[:60]}...")
        return

    pragma = f"#pragma omp simd aligned({alignment_var}: 16)\n\t"
    content = content.replace(target_string, pragma + target_string, 1)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[PATCHED] OpenMP SIMD pragma injected into {filepath}.")


def build_and_install_mimalloc(install_prefix="build/release-linux-aarch64"):
    """
    Clone, build, and install mimalloc as a shared library.
    The library is built with the SAME Cortex-A35 flags as the game
    and placed in the output directory so it's packaged in the artifact.
    """
    mimalloc_src = "/tmp/mimalloc-src"
    mimalloc_build = "/tmp/mimalloc-build"

    if os.path.exists(mimalloc_src):
        shutil.rmtree(mimalloc_src)
    if os.path.exists(mimalloc_build):
        shutil.rmtree(mimalloc_build)

    print("[INFO] Cloning mimalloc from GitHub...")
    subprocess.run(
        ["git", "clone", "--depth=1",
         "https://github.com/microsoft/mimalloc.git", mimalloc_src],
        check=True
    )

    os.makedirs(mimalloc_build, exist_ok=True)

    # Use the same optimization flags as the game for consistency.
    mimalloc_cflags = (
        "-O3 -mcpu=cortex-a35 -mtune=cortex-a35 -fomit-frame-pointer "
        "-fno-stack-protector -fno-asynchronous-unwind-tables -fmerge-all-constants "
        "-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon -fno-unroll-loops"
    )

    print("[INFO] Configuring mimalloc with CMake...")
    subprocess.run(
        ["cmake", mimalloc_src,
         "-DCMAKE_BUILD_TYPE=Release",
         "-DMI_BUILD_SHARED=ON",
         "-DMI_BUILD_STATIC=OFF",
         "-DMI_BUILD_OBJECT=OFF",
         f"-DCMAKE_C_FLAGS={mimalloc_cflags}",
         f"-DCMAKE_INSTALL_PREFIX={os.path.abspath(install_prefix)}"],
        cwd=mimalloc_build,
        check=True
    )

    print("[INFO] Building mimalloc...")
    subprocess.run(
        ["make", "-j", str(os.cpu_count() or 2)],
        cwd=mimalloc_build,
        check=True
    )

    print("[INFO] Installing mimalloc to build output...")
    subprocess.run(
        ["make", "install"],
        cwd=mimalloc_build,
        check=True
    )

    # Also copy directly into the mod folder for convenience
    mod_dir = os.path.join(install_prefix, "smokinguns")
    os.makedirs(mod_dir, exist_ok=True)
    for lib in ["libmimalloc.so", "libmimalloc.so.3"]:
        src_lib = os.path.join(install_prefix, "lib", lib)
        if os.path.exists(src_lib):
            shutil.copy2(src_lib, os.path.join(mod_dir, lib))
            print(f"[INFO] Copied {lib} to {mod_dir}")

    print("[PATCHED] mimalloc built and installed.")


def write_autoexec(output_mod_dir):
    """Write an autoexec.cfg with maximum performance cvars."""
    os.makedirs(output_mod_dir, exist_ok=True)
    autoexec_path = os.path.join(output_mod_dir, "autoexec.cfg")
    if os.path.exists(autoexec_path):
        return
    cvars = [
        'seta s_musicvolume "0"',
        'seta cg_boostfps "1"',
        'seta cg_gunsmoke "0"',
        'seta cg_glowflares "0"',
        'seta r_picmip "5"',
        'seta r_vertexLight "1"',
        'seta r_dynamiclight "0"',
        'seta r_fastsky "1"',
        'seta com_maxfps "60"',
        'seta com_busyWait "0"',
    ]
    with open(autoexec_path, 'w') as f:
        f.write("// Auto-generated by patch_arm64.py\n")
        f.write("\n".join(cvars) + "\n")
    print(f"[INFO] autoexec.cfg written to {autoexec_path}")


def fix_git_safe_directory():
    """Prevent 'dubious ownership' git errors inside Docker."""
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "/work"],
        check=False, capture_output=True
    )


def crawl_and_download_mirror(base_url, target_base_dir, current_subpath="", max_depth=10):
    """Recursively crawl and download the Smokin' Guns asset mirror."""
    if max_depth <= 0:
        return
    active_url = urllib.parse.urljoin(base_url, current_subpath)
    try:
        req = urllib.request.Request(active_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as response:
            html_content = response.read().decode('utf-8', errors='ignore')

        parser = DirectoryParser()
        parser.feed(html_content)

        local_dir = os.path.join(target_base_dir, current_subpath)
        os.makedirs(local_dir, exist_ok=True)

        for filename in sorted(set(parser.files)):
            file_url = urllib.parse.urljoin(active_url, filename)
            dest_path = os.path.join(local_dir, filename)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                continue
            try:
                urllib.request.urlretrieve(file_url, dest_path)
                print(f"  Downloaded: {filename}")
            except Exception as dl_err:
                print(f"  [WARN] Failed to download {file_url}: {dl_err}")

        for subdir in sorted(set(parser.subdirs)):
            clean_subdir = subdir.lstrip('/')
            next_subpath = os.path.join(current_subpath, clean_subdir)
            crawl_and_download_mirror(
                base_url, target_base_dir, next_subpath, max_depth - 1
            )
    except Exception as e:
        print(f"[ERROR] Crawling {active_url}: {e}")


def main():
    print("=" * 60)
    print(" Smokin' Guns ARM64 (RK3326 / Cortex-A35) Build Patcher")
    print("=" * 60)

    fix_git_safe_directory()

    # --- Source patches --------------------------------------------------
    patch_makefile('Makefile')
    patch_q_platform('code/qcommon/q_platform.h')

    # NEON math micro-optimisation
    inject_neon_math('code/qcommon/q_math.c')

    # OpenMP SIMD pragmas on heavy renderer / game loops
    inject_openmp_simd(
        'code/renderer/tr_mesh.c',
        'for ( i = 0 ; i < numVerts ; i++ )',
        alignment_var='vertices'
    )
    inject_openmp_simd(
        'code/game/bg_pmove.c',
        'for ( i = 0 ; i < pml.numtouch ; i++ )',
        alignment_var='pml.touchents'
    )

    # --- Build mimalloc --------------------------------------------------
    build_and_install_mimalloc()

    # --- Compilation -----------------------------------------------------
    cpu_count = os.cpu_count() or 2
    cc = os.environ.get("CC", "gcc")

    # Cortex-A35 optimization flags.
    # -fno-unroll-loops: avoids I-cache thrashing on in-order A35.
    # -fno-semantic-interposition: lets compiler inline across .so boundaries.
    optimize_flags = (
        "-O3 "
        "-mcpu=cortex-a35 "
        "-mtune=cortex-a35 "
        "-pipe "
        "-fomit-frame-pointer "
        "-ffast-math "
        "-ftree-vectorize "
        "-fno-math-errno "
        "-fno-trapping-math "
        "-fno-semantic-interposition "
        "-fno-stack-protector "
        "-fno-asynchronous-unwind-tables "
        "-fmerge-all-constants "
        "-falign-functions=16 "
        "-falign-loops=16 "
        "-DNDEBUG "
        "-w "
        "-fcommon "
        "-fopenmp-simd "
        "-flax-vector-conversions "
        "-mno-outline-atomics "
        "-fno-unroll-loops"
    )

    compile_cmd = (
        f"make -j{cpu_count} "
        f"ARCH=aarch64 "
        f"BUILD_GAME_SO=1 "
        f"BUILD_GAME_QVM=0 "
        f'CC="{cc}" '
        f'OPTIMIZE="{optimize_flags}" '
        f'LDFLAGS="-Wl,-O1 -Wl,--as-needed -Wl,--strip-all"'
    )

    print(f"\n[INFO] Compiling with CC={cc}, {cpu_count} parallel jobs")
    print(f"[INFO] OPTIMIZE flags: {optimize_flags}\n")
    subprocess.run(compile_cmd, shell=True, check=True)

    # --- Mirror game assets -----------------------------------------------
    mirror_root = "http://download.smokin-guns.org/mirror.9k.lv/smokinguns/smokinguns/"
    output_mod_dir = "build/release-linux-aarch64/smokinguns"
    print(f"\n[INFO] Mirroring game assets from {mirror_root}")
    print(f"[INFO] Target directory: {output_mod_dir}\n")
    crawl_and_download_mirror(mirror_root, output_mod_dir)

    # --- Write autoexec.cfg -----------------------------------------------
    write_autoexec(output_mod_dir)

    print("\n" + "=" * 60)
    print(" Build complete!")
    print("=" * 60)


if __name__ == '__main__':
    main()
