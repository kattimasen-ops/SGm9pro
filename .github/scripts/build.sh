#!/bin/bash
# ============================================================
# Smokin' Guns - Cross-Compile fuer ARM64 / RK3326
# Laeuft im ubuntu:20.04 x86_64 Container.
# Erzeugt ARM64-Binaries mit GLIBC 2.31 (kompatibel mit R36S).
# ============================================================
set -e

export DEBIAN_FRONTEND=noninteractive

# ------------------------------------------------------------
# 1. ARM64-Multiarch im Container einrichten
# ------------------------------------------------------------
echo "==> Setting up ARM64 multiarch"
dpkg --add-architecture arm64

# Host-Quellen (amd64 only)
rm -f /etc/apt/sources.list
printf '%s\n' \
  'deb [arch=amd64] http://archive.ubuntu.com/ubuntu focal main restricted universe multiverse' \
  'deb [arch=amd64] http://archive.ubuntu.com/ubuntu focal-updates main restricted universe multiverse' \
  'deb [arch=amd64] http://security.ubuntu.com/ubuntu focal-security main restricted universe multiverse' \
  > /etc/apt/sources.list

# ARM64-Quellen (arm64 only)
mkdir -p /etc/apt/sources.list.d
printf '%s\n' \
  'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal main restricted universe multiverse' \
  'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal-updates main restricted universe multiverse' \
  'deb [arch=arm64] http://ports.ubuntu.com/ubuntu-ports focal-security main restricted universe multiverse' \
  > /etc/apt/sources.list.d/arm64.list

echo "==> apt-get update"
apt-get update

# ------------------------------------------------------------
# 2. Abhaengigkeiten installieren
# ------------------------------------------------------------
echo "==> Installing cross-toolchain and ARM64 libraries"
apt-get install -y --no-install-recommends \
  build-essential cmake git ccache python3 pkg-config wget \
  crossbuild-essential-arm64 \
  libsdl1.2-dev:arm64 \
  libopenal-dev:arm64 libcurl4-openssl-dev:arm64 \
  libvorbis-dev:arm64 libogg-dev:arm64 \
  libfreetype6-dev:arm64 libpng-dev:arm64 zlib1g-dev:arm64 \
  libopus-dev:arm64 libopusfile-dev:arm64 libspeex-dev:arm64 \
  libgbm-dev:arm64 libegl1-mesa-dev:arm64 libgles2-mesa-dev:arm64 \
  libdrm-dev:arm64 libx11-dev:arm64 libxext-dev:arm64 \
  libgl1-mesa-dev:arm64 libglu1-mesa-dev:arm64 \
  libudev-dev:arm64 libasound2-dev:arm64 libpulse-dev:arm64

# ------------------------------------------------------------
# 3. Pfade und Umgebung
# ------------------------------------------------------------
export OPTIMIZE="-O3 -mcpu=cortex-a35 -mtune=cortex-a35 \
-pipe -fomit-frame-pointer -ffast-math -ftree-vectorize \
-fno-math-errno -fno-trapping-math -fno-semantic-interposition \
-fno-plt -fno-exceptions -fno-rtti -fno-stack-protector \
-fno-asynchronous-unwind-tables -fmerge-all-constants \
-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon"
export LDFLAGS="-Wl,-O1 -Wl,--as-needed"

export SRC_DIR="/work/build-work"
export OUT_LIBS="/work/out/libs.aarch64"
export PATCH_SCRIPT="/work/.github/scripts/patch_arm64.py"
export TOOLCHAIN="/work/.github/scripts/aarch64-toolchain.cmake"
export CC="aarch64-linux-gnu-gcc"
export CXX="aarch64-linux-gnu-g++"

# pkg-config muss ARM64-Pfade durchsuchen
export PKG_CONFIG_PATH="/usr/lib/aarch64-linux-gnu/pkgconfig"
export PKG_CONFIG_LIBDIR="/usr/lib/aarch64-linux-gnu/pkgconfig:/usr/share/pkgconfig"
unset PKG_CONFIG_SYSROOT_DIR

mkdir -p "${SRC_DIR}" "${OUT_LIBS}"

# ------------------------------------------------------------
# 4. CMake 3.28.3 (focal hat nur 3.16)
# ------------------------------------------------------------
echo "==> Installing CMake 3.28.3"
CMAKE_VERSION=3.28.3
cd /tmp
wget -q "https://cmake.org/files/v3.28/cmake-${CMAKE_VERSION}-linux-x86_64.tar.gz" -O /tmp/cmake.tar.gz
mkdir -p /opt/cmake
tar -xzf /tmp/cmake.tar.gz -C /opt/cmake --strip-components=1
export PATH=/opt/cmake/bin:${PATH}
cmake --version

# ------------------------------------------------------------
# 5. gl4es
# ------------------------------------------------------------
echo "==> Building gl4es"
cd "${SRC_DIR}"
[ -d gl4es ] || git clone --depth=1 https://github.com/ptitSeb/gl4es.git
cd gl4es
rm -rf build && mkdir build && cd build
cmake .. \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_FLAGS="${OPTIMIZE}" \
  -DNOX11=ON -DGBM=ON -DEGL_WRAPPER=ON \
  -DDEFAULT_ES=2 -DSTATICLIB=OFF
make -j$(nproc)
GL4ES_GL=$(find "${SRC_DIR}/gl4es" -name "libGL.so.1" -print -quit)
GL4ES_EGL=$(find "${SRC_DIR}/gl4es" -name "libEGL.so.1" -print -quit)
echo "Found libGL:  ${GL4ES_GL}"
echo "Found libEGL: ${GL4ES_EGL}"
cp "${GL4ES_GL}"  "${OUT_LIBS}/libGL.so.1"
cp "${GL4ES_EGL}" "${OUT_LIBS}/libEGL.so.1"

# ------------------------------------------------------------
# 6. SDL2
# ------------------------------------------------------------
echo "==> Building SDL2"
cd "${SRC_DIR}"
[ -d SDL ] || git clone --depth=1 -b release-2.30.2 https://github.com/libsdl-org/SDL.git
cd SDL
rm -rf build && mkdir build && cd build
cmake .. \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/opt/sdl2-aarch64 \
  -DSDL_STATIC=OFF -DSDL_SHARED=ON \
  -DSDL_KMSDRM=ON -DSDL_WAYLAND=OFF \
  -DSDL_X11=ON -DSDL_ALSA=ON -DSDL_PULSEAUDIO=ON
make -j$(nproc)
make install
SDL2_LIB=$(find /opt/sdl2-aarch64 -name "libSDL2-2.0.so.0" -print -quit)
echo "Found SDL2: ${SDL2_LIB}"
cp "${SDL2_LIB}" "${OUT_LIBS}/libSDL2-2.0.so.0"

# ------------------------------------------------------------
# 7. sdl12-compat
# ------------------------------------------------------------
echo "==> Building sdl12-compat"
cd "${SRC_DIR}"
[ -d sdl12-compat ] || git clone --depth=1 https://github.com/libsdl-org/sdl12-compat.git
cd sdl12-compat
python3 "${PATCH_SCRIPT}"
rm -rf build && mkdir build && cd build
cmake .. \
  -DCMAKE_TOOLCHAIN_FILE="${TOOLCHAIN}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DSDL2_INCLUDE_DIR=/opt/sdl2-aarch64/include/SDL2 \
  -DSDL2_LIBRARY=/opt/sdl2-aarch64/lib/libSDL2-2.0.so \
  -DCMAKE_C_FLAGS="${OPTIMIZE} -fvisibility=default"
make -j$(nproc)
SDL12_LIB=$(find "${SRC_DIR}/sdl12-compat" -name "libSDL-1.2.so.0" -print -quit)
echo "Found sdl12-compat: ${SDL12_LIB}"
cp "${SDL12_LIB}" "${OUT_LIBS}/libSDL-1.2.so.0"

# ------------------------------------------------------------
# 8. Smokin' Guns
# ------------------------------------------------------------
echo "==> Building Smokin' Guns"
cd "${SRC_DIR}"
[ -d SmokinGuns ] || git clone --depth=1 https://github.com/smokin-guns/SmokinGuns.git
cd SmokinGuns
python3 "${PATCH_SCRIPT}"

make release -j$(nproc) \
  PLATFORM=linux \
  ARCH=aarch64 \
  COMPILE_ARCH=aarch64 \
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

REL_DIR="${SRC_DIR}/SmokinGuns/build/release-linux-aarch64"
cp "${OUT_LIBS}"/*.so* "${REL_DIR}/"
echo "=== Final release directory ==="
ls -la "${REL_DIR}/"
echo "=== smokinguns subdir ==="
ls -la "${REL_DIR}/smokinguns/" || true

echo "==> Cross-Compile erfolgreich."
