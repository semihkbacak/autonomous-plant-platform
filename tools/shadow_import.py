"""Offline ingestion CLI; uses no OT/network APIs.

Example: python -m tools.shadow_import --csv offline.csv --db ~/.local/state/autonomous-plant-platform/offline_shadow.sqlite3
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from app.site_shadow import ShadowStore


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--csv', type=Path, required=True)
    p.add_argument('--db', type=Path, default=Path.home()/'.local/state/autonomous-plant-platform/offline_shadow.sqlite3')
    args = p.parse_args()
    print(json.dumps(ShadowStore(args.db).import_csv(args.csv), indent=2))
    print('Offline CSV only. No field provenance or command access validated.')


if __name__ == '__main__':
    main()
