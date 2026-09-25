# Toolchain-Datei fuer aarch64-Cross-Compilation (Ubuntu Multiarch)
#
# WICHTIG: KEIN CMAKE_FIND_ROOT_PATH setzen. Bei Ubuntu-Multiarch
# (crossbuild-essential-arm64 + :arm64-Pakete ins System installiert)
# existiert kein befuelltes Sysroot unter /usr/aarch64-linux-gnu.
# Die ARM64-Bibliotheken liegen unter /usr/lib/aarch64-linux-gnu,
# die Header unter /usr/include und /usr/include/aarch64-linux-gnu.
#
# MODE_LIBRARY/INCLUDE/PACKAGE auf BOTH: CMake findet sowohl die
# Multiarch-Pfade als auch die Host-Pfade. ONLY wuerde die Suche auf
# einen (leeren) CMAKE_FIND_ROOT_PATH einschraenken und nichts finden.

set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR aarch64)

set(CMAKE_C_COMPILER   aarch64-linux-gnu-gcc)
set(CMAKE_CXX_COMPILER aarch64-linux-gnu-g++)

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE BOTH)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE BOTH)
