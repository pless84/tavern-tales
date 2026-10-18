#!/bin/sh
# Launch Tavern Tales with the Ren'Py SDK ($RENPY_SDK, default ~/Games/renpy-8.5.3-sdk).
# Falls back to the Ren'Py 8.5 runtime bundled with Summertime Saga 21.
# Extra args pass through, e.g. ./run.sh lint
HERE="$(cd "$(dirname "$0")" && pwd)"
RENPY_SDK="${RENPY_SDK:-$HOME/Games/renpy-8.5.3-sdk}"
if [ -x "$RENPY_SDK/renpy.sh" ]; then
    exec "$RENPY_SDK/renpy.sh" "$HERE" "${@:-run}"
fi
RT="$HOME/Games/summertimesaga-21.0.0-wip.8194-pc/lib/py3-linux-x86_64/summertimesaga"
[ -x "$RT" ] || { echo "No Ren'Py runtime found. Install the Ren'Py SDK and set RENPY_SDK."; exit 1; }
exec "$RT" "$HERE" "${@:-run}"
