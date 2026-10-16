#!/usr/bin/env bash
# Local synthetic simulator setup, never connect to OT equipment.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert (3,12) <= sys.version_info[:2] < (3,15), "Require Python 3.12–3.14; 3.13 is verified"'
if [[ -d .venv && ! -x .venv/bin/python ]]; then
  backup=".venv_otheros_backup_$(date +%Y%m%d_%H%M%S)"
  mv .venv "$backup"
  echo "Saved cross-OS/invalid virtualenv as: $backup"
fi
if [[ ! -x .venv/bin/python ]]; then
  "$PYTHON" -m venv .venv
fi
# Always synchronize requirements to avoid loading a model trained with a different sklearn version.
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m desktop.viewer_entry_v15 --self-test
echo "Linux environment OK. Default launcher is read-only SHADOW."
