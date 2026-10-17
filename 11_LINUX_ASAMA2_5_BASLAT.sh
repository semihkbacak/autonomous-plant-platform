#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]];then echo 'Install first with 01_LINUX_KUR_TEST_VE_BASLAT.sh';exit 1;fi
exec .venv/bin/python -m desktop.full_simulator_launcher
