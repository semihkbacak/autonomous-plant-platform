#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then echo "Once kurulum betigini calistirin"; exit 1; fi
.venv/bin/python -m desktop.full_simulator_launcher
