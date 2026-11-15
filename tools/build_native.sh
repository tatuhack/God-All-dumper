#!/bin/sh
set -eu
: "${ANDROID_NDK_HOME:?Set ANDROID_NDK_HOME to Android NDK 28.2.13676358}"
: "${CMAKE_BIN:?Set CMAKE_BIN to CMake 4.1.2 bin directory}"
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILD=${1:-"$ROOT/build/native"}
mkdir -p "$BUILD"
BUILD=$(CDPATH= cd -- "$BUILD" && pwd)
for ABI in arm64-v8a armeabi-v7a x86 x86_64; do
  "$CMAKE_BIN/cmake" -S "$ROOT/module/src/main/cpp" -B "$BUILD/$ABI" -G Ninja \
    "-DCMAKE_MAKE_PROGRAM=$CMAKE_BIN/ninja" \
    "-DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK_HOME/build/cmake/android.toolchain.cmake" \
    "-DANDROID_ABI=$ABI" -DANDROID_PLATFORM=android-23 -DANDROID_STL=c++_static \
    -DMODULE_NAME=pxojdumper -DCMAKE_BUILD_TYPE=Release \
    "-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=$BUILD/$ABI/lib"
  "$CMAKE_BIN/cmake" --build "$BUILD/$ABI" --parallel 2
done
python3 "$ROOT/tools/package_module.py" --libs "$BUILD" --output "$ROOT/out"
