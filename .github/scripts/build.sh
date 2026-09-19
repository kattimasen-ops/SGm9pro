#!/bin/bash
# ============================================================
# Smokin' Guns - ARM64 Build (ubuntu:20.04 aarch64 + QEMU)
# Basiert auf dem erfolgreichen 38-Minuten-Run.
# Aim-Assist wird ueber patch_arm64.py injiziert.
#
# Robustheit:
#   - make mit -j2 statt -j$(nproc)  (halbiert QEMU-Speicherdruck)
#   - Dreifacher Retry pro make-Aufruf (faengt QEMU-Zufallscrashs ab)
#   - ccache wird per GitHub Actions Cache persistiert
#   - SDL2 und sdl12-compat: nur Bibliotheks-Targets bauen (keine Tests)
# ============================================================
set -e

export DEBIAN_FRONTEND=noninteractive
export OPTIMIZE="-O3 -mcpu=cortex-a35 -mtune=cortex-a35 \
-pipe -fomit-frame-pointer -ffast-math -ftree-vectorize \
-fno-math-errno -fno-trapping-math -fno-semantic-interposition \
-fno-plt -fno-exceptions -fno-rtti -fno-stack-protector \
-fno-asynchronous-unwind-tables -fmerge-all-constants \
-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon"
export LDFLAGS="-Wl,-O1 -Wl,--as-needed"

echo "==> pwd: $(pwd)"

# ------------------------------------------------------------
# Abhaengigkeiten (identisch zum erfolgreichen 38-Minuten-Run)
# ------------------------------------------------------------
apt-get update
apt-get install -y --no-install-recommends \
  build-essential git pkg-config ca-certificates wget file zip python3 ccache \
  libsdl1.2-dev libfreetype6-dev libjpeg-dev libpng-dev zlib1g-dev \
  libogg-dev libvorbis-dev libopus-dev libopusfile-dev libcurl4-openssl-dev \
  libopenal-dev libspeex-dev libgbm-dev libegl1-mesa-dev libgles2-mesa-dev \
  libdrm-dev libx11-dev libxext-dev libgl1-mesa-dev libglu1-mesa-dev \
  libudev-dev libasound2-dev libpulse-dev autoconf automake libtool

git config --global --add safe.directory '*'
ccache -M 2G
export CC="ccache gcc"
export CXX="ccache g++"

# ------------------------------------------------------------
# CMake 3.28.3 (Ubuntu 20.04 hat nur 3.16, zu alt fuer gl4es)
# ------------------------------------------------------------
CMAKE_VERSION=3.28.3
wget -q https://cmake.org/files/v3.28/cmake-${CMAKE_VERSION}-linux-aarch64.tar.gz -O /tmp/cmake.tar.gz
mkdir -p /opt/cmake
tar -xzf /tmp/cmake.tar.gz -C /opt/cmake --strip-components=1
export PATH=/opt/cmake/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
cmake --version

mkdir -p /work/src /work/out/libs.aarch64

# ------------------------------------------------------------
# gl4es
# ------------------------------------------------------------
echo "==> Building gl4es"
cd /work/src
git clone --depth=1 https://github.com/ptitSeb/gl4es.git
cd gl4es
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_FLAGS="${OPTIMIZE}" \
  -DNOX11=ON -DGBM=ON -DEGL_WRAPPER=ON -DDEFAULT_ES=2 -DSTATICLIB=OFF

# Robustheits-Retry: bis zu 3 Versuche
make -j2 || make -j2 || make -j2

GL4ES_LIB=$(find /work/src/gl4es -name libGL.so.1 -print -quit)
EGL_LIB=$(find /work/src/gl4es -name libEGL.so.1 -print -quit)
cp "${GL4ES_LIB}" /work/out/libs.aarch64/libGL.so.1
cp "${EGL_LIB}"   /work/out/libs.aarch64/libEGL.so.1

# ------------------------------------------------------------
# SDL2 2.30.2  (nur Bibliothek, KEINE Tests)
# ------------------------------------------------------------
echo "==> Building SDL2 (library target only)"
cd /work/src
git clone --depth=1 -b release-2.30.2 https://github.com/libsdl-org/SDL.git
cd SDL
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/opt/sdl2 \
  -DSDL_STATIC=OFF -DSDL_SHARED=ON -DSDL_KMSDRM=ON -DSDL_WAYLAND=OFF \
  -DSDL_TESTS=OFF

# Nur die Bibliothek bauen - Tests ueberspringen (spart ~30 QEMU-Compiles)
make -j2 SDL2 || make -j2 SDL2 || make -j2 SDL2
make -j2 install || make -j2 install || make -j2 install

SDL2_LIB=$(find /opt/sdl2 -name libSDL2-2.0.so.0 -print -quit)
cp "${SDL2_LIB}" /work/out/libs.aarch64/libSDL2-2.0.so.0

# ------------------------------------------------------------
# sdl12-compat (mit patch_arm64.py)  (nur Bibliothek, KEINE Tests)
# ------------------------------------------------------------
echo "==> Building sdl12-compat (library targets only)"
cd /work/src
git clone --depth=1 https://github.com/libsdl-org/sdl12-compat.git
cd sdl12-compat
python3 /work/.github/scripts/patch_arm64.py
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release \
  -DSDL2_INCLUDE_DIR=/opt/sdl2/include/SDL2 \
  -DSDL2_LIBRARY=/opt/sdl2/lib/libSDL2-2.0.so \
  -DCMAKE_C_FLAGS="${OPTIMIZE} -fvisibility=default"

# Nur die zwei Bibliotheks-Targets bauen - Tests ueberspringen
make -j2 SDL SDLmain || make -j2 SDL SDLmain || make -j2 SDL SDLmain

SDL12_LIB=$(find /work/src/sdl12-compat -name libSDL-1.2.so.0 -print -quit)
cp "${SDL12_LIB}" /work/out/libs.aarch64/libSDL-1.2.so.0

# ------------------------------------------------------------
# Smokin' Guns (mit patch_arm64.py — Aim-Assist wird injiziert)
# ------------------------------------------------------------
echo "==> Building Smokin' Guns"
cd /work/src
git clone --depth=1 https://github.com/smokin-guns/SmokinGuns.git
cd SmokinGuns
python3 /work/.github/scripts/patch_arm64.py

make release -j2 PLATFORM=linux \
  ARCH=aarch64 \
  COMPILE_ARCH=aarch64 \
  CC="ccache gcc" \
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
  LDFLAGS="${LDFLAGS}" \
  || \
make release -j2 PLATFORM=linux \
  ARCH=aarch64 \
  COMPILE_ARCH=aarch64 \
  CC="ccache gcc" \
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
  LDFLAGS="${LDFLAGS}" \
  || \
make release -j2 PLATFORM=linux \
  ARCH=aarch64 \
  COMPILE_ARCH=aarch64 \
  CC="ccache gcc" \
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
# Bibliotheken neben die Binaerdateien
# ------------------------------------------------------------
REL_DIR="/work/src/SmokinGuns/build/release-linux-aarch64"
cp /work/out/libs.aarch64/*.so* "${REL_DIR}/"
echo "=== Final release directory ==="
ls -la "${REL_DIR}/"
echo "==> Build erfolgreich."
