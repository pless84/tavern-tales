#!/usr/bin/env bash
# Run every check: unit tests, Ren'Py lint, and the Ren'Py test suite against a mock LLM.
# The Ren'Py tests run on a temporary copy of the project with its own save folder,
# so your real saves, settings and character cards are never touched.
#
# Usage: bash tools/check.sh [testcase-or-suite]
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RENPY="${RENPY:-$HOME/Games/renpy-8.5.3-sdk/renpy.sh}"
PORT="${TT_MOCK_PORT:-8799}"
TARGET="${1:-}"
FAIL=0

step() { printf '\n== %s\n' "$*"; }

step "unit tests"
for t in "$ROOT"/tools/test_*.py; do
    python3 -B "$t" || { echo "FAILED: $t"; FAIL=1; }
done

step "lint"
LINT="$("$RENPY" "$ROOT" lint 2>&1)"; LRC=$?
if [ $LRC -ne 0 ] || ! grep -q "lint report" <<<"$LINT" || grep -qE '^game/.*:[0-9]+|[Ee]rror|Exception' <<<"$LINT"; then
    echo "$LINT"; echo "FAILED: lint"; FAIL=1
else
    echo "lint clean"
fi

step "ren'py tests"
TMP="$(mktemp -d)" || { echo "mktemp failed"; exit 1; }
cleanup() {
    [ -n "${MOCK_PID:-}" ] && kill "$MOCK_PID" 2>/dev/null
    rm -rf "${TMP:?}"
}
trap cleanup EXIT

PROJ="$TMP/proj"
mkdir -p "$PROJ/characters" "$TMP/saves"
cp -r "$ROOT/game" "$PROJ/game"
rm -rf "$PROJ/game/saves" "$PROJ/game/cache"
# Sample cards only (never the user's own cards).
for f in Mira.png Rook.json Rook.png; do cp "$ROOT/characters/$f" "$PROJ/characters/" || { echo "missing sample card $f"; exit 1; }; done
[ -d "$ROOT/characters/Mira" ] && cp -r "$ROOT/characters/Mira" "$PROJ/characters/"
[ -d "$ROOT/tools/fixtures" ] && cp -r "$ROOT/tools/fixtures" "$TMP/fixtures"

if curl -s "http://127.0.0.1:$PORT/v1/models" >/dev/null 2>&1; then
    echo "port $PORT is already in use (stale mock?); set TT_MOCK_PORT"; exit 1
fi
python3 -B "$ROOT/tools/mock_llm.py" "$PORT" >"$TMP/mock.log" 2>&1 &
MOCK_PID=$!
for _ in $(seq 50); do curl -s "http://127.0.0.1:$PORT/v1/models" >/dev/null && break; sleep 0.1; done
kill -0 "$MOCK_PID" 2>/dev/null || { echo "mock server failed to start"; cat "$TMP/mock.log"; exit 1; }

export TT_MOCK_URL="http://127.0.0.1:$PORT" TT_NO_ST_DETECT=1 TT_TEST_ROOT="$PROJ" TT_FIXTURES="$TMP/fixtures"
mkdir -p "$ROOT/tests/screenshots"
find "$ROOT/tests/screenshots" -maxdepth 1 -name "*.png" -delete
timeout 480 "$RENPY" "$PROJ" --savedir "$TMP/saves" test $TARGET --hide-header --report-detailed >"$ROOT/tests/last_test.out" 2>&1
RC=$?
[ -d "$PROJ/tests/screenshots" ] && cp -r "$PROJ/tests/screenshots/." "$ROOT/tests/screenshots/"
grep -vE '^(Display|Screen sizes|Maximum texture)' "$ROOT/tests/last_test.out" | tail -40
if [ -f "$PROJ/traceback.txt" ]; then
    echo "--- traceback.txt"; head -40 "$PROJ/traceback.txt"; FAIL=1
fi
if [ $RC -ne 0 ] || ! grep -q "Status: PASSED" "$ROOT/tests/last_test.out"; then
    echo "FAILED: ren'py tests (exit $RC)"; FAIL=1
fi

step "result"
if [ $FAIL -eq 0 ]; then echo "ALL CHECKS PASSED"; else echo "SOME CHECKS FAILED"; fi
exit $FAIL
