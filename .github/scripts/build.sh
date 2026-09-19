#!/bin/bash
# ============================================================
# Build-Skript fuer Smokin' Guns auf ARM64 / RK3326
# Laeuft im Ubuntu 18.04 aarch64 Docker-Container.
#
# GLIBC 2.27 (Ubuntu 18.04) → kompatibel mit Handheld (GLIBC 2.30).
# GCC 9 aus ubuntu-toolchain-r/test → stabil unter QEMU.
# (GCC 7 crasht unter QEMU mit ICE/Segfault in gl4es.)
# ============================================================
set -e

echo "==> pwd: $(pwd)"
echo "==> Inhalt:"
ls -la

# --- Umgebungsvariablen -------------------------------------
export OPTIMIZE="-O3 -mcpu=cortex-a35 -mtune=cortex-a35 \
-pipe -fomit-frame-pointer -ffast-math -ftree-vectorize \
-fno-math-errno -fno-trapping-math -fno-semantic-interposition \
-fno-plt -fno-exceptions -fno-rtti -fno-stack-protector \
-fno-asynchronous-unwind-tables -fmerge-all-constants \
-falign-functions=16 -falign-loops=16 -DNDEBUG -w -fcommon"
export LDFLAGS="-Wl,-O1 -Wl,--as-needed"
export DEBIAN_FRONTEND=noninteractive

export OUT_LIBS="/work/out/libs.aarch64"
export SRC_DIR="/work/build-work"
export PATCH_SCRIPT="/work/.github/scripts/patch_arm64.py"

mkdir -p "${OUT_LIBS}" "${SRC_DIR}"

# --- Systemabhaengigkeiten ----------------------------------
echo "==> apt-get update"
apt-get update

echo "==> apt-get install (Basis-Pakete)"
apt-get install -y --no-install-recommends \
  ca-certificates \
  software-properties-common \
  gnupg \
  wget

# --- GCC 9 aus PPA installieren -----------------------------
# GCC 7 (Ubuntu-18.04-Default) crasht unter QEMU.
# GCC 9 ist stabil und ausgereift fuer aarch64-QEMU.
echo "==> Adding ubuntu-toolchain-r/test PPA for GCC 9"
add-apt-repository -y ppa:ubuntu-toolchain-r/test
apt-get update

echo "==> Installing GCC 9 and all build dependencies"
apt-get install -y --no-install-recommends \
  build-essential \
  gcc-9 g++-9 \
  make cmake git ccache python3 pkg-config \
  autoconf automake libtool \
  libsdl1.2-dev \
  libfreetype6-dev \
  libjpeg-dev \
  libpng-dev \
  zlib1g-dev \
  libogg-dev \
  libvorbis-dev \
  libopus-dev \
  libopusfile-dev \
  libcurl4-openssl-dev \
  libopenal-dev \
  libspeex-dev \
  libgbm-dev \
  libegl1-mesa-dev \
  libgles2-mesa-dev \
  libdrm-dev \
  libx11-dev \
  libxext-dev \
  libgl1-mesa-dev \
  libglu1-mesa-dev \
  libudev-dev \
  libasound2-dev \
  libpulse-dev

# --- Compiler auf GCC 9 umstellen ---------------------------
echo "==> Setting GCC 9 as the default compiler"
update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 90 \
  --slave /usr/bin/g++ g++ /usr/bin/g++-9 \
  --slave /usr/bin/gcc-ar gcc-ar /usr/bin/gcc-ar-9 \
  --slave /usr/bin/gcc-nm gcc-nm /usr/bin/gcc-nm-9 \
  --slave /usr/bin/gcc-ranlib gcc-ranlib /usr/bin/gcc-ranlib-9

export CC=gcc-9
export CXX=g++-9
echo "==> gcc version:"
gcc --version
echo "==> g++ version:"
g++ --version

which sdl-config && sdl-config --version

# --- CMake 3.28.3 manuell installieren ----------------------
# Ubuntu 18.04 hat CMake 3.10, das kein check_compiler_flag kennt.
echo "==> Installing CMake 3.28.3"
CMAKE_VERSION=3.28.3
cd /tmp
wget -q "https://cmake.org/files/v3.28/cmake-${CMAKE_VERSION}-linux-aarch64.tar.gz" -O /tmp/cmake.tar.gz
mkdir -p /opt/cmake
tar -xzf /tmp/cmake.tar.gz -C /opt/cmake --strip-components=1
export PATH=/opt/cmake/bin:${PATH}
cmake --version

# --- gl4es --------------------------------------------------
# Mit GCC 9 ist die volle Optimierung wieder sicher.
echo "==> Building gl4es"
cd "${SRC_DIR}"
git clone --depth=1 https://github.com/ptitSeb/gl4es.git
cd gl4es
mkdir -p build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=gcc-9 \
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

# --- SDL2 ---------------------------------------------------
echo "==> Building SDL2"
cd "${SRC_DIR}"
git clone --depth=1 -b release-2.30.2 https://github.com/libsdl-org/SDL.git
cd SDL
mkdir -p build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=gcc-9 \
  -DCMAKE_INSTALL_PREFIX=/opt/sdl2 \
  -DSDL_STATIC=OFF -DSDL_SHARED=ON \
  -DSDL_KMSDRM=ON -DSDL_WAYLAND=OFF
make -j$(nproc) install
SDL2_LIB=$(find /opt/sdl2 -name "libSDL2-2.0.so.0" -print -quit)
echo "Found SDL2: ${SDL2_LIB}"
cp "${SDL2_LIB}" "${OUT_LIBS}/libSDL2-2.0.so.0"

# --- sdl12-compat -------------------------------------------
echo "==> Building sdl12-compat"
cd "${SRC_DIR}"
git clone --depth=1 https://github.com/libsdl-org/sdl12-compat.git
cd sdl12-compat
python3 "${PATCH_SCRIPT}"
mkdir -p build && cd build
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER=gcc-9 \
  -DSDL2_INCLUDE_DIR=/opt/sdl2/include/SDL2 \
  -DSDL2_LIBRARY=/opt/sdl2/lib/libSDL2-2.0.so \
  -DCMAKE_C_FLAGS="${OPTIMIZE} -fvisibility=default"
make -j$(nproc)
SDL12_LIB=$(find "${SRC_DIR}/sdl12-compat" -name "libSDL-1.2.so.0" -print -quit)
echo "Found sdl12-compat: ${SDL12_LIB}"
cp "${SDL12_LIB}" "${OUT_LIBS}/libSDL-1.2.so.0"

# --- Smokin' Guns -------------------------------------------
echo "==> Building Smokin' Guns"
cd "${SRC_DIR}"
git clone --depth=1 https://github.com/smokin-guns/SmokinGuns.git
cd SmokinGuns
python3 "${PATCH_SCRIPT}"

make release -j$(nproc) \
  PLATFORM=linux \
  ARCH=aarch64 \
  COMPILE_ARCH=aarch64 \
  CC="ccache gcc-9" \
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

echo "==> Build erfolgreich."
