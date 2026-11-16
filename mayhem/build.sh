#!/usr/bin/env bash
#
# mayhem/build.sh — builds the fuzz target and the test oracle's server.
#
#  * /mayhem/rfb_server  AFL harness: the whole TurboVNC server (Xvnc, built with $SANITIZER_FLAGS and
#                        afl-clang-fast) linked with mayhem/rfb_harness.c instead of the stock main().
#  * mayhem/build-test/bin/Xvnc  the stock server built with the project's normal flags, for test.sh.
#
# Runs offline: everything comes from apt -dev packages and the in-tree sources (zlib-ng is bundled).
set -euo pipefail

[ -n "${SOURCE_DATE_EPOCH:-}" ] || unset SOURCE_DATE_EPOCH

: "${SANITIZER_FLAGS=-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer}"
: "${DEBUG_FLAGS:=-g -gdwarf-3}"
: "${CC:=clang}" ; : "${CXX:=clang++}"
: "${MAYHEM_JOBS:=$(nproc)}"
: "${COVERAGE_FLAGS=}"
: "${SRC:=/mayhem}"
export SANITIZER_FLAGS DEBUG_FLAGS CC CXX MAYHEM_JOBS COVERAGE_FLAGS

cd "$SRC"
OUT="$SRC/mayhem"

# TVNC_DRI3=0: DRI3 needs xshmfence/gbm, which add nothing to the RFB protocol surface.
# TVNC_BUILDVIEWER=0: the Java viewer is not the server under test.
CMAKE_COMMON=(-G Ninja -DCMAKE_BUILD_TYPE=Release -DTVNC_BUILDVIEWER=0 -DTVNC_DRI3=0
              -DTVNC_BUILDWEBSERVER=0 -DTVNC_BUILDSYSTEMD=0)

# 1) The stock server with normal flags: test.sh's oracle runs it.
# CMake reads the compiler from $CC on the first configure only and keeps it cached afterwards.
cmake -S "$SRC" -B "$OUT/build-test" "${CMAKE_COMMON[@]}" -DCMAKE_C_FLAGS="$COVERAGE_FLAGS"
cmake --build "$OUT/build-test" --target Xvnc -j"$MAYHEM_JOBS"

# 2) The sanitized, AFL-instrumented server; the object and link line are Xvnc's own, with
#    stubmain.c.o (the stock main) swapped for the harness.
AFLCC=afl-clang-fast
# Relaxed UBSan checks: the Xorg core is full of benign idioms that otherwise abort server start-up before a
# single RFB byte is read: NULL passed to memset/memcpy with size 0 (nonnull-attribute, dix/privates.c), zero
# offset applied to NULL (pointer-overflow, mi/mieq.c), shifts of -1 and 1023<<22 (shift-base, dix/resource.c,
# Xext/hashtable.c, mi/micmap.c) and calls through the NoopDDA stub (function, dix/*.c). ASan and the rest of
# UBSan stay halting.
RELAX="-fno-sanitize=nonnull-attribute,pointer-overflow,shift-base,function"
FUZZ_FLAGS="$SANITIZER_FLAGS $RELAX $DEBUG_FLAGS"
# CMAKE_C_FLAGS_RELEASE=-O2: CMake's default Release flags carry -DNDEBUG, which would compile out the
# server's assert()s (e.g. the ZRLE palette bounds in hw/vnc/zrle*.c); unix/CMakeLists.txt raises -O2 to -O3.
CC="$AFLCC" cmake -S "$SRC" -B "$OUT/build-fuzz" "${CMAKE_COMMON[@]}" \
      -DCMAKE_C_FLAGS="$FUZZ_FLAGS" -DCMAKE_C_FLAGS_RELEASE=-O2
cmake --build "$OUT/build-fuzz" --target Xvnc -j"$MAYHEM_JOBS"

# shellcheck disable=SC2086
$AFLCC $FUZZ_FLAGS -c "$OUT/rfb_harness.c" -o "$OUT/build-fuzz/rfb_harness.o"
# shellcheck disable=SC2086
$CXX $SANITIZER_FLAGS $DEBUG_FLAGS -c "$OUT/lsan_off.cc" -o "$OUT/build-fuzz/lsan_off.o"

cd "$OUT/build-fuzz"
LINK=$(ninja -t commands bin/Xvnc | tail -n 1)
LINK=${LINK#: && }
LINK=${LINK% && :}
LINK=${LINK//unix\/Xvnc\/programs\/Xserver\/CMakeFiles\/Xvnc.dir\/dix\/stubmain.c.o/$OUT/build-fuzz/rfb_harness.o $OUT/build-fuzz/lsan_off.o}
LINK=${LINK//-o bin\/Xvnc/-o $SRC/rfb_server}
LINK=${LINK//-Xlinker --dependency-file=unix\/Xvnc\/programs\/Xserver\/CMakeFiles\/Xvnc.dir\/link.d/}
[[ $LINK == *rfb_harness.o* && $LINK == *"-o $SRC/rfb_server"* ]] || { echo "unexpected Xvnc link line: $LINK" >&2; exit 1; }
eval "$LINK"
test -x "$SRC/rfb_server"
