#!/usr/bin/env bash
# Launch MixMind from Terminal (starts Electron + Python bridge).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ ! -d node_modules ]]; then
  echo "Installing npm dependencies…"
  npm install
fi

exec npm start
