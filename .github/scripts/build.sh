#!/bin/bash
# ============================================================
# Smokin' Guns - Cross-Compile fuer ARM64 / RK3326
# Laeuft im ubuntu:20.04 x86_64 Container (kein QEMU).
# Erzeugt ARM64-Binaries mit GLIBC 2.31 (kompatibel mit R36S).
# ============================================================
set -e

export DEBIAN_FRONTEND=noninteractive

echo "==> Host arch: $(uname -m)"

# ------------------------------------------------------------
# 1. Multiarch aktivieren + apt-Quellen sauber konfigurieren
# ------------------------------------------------------------
dpkg --add-architecture arm64

rm -f /etc/apt/sources.list
printf '%s\n' \
  'deb [arch=amd64] http://archive.ubuntu.com/ubuntu focal main restricted universe multiverse' \
  'deb [arch=amd64] http://archive.ubuntu.com/ubuntu focal-updates main restricted universe multiverse' \
  'deb [arch=amd64] http://security.ubuntu.com/ubuntu focal-security main restricted universe multiverse' \
  > /etc/apt/sources.list

mkdir -p /etc/apt/sources.list.d
printf '%s\n' \
  'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal main restricted universe multiverse' \
  'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal-updates main restricted universe multiverse' \
  'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal-security main restricted universe multiverse' \
  > /etc/apt/sources.list.d/arm64.list

echo "==> apt-get update"
apt-get update

# ------------------------------------------------------------
# 2. Cross-Toolchain + ARM64-Zielbibliotheken installieren
# ------------------------------------------------------------
echo "==> Installing cross-toolchain and ARM64 libs"
apt-get install -y --no-install-recommends \
  build-essential cmake git pkg-config ca-certificates wget file zip python3 ccache \
  crossbuild-essential-arm64 \
  libsdl1.2-dev:arm64 \
  libfreetype6-dev:arm64 libjpeg-dev:arm64 libpng-dev:arm64 zlib1g-dev:arm64 \
  libogg-dev:arm64 libvorbis-dev:arm64 libopus-dev:arm64 libopusfile-dev:arm64 \
  libcurl4-openssl-dev:arm64 libopenal-dev:arm64 libspeex-dev:arm64 \
  libgbm-dev:arm64 libegl1-mesa-dev:arm64 libgles2-mesa-dev:arm64 \
  libdrm-dev:arm64 libx11-dev:arm64 libxext-dev:arm64 \
  libgl1-mesa-dev:arm64 libglu1-mesa-dev:arm64 \
  libudev-dev:arm64 libasound2-dev:arm64 libpulse-dev:arm64

which aarch64-linux-gnu-gcc
aarch64-linux-gnu-gcc --version | head -1

# ------------------------------------------------------------
# 3. Umgebungsvariablen - OPTIMIERT FUER CORTEX-A35
# ------------------------------------------------------------
export OPTIMIZE="-O3 -mcpu=cortex-a35 -mtune=cortex-a35 \
-pipe -fomit-frame-pointer -ffast-math -ftree-vectorize \
-fno-math-errno -fno-trapping-math -fno-semantic-interposition \
-fno-plt -fno-exceptions -fno-rtti -fno-stack-protector \
-fno-asynchronous-unwind-tables -fmerge-all-constants \
-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon \
-falign-jumps=16 -falign-labels=16 \
-fvect-cost-model=unlimited \
-fprefetch-loop-arrays \
-fgcse-after-reload \
-fipa-cp-clone \
-fpeel-loops \
-fpredictive-commoning \
-fsplit-paths \
-ftree-loop-distribute-patterns"
export LDFLAGS="-Wl,-O1 -Wl,--as-needed"

export SRC_DIR="/work/src"
export OUT_LIBS="/work/out/libs.aarch64"
export CC="aarch64-linux-gnu-gcc"
export CXX="aarch64-linux-gnu-g++"

export PKG_CONFIG_PATH="/usr/lib/aarch64-linux-gnu/pkgconfig"
export PKG_CONFIG_LIBDIR="/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig"
unset PKG_CONFIG_SYSROOT_DIR

mkdir -p "${SRC_DIR}" "${OUT_LIBS}"

# ------------------------------------------------------------
# 4. CMake 3.28.3
# ------------------------------------------------------------
echo "==> Installing CMake 3.28.3"
CMAKE_VERSION=3.28.3
wget -q "https://cmake.org/files/v3.28/cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz" -O /tmp/cmake.tar.gz
mkdir -p /opt/cmake
tar -xzf /tmp/cmake.tar.gz -C /opt/cmake --strip-components=1
export PATH=/opt/cmake/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cmake --version

# ------------------------------------------------------------
# 5. Toolchain-File erzeugen
# ------------------------------------------------------------
cat > /tmp/aarch64-toolchain.cmake <<'EOF'
set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)
set(CMAKE_C_COMPILER aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
EOF
export TOOLCHAIN=/tmp/aarch64-toolchain.cmake

# ------------------------------------------------------------
# 6. gl4es
# ------------------------------------------------------------
echo "==> Building gl4es"
cd "${SRC_DIR}"
git clone --depth=1 https://github.com/ptitSeb/gl4es.git
cd gl4es
mkdir -p build && cd build
cmake .. \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="${OPTIMIZE}" \
  -DNOX11=ON -DGBM=ON -DEGL_WRAPPER=ON \
  -DDEFAULT_ES=2 -DSTATICLIB=OFF
make -j$(nproc)
GL4ES_LIB=$(find "${SRC_DIR}/gl4es" -name libGL.so.1 -print -quit)
EGL_LIB=$(find "${SRC_DIR}/gl4es" -name libEGL.so.1 -print -quit)
cp "${GL4ES_LIB}" "${OUT_LIBS}/libGL.so.1"
cp "${EGL_LIB}"   "${OUT_LIBS}/libEGL.so.1"

# ------------------------------------------------------------
# 7. SDL2 2.30.2
# ------------------------------------------------------------
echo "==> Building SDL2"
cd "${SRC_DIR}"
git clone --depth=1 -b release-2.30.2 https://github.com/libsdl-org/SDL.git
cd SDL
mkdir -p build && cd build
cmake .. \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/sdl2-aarch64 \
  -DCMAKE_C_FLAGS="${OPTIMIZE}" \
  -DSDL_STATIC=OFF -DSDL_SHARED=ON \
  -DSDL_KMSDRM=ON -DSDL_WAYLAND=OFF \
  -DSDL_X11=ON -DSDL_ALSA=ON -DSDL_PULSEAUDIO=ON
make -j$(nproc)
make install
SDL2_LIB=$(find /opt/sdl2-aarch64 -name libSDL2-2.0.so.0 -print -quit)
cp "${SDL2_LIB}" "${OUT_LIBS}/libSDL2-2.0.so.0"

# ------------------------------------------------------------
# 8. sdl12-compat
# ------------------------------------------------------------
echo "==> Building sdl12-compat"
cd "${SRC_DIR}"
git clone --depth=1 https://github.com/libsdl-org/sdl12-compat.git
cd sdl12-compat
python3 /work/.github/scripts/patch_arm64.py
mkdir -p build && cd build
cmake .. \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSDL2_INCLUDE_DIR=/opt/sdl2-aarch64/include/SDL2 \
  -DSDL2_LIBRARY=/opt/sdl2-aarch64/lib/libSDL2-2.0.so \
  -DCMAKE_C_FLAGS="${OPTIMIZE} -fvisibility=default"
make -j$(nproc)
SDL12_LIB=$(find "${SRC_DIR}/sdl12-compat" -name libSDL-1.2.so.0 -print -quit)
cp "${SDL12_LIB}" "${OUT_LIBS}/libSDL-1.2.so.0"

# ------------------------------------------------------------
# 9. Smokin' Guns
# ------------------------------------------------------------
echo "==> Building Smokin' Guns"
cd "${SRC_DIR}"
git clone --depth=1 https://github.com/smokin-guns/SmokinGuns.git
cd SmokinGuns
python3 /work/.github/scripts/patch_arm64.py

# ------------------------------------------------------------
# 9b. PURE-SERVER NATIVE-VM BYPASS
#     Entfernt das !fs_numServerPaks-Gate in FS_FindVM.
#     KEIN Fake-Checksum-Bypass noetig (pk3 unveraendert).
# ------------------------------------------------------------
echo "==> Applying pure-server native-VM bypass (files.c)"
python3 - <<'PYEOF'
import re, sys
from pathlib import Path

fc = Path("code/qcommon/files.c")
if not fc.exists():
    for p in Path("code").rglob("files.c"):
        fc = p
        break
if not fc.exists():
    print("[bypass] files.c not found", file=sys.stderr)
    sys.exit(1)

src = fc.read_text()
orig = src

src, n = re.subn(
    r'if\s*\(\s*search->dir\s*&&\s*!fs_numServerPaks\s*\)',
    'if ( search->dir ) /* PURE_BYPASS v13.9: native .so auch bei pure */',
    src, count=1,
)
if n == 0:
    print("[bypass] WARNING: FS_FindVM pure-gate nicht gefunden", file=sys.stderr)
else:
    print(f"[bypass] FS_FindVM pure-gate entfernt: {n}x")

if src != orig:
    fc.write_text(src)
    print(f"[bypass] files.c updated ({len(orig)} -> {len(src)} bytes)")
PYEOF

# ------------------------------------------------------------
# 10. Build
# ------------------------------------------------------------
make release -j$(nproc) \
  PLATFORM=linux \
  ARCH=aarch64 \
  COMPILE_ARCH=aarch64 \
  COMPILE_PLATFORM=linux \
  CC="${CC}" \
  BUILD_STANDALONE=1 \
  Q3UIDIR=code/ui \
  BUILD_GAME_QVM=0 \
  BUILD_GAME_SO=1 \
  BUILD_SERVER=0 \
  BUILD_RENDERER_REND2=0 \
  USE_OPENAL=0 \
  USE_CODEC_VORBIS=0 \
  USE_CURL=0 \
  USE_MUMBLE=0 \
  USE_VOIP=0 \
  USE_INTERNAL_ZLIB=1 \
  USE_INTERNAL_SPEEX=1 \
  USE_LOCAL_HEADERS=0 \
  WERROR=0 \
  OPTIMIZE="${OPTIMIZE}" \
  LDFLAGS="${LDFLAGS}"

# ------------------------------------------------------------
# 11. Bibliotheken neben die Binaerdateien
# ------------------------------------------------------------
REL_DIR="${SRC_DIR}/SmokinGuns/build/release-linux-aarch64"
cp "${OUT_LIBS}"/*.so* "${REL_DIR}/"
echo "=== Final release directory ==="
ls -la "${REL_DIR}/"
echo "=== smokinguns subdir ==="
ls -la "${REL_DIR}/smokinguns/" || true

echo "==> Cross-Compile erfolgreich."
