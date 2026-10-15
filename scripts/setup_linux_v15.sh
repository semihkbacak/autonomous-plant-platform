#!/usr/bin/env bash
# Run only in an intentionally trusted clone of this simulator project.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ ! -f requirements.txt || ! -f app/main.py ]]; then
  echo "ERROR: Run from a complete Autonomous Plant Platform project" >&2
  exit 2
fi
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert (3,12) <= sys.version_info[:2] < (3,15), "Use Python 3.12–3.14"'
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
if ! .venv/bin/python -c 'import fastapi, uvicorn, pvlib, sklearn, pydantic' 2>/dev/null; then
  echo "Dependencies missing; installing from requirements.txt (internet may be required)"
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python -m desktop.viewer_entry_v15 --self-test
echo "SETUP OK — local read-only SHADOW startup:"
echo "  .venv/bin/python -m tools.v15_launcher"
echo "For local-only simulations:"
echo "  .venv/bin/python -m tools.v15_launcher --mode SIMULATION --enable-local-sim-commands"
