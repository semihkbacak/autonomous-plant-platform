#!/usr/bin/env bash
# Read-only advisory audit: never stages, commits or pushes.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
echo '--- Git current branch/remotes ---'
git rev-parse --show-toplevel 2>/dev/null || true
git branch --show-current 2>/dev/null || true
git remote -v 2>/dev/null || true
echo '--- Untracked/modified sources (review!) ---'
git status --short 2>/dev/null || true
echo '--- Possible local files requiring exclusion (names only; do not upload) ---'
find . -type f \( -name '*.sqlite3' -o -name '.env' -o -name '*.pem' -o -name '*.key' -o -name '*credentials*' \) \
    -not -path './.venv/*' -not -path './.git/*' -print | head -80
echo 'AUDIT FINISHED — NO GIT CHANGES MADE'
