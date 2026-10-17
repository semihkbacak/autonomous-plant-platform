#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]];then echo 'Install first with 01_LINUX_KUR_TEST_VE_BASLAT.sh';exit 1;fi
export APP_OPERATION_MODE=SIMULATION PYTHONDONTWRITEBYTECODE=1
mkdir -p .linux_test_tmp
.venv/bin/python -m pytest -q --assert=plain --tb=short --basetemp=.linux_test_tmp/stages_2_5 tests
.venv/bin/python scripts/verify_stages_2_5.py
