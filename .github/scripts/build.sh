#!/bin/bash
# ============================================================
# Cross-Compile Smokin' Guns fuer ARM64 / RK3326 auf x86_64.
# Kein QEMU, kein Docker. Nativ auf dem GitHub-Runner.
# ============================================================
set -e

echo "==> Host architecture:"
uname -m

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
# CMake 3.28.3 (Ubuntu 20.04 hat 3.16 - zu alt fuer gl4es)
# ------------------------------------------------------------
echo "==> Installing CMake 3.28.3"
if [ ! -x /opt/cmake/bin/cmake ]; then
    wget -q "https://cmake.org/files/v3.28/cmake-3.28.3-linux-x86_64.tar.gz" -O /tmp/cmake.tar.gz
    mkdir -p /opt/cmake
    tar -xzf /tmp/cmake.tar.gz -C /opt/cmake --strip-components=1
fi
export PATH=/opt/cmake/bin:${PATH}
cmake --version

# ------------------------------------------------------------
# gl4es
# ------------------------------------------------------------
echo "==> Building gl4es (cross-compile)"
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
# SDL2 2.30.2
# ------------------------------------------------------------
echo "==> Building SDL2 (cross-compile)"
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
  -DSDL_X11=OFF -DSDL_ALSA=OFF -DSDL_PULSEAUDIO=OFF \
  -DSDL_OSS=OFF -DSDL_DISKAUDIO=ON -DSDL_DUMMYAUDIO=ON
make -j$(nproc)
make install
SDL2_LIB=$(find /opt/sdl2-aarch64 -name "libSDL2-2.0.so.0" -print -quit)
echo "Found SDL2: ${SDL2_LIB}"
cp "${SDL2_LIB}" "${OUT_LIBS}/libSDL2-2.0.so.0"

# ------------------------------------------------------------
# sdl12-compat
# ------------------------------------------------------------
echo "==> Building sdl12-compat (cross-compile)"
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
# Smokin' Guns
# ------------------------------------------------------------
echo "==> Building Smokin' Guns (cross-compile)"
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
