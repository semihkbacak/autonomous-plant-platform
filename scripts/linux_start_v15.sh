#!/usr/bin/env bash
# Simulation-only runner (localhost). No PLC / SCADA command connection.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:---test-and-start}"
case "$MODE" in
  --test-and-start|--test-only|--skip-tests) ;;
  *) echo "Usage: bash scripts/linux_start_v15.sh [--test-and-start|--test-only|--skip-tests]" >&2; exit 2;;
esac
bash scripts/setup_linux_v15.sh
if [[ "$MODE" != "--skip-tests" ]]; then
  mkdir -p .linux_test_tmp
  .venv/bin/python -m pytest -q --assert=plain --tb=short --basetemp=.linux_test_tmp/pytest_run
fi
if [[ "$MODE" == "--test-only" ]]; then
  echo "All Linux regression tests passed."
  exit 0
fi
echo "Starting LOCAL simulation-only server on 127.0.0.1:8000"
exec .venv/bin/python -m tools.v15_launcher --mode SIMULATION --enable-local-sim-commands
