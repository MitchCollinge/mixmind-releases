#!/usr/bin/env bash
# Open/focus the MixMind desktop app while Ableton Live is running with the
# MixMind MIDI Remote Script (TCP command on port 65432).
# Usage: ./scripts/launch-mixmind-from-live.sh
set -euo pipefail
MSG='{"command":"open_mixmind","params":{}}'
if command -v nc >/dev/null 2>&1; then
  printf '%s\n' "$MSG" | nc -w 3 127.0.0.1 65432 || true
  exit 0
fi
echo "Install netcat (nc) or run: echo '$MSG' | nc 127.0.0.1 65432" >&2
exit 1
