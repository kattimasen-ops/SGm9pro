#!/usr/bin/env python3
"""
Smokin' Guns ARM64 (RK3326 / Cortex-A35) build patcher.
Fixes ARCH_STRING, injects NEON math, OpenMP SIMD, builds mimalloc,
mirrors .pk3 game assets, and writes a performance autoexec.cfg.
"""

import os
import re
import glob
import subprocess
import urllib.request
import urllib.parse
import html.parser
import shutil


# ===========================================================================
# Directory listing parser (only .pk3 files)
# ===========================================================================

class DirectoryParser(html.parser.HTMLParser):
    EXCLUDED_FILES = {"sg_pak0.pk3"}

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
                    elif value.lower().endswith('.pk3'):
                        if value not in self.EXCLUDED_FILES:
                            self.files.append(value)


# ===========================================================================
# Makefile patch
# ===========================================================================

def patch_makefile(filepath="Makefile"):
    """Patch Makefile: ARCH, BUILD_GAME_SO, BUILD_GAME_QVM, fmt fallback, ARCH_STRING."""
    if not os.path.exists(filepath):
        print(f"Error: Makefile not found at {filepath}")
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    content = re.sub(r'ARCH\s*\?=\s*.*', 'ARCH ?= aarch64', content)
    content = re.sub(r'BUILD_GAME_SO\s*\?=\s*.*', 'BUILD_GAME_SO ?= 1', content)
    content = re.sub(r'BUILD_GAME_QVM\s*\?=\s*.*', 'BUILD_GAME_QVM ?= 0', content)

    # Fix fmt width fallback (tput returns nothing in Docker)
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

    # Force ARCH_STRING to be passed via CFLAGS (ioquake3 recommended way)
    if 'ARCH_STRING' not in content:
        content = re.sub(
            r'(CFLAGS\s*\+?=\s*)',
            r'\1-DARCH_STRING=\\"$(ARCH)\\" ',
            content, count=1
        )

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print("[PATCHED] Makefile: ARCH=aarch64, BUILD_GAME_SO=1, BUILD_GAME_QVM=0, ARCH_STRING, fmt fallback")
    return True


# ===========================================================================
# q_platform.h patch (robust fallback)
# ===========================================================================

def patch_q_platform(filepath="code/qcommon/q_platform.h"):
    """
    Add AArch64 fallback defines to q_platform.h.
    The Makefile passes -DARCH_STRING=\"aarch64\", this is only a safety net.
    """
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found")
        return False
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if '__aarch64__' in content:
        print("[SKIP] q_platform.h already has AArch64 support.")
        return False

    aarch64_fallback = (
        "\n"
        "/* ---- AArch64 (ARM64) fallback support ---- */\n"
        "#if defined(__aarch64__) && !defined(ARCH_STRING)\n"
        "#define ARCH_STRING \"aarch64\"\n"
        "#endif\n"
        "#if defined(__aarch64__) && !defined(CPUSTRING)\n"
        "#define CPUSTRING \"aarch64\"\n"
        "#endif\n"
        "#if defined(__aarch64__) && !defined(ID_LITTLE_ENDIAN)\n"
        "#define ID_LITTLE_ENDIAN 1\n"
        "#endif\n"
        "#if defined(__aarch64__) && !defined(id386)\n"
        "#define id386 0\n"
        "#endif\n"
        "/* ---- end AArch64 fallback ---- */\n"
    )

    match = re.search(r'(#define\s+\w+\s*\n)', content)
    if match:
        insert_pos = match.end()
        content = content[:insert_pos] + aarch64_fallback + content[insert_pos:]
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        print("[PATCHED] AArch64 fallback block added to q_platform.h.")
        return True

    print("[WARN] Could not find insertion point in q_platform.h")
    return False


# ===========================================================================
# NEON math injection
# ===========================================================================

def inject_neon_math(filepath="code/qcommon/q_math.c"):
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
        "float Q_rsqrt(float number) {\n"
        "    float32x4_t v = vdupq_n_f32(number);\n"
        "    float32x4_t vr = vrsqrteq_f32(v);\n"
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


# ===========================================================================
# SIMD loop injection (robust, pattern-based)
# ===========================================================================

def inject_simd_by_pattern(filepath, pattern, alignment_var, description):
    """Inject a SIMD pragma before the first match of a regex pattern."""
    if not os.path.exists(filepath):
        print(f"[SKIP] {filepath} not found")
        return
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()

    if "#pragma omp simd" in content:
        print(f"[SKIP] OpenMP SIMD already present in {filepath}")
        return

    match = re.search(pattern, content)
    if not match:
        print(f"[WARN] Pattern not found in {filepath} ({description}) - skipping.")
        return

    insert_pos = match.start()
    pragma = f"#pragma omp simd aligned({alignment_var}: 16)\n\t"
    content = content[:insert_pos] + pragma + content[insert_pos:]

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[PATCHED] SIMD pragma injected into {filepath} ({description}).")


def find_and_patch_simd_loops():
    """
    Locate the hot loops in tr_mesh.c and bg_pmove.c and inject SIMD pragmas.
    Uses glob-based discovery + flexible regex to survive code variations.
    """
    # ---- tr_mesh.c : vertex transformation loop ----
    tr_mesh_candidates = glob.glob("code/**/tr_mesh.c", recursive=True)
    if tr_mesh_candidates:
        tr_mesh = tr_mesh_candidates[0]
        inject_simd_by_pattern(
            tr_mesh,
            pattern=r'(for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*numVerts\s*;)',
            alignment_var='vertices',
            description="tr_mesh.c vertex loop"
        )
    else:
        print("[WARN] tr_mesh.c not found anywhere under code/")

    # ---- bg_pmove.c : touch-entity loop ----
    bg_pmove_candidates = glob.glob("code/**/bg_pmove.c", recursive=True)
    if bg_pmove_candidates:
        bg_pmove = bg_pmove_candidates[0]
        inject_simd_by_pattern(
            bg_pmove,
            pattern=r'(for\s*\(\s*i\s*=\s*0\s*;\s*i\s*<\s*pm->numtouch\s*;)',
            alignment_var='pm->touchents',
            description="bg_pmove.c touch loop"
        )
    else:
        print("[WARN] bg_pmove.c not found anywhere under code/")


# ===========================================================================
# mimalloc
# ===========================================================================

def install_newer_cmake():
    """Install a recent CMake via pip (Ubuntu 20.04 ships 3.16, mimalloc needs >= 3.18)."""
    print("[INFO] Upgrading CMake via pip (requires >= 3.18 for mimalloc)...")
    subprocess.run(["python3", "-m", "pip", "install", "--upgrade", "pip"], check=True)
    subprocess.run(["python3", "-m", "pip", "install", "cmake>=3.18"], check=True)
    result = subprocess.run(["cmake", "--version"], capture_output=True, text=True, check=True)
    version_line = result.stdout.strip().splitlines()[0]
    print(f"[INFO] CMake version now: {version_line}")
    match = re.search(r'(\d+)\.(\d+)\.(\d+)', version_line)
    if not match:
        raise RuntimeError(f"Could not parse CMake version from: {version_line}")
    major, minor = int(match.group(1)), int(match.group(2))
    if (major, minor) < (3, 18):
        raise RuntimeError(f"CMake version still too old: {version_line}. Need >= 3.18.")


def build_and_install_mimalloc(install_prefix="build/release-linux-aarch64"):
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
        cwd=mimalloc_build, check=True
    )

    print("[INFO] Building mimalloc...")
    subprocess.run(["make", "-j", str(os.cpu_count() or 2)], cwd=mimalloc_build, check=True)

    print("[INFO] Installing mimalloc to build output...")
    subprocess.run(["make", "install"], cwd=mimalloc_build, check=True)

    mod_dir = os.path.join(install_prefix, "smokinguns")
    os.makedirs(mod_dir, exist_ok=True)
    for lib in ["libmimalloc.so", "libmimalloc.so.3", "libmimalloc.so.3.5"]:
        src_lib = os.path.join(install_prefix, "lib", lib)
        if os.path.exists(src_lib):
            shutil.copy2(src_lib, os.path.join(mod_dir, lib))
            print(f"[INFO] Copied {lib} to {mod_dir}")

    print("[PATCHED] mimalloc built and installed.")


# ===========================================================================
# Mirror download
# ===========================================================================

def crawl_and_download_mirror(base_url, target_base_dir, current_subpath="", max_depth=10):
    if max_depth <= 0:
        return
    active_url = urllib.parse.urljoin(base_url, current_subpath)
    try:
        req = urllib.request.Request(active_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as response:
            html_content = response.read().decode('utf-8', errors='ignore')
        parser = DirectoryParser()
        parser.feed(html_content)
        local_dir = os.path.join(target_base_dir, current_subpath)
        os.makedirs(local_dir, exist_ok=True)
        if parser.files:
            print(f"  Found {len(parser.files)} .pk3 file(s) in {active_url}")
        for filename in sorted(set(parser.files)):
            file_url = urllib.parse.urljoin(active_url, filename)
            dest_path = os.path.join(local_dir, filename)
            if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
                print(f"  [SKIP] Already exists: {filename}")
                continue
            try:
                print(f"  Downloading: {filename} ...", end="", flush=True)
                urllib.request.urlretrieve(file_url, dest_path)
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                print(f" done ({size_mb:.1f} MB)")
            except Exception as dl_err:
                print(f" FAILED: {dl_err}")
                if os.path.exists(dest_path):
                    try:
                        os.remove(dest_path)
                    except OSError:
                        pass
        for subdir in sorted(set(parser.subdirs)):
            clean_subdir = subdir.lstrip('/')
            next_subpath = os.path.join(current_subpath, clean_subdir)
            crawl_and_download_mirror(base_url, target_base_dir, next_subpath, max_depth - 1)
    except Exception as e:
        print(f"[ERROR] Crawling {active_url}: {e}")


# ===========================================================================
# autoexec.cfg
# ===========================================================================

def write_autoexec(output_mod_dir):
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


# ===========================================================================
# Helpers
# ===========================================================================

def fix_git_safe_directory():
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", "/work"],
        check=False, capture_output=True
    )


# ===========================================================================
# Main
# ===========================================================================

def main():
    print("=" * 60)
    print(" Smokin' Guns ARM64 (RK3326 / Cortex-A35) Build Patcher")
    print("=" * 60)

    fix_git_safe_directory()

    patch_makefile('Makefile')
    patch_q_platform('code/qcommon/q_platform.h')
    inject_neon_math('code/qcommon/q_math.c')
    find_and_patch_simd_loops()

    install_newer_cmake()
    build_and_install_mimalloc()

    cpu_count = os.cpu_count() or 2
    cc = os.environ.get("CC", "gcc")

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

    mirror_root = "http://download.smokin-guns.org/mirror.9k.lv/smokinguns/smokinguns/"
    output_mod_dir = "build/release-linux-aarch64/smokinguns"
    print(f"\n[INFO] Mirroring .pk3 assets from {mirror_root}")
    print(f"[INFO] Target directory: {output_mod_dir}")
    print(f"[INFO] Excluded: sg_pak0.pk3 (370 MB base package)\n")
    crawl_and_download_mirror(mirror_root, output_mod_dir)

    write_autoexec(output_mod_dir)

    print("\n" + "=" * 60)
    print(" Build complete!")
    print("=" * 60)
    print(f"\n Artifact contents: {os.path.abspath('build/release-linux-aarch64')}")
    print(" Copy the entire folder to your device's port directory.")
    print("=" * 60)


if __name__ == '__main__':
    main()
