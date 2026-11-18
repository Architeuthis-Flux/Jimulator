#!/bin/sh
# SPDX-License-Identifier: MIT
# Builds the routing-lab harness against one firmware src/ tree.
#
#   build.sh <src_root> <out_binary>        SANITIZE=0 drops the sanitizers
#
# The firmware's routing sources are compiled through symlinks in the object
# directory (as test/test_routing_og/run.sh does), so the headers next to them
# (States.h, LEDs.h, ...) lose to harness/stubs in include order.
set -e
[ $# -eq 2 ] || { echo "usage: build.sh <src_root> <out_binary>" >&2; exit 2; }
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(cd "$1" && pwd)
OUT=$2
OBJ="$OUT.obj"
rm -rf "$OBJ"
mkdir -p "$OBJ" "$(dirname "$OUT")"

# The enum and bool checks are off: clearAllNTCC() memsets the path table to
# -1 by design, and the router reads pathType / skip of entries it has not
# assigned yet (NetsToChipConnections.cpp, the duplicate pass). Every case
# would abort on that. Everything else UBSan and ASan check stays on.
SAN="-fsanitize=address,undefined -fno-sanitize=enum,bool -fno-sanitize-recover=undefined -fno-omit-frame-pointer"
[ "$SANITIZE" = "0" ] && SAN=""
FLAGS="-std=c++17 -O1 -g $SAN -include config.h -I $HERE/stubs -I $SRC/routing -I $SRC -I $SRC/sensing"

# name:path pairs; firmware files under routing/ go through a symlink
UNITS="lab_harness:$HERE/lab_harness.cpp firmware_stubs:$HERE/firmware_stubs.cpp \
board:$SRC/boards/board.cpp board_og:$SRC/boards/og/board_og.cpp board_v5:$SRC/boards/v5/board_v5.cpp"
for f in NetsToChipConnections MatrixState NetManager RouteSafety InfraPaths; do
    ln -sf "$SRC/routing/$f.cpp" "$OBJ/fw_$f.cpp"
    UNITS="$UNITS fw_$f:$OBJ/fw_$f.cpp"
done

PIDS=""
for u in $UNITS; do
    name=${u%%:*}; path=${u#*:}
    # shellcheck disable=SC2086
    g++ $FLAGS -c "$path" -o "$OBJ/$name.o" 2> "$OBJ/$name.err" &
    PIDS="$PIDS $!"
done
FAIL=0
for p in $PIDS; do wait "$p" || FAIL=1; done
if [ $FAIL -ne 0 ]; then
    cat "$OBJ"/*.err >&2
    exit 1
fi
# shellcheck disable=SC2086
g++ $SAN -o "$OUT" "$OBJ"/*.o 2> "$OBJ/link.err" || { cat "$OBJ/link.err" >&2; exit 1; }
