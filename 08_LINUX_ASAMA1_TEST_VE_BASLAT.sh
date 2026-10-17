#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ ! -x .venv/bin/python ]]; then
  echo "First install dependencies with: bash 01_LINUX_KUR_TEST_VE_BASLAT.sh" >&2
  exit 2
fi
.venv/bin/python -m pytest -q --assert=plain tests/test_stage1_three_plant_sync.py
.venv/bin/python -m desktop.full_simulator_launcher
