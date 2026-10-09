#!/usr/bin/env bash
# LeadScout launcher for Linux (and macOS via start.command).
# First run: creates a private Python environment and installs LeadScout.
# Every run: opens the dashboard in your browser.
set -euo pipefail
cd "$(dirname "$0")"

pause() { read -r -p "Press Enter to close this window..." _ || true; }

PY=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1 && "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PY="$cmd"; break
  fi
done
if [ -z "$PY" ]; then
  echo "LeadScout needs Python 3.10 or newer."
  echo "Download it from https://www.python.org/downloads/ , install it, then run this file again."
  pause; exit 1
fi

if [ ! -x .venv/bin/leadscout ]; then
  echo "First run: setting up LeadScout (this takes a minute)..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install --upgrade pip >/dev/null
  if ! .venv/bin/python -m pip install -e ".[web,packs]"; then
    echo "Installing LeadScout failed. Check your internet connection and try again."
    rm -rf .venv
    pause; exit 1
  fi
fi

[ -f campaign.yaml ] || .venv/bin/leadscout init

echo "Starting LeadScout. Keep this window open while you use it; close it to stop."
.venv/bin/leadscout web --open || { echo "LeadScout stopped with an error (see above)."; pause; exit 1; }
