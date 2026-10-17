#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 scripts/release/publish_rc1.py --dry-run
