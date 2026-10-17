"""Create a clearly labelled SYNTHETIC GES historian for the local dashboard.

The dashboard is historian-backed. It cannot show a graph until there are saved
simulation runs. This script creates an explicit repeatable sample from the
repository's synthetic CSV and never connects to a real energy plant.

Existing databases are NOT overwritten; a custom GES_HISTORIAN_DB is respected.
"""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELATIVE_DEFAULT = Path('outputs/ges_v20_synthetic_demo/historian.sqlite3')


def default_history_path(root: Path = ROOT) -> Path:
    return root / RELATIVE_DEFAULT


def inspect_history(path: str | Path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f'GES demo historian missing: {path}')
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)) as db:
        quick_check = db.execute('PRAGMA quick_check').fetchone()[0]
        if quick_check != 'ok':
            raise RuntimeError('Existing historian failed SQLite quick_check')
        runs = db.execute('SELECT COUNT(*) FROM simulation_runs').fetchone()[0]
        samples = db.execute('SELECT COUNT(*) FROM production_intervals').fetchone()[0]
        mppt = db.execute('SELECT COUNT(*) FROM ges_mppt_intervals').fetchone()[0]
        pq = db.execute('SELECT COUNT(*) FROM ges_pq_intervals').fetchone()[0]
    if min(runs, samples, mppt, pq) < 1:
        raise RuntimeError('Existing historian is incomplete; will not overwrite it')
    return {'path': str(path.resolve()), 'runs': runs, 'intervals': samples,
            'mppt_intervals': mppt, 'pq_intervals': pq, 'scope': 'SYNTHETIC_OFFLINE_DEMO_ONLY'}


def ensure_synthetic_ges_history(path: str | Path | None = None, *, root: Path = ROOT) -> dict:
    """Create once, validate on later starts; never overwrite user's data."""
    path = Path(path) if path is not None else default_history_path(root)
    if path.exists():
        return inspect_history(path)

    from demo_ges_integrated_v04 import build_integrated_demo_pipeline, build_integrated_snapshots
    from simulator.solar.historian import SolarHistorian
    from simulator.solar.solar_timeseries import SolarTimeSeriesSimulator, SolarIntervalInput
    from simulator.solar.weather_io import load_weather_intervals_csv
    from simulator.solar.pq_dispatch import PQCapability

    rows = load_weather_intervals_csv(root / 'data/solar/demo_weather_15m.csv')
    pipeline = build_integrated_demo_pipeline()
    simulator = SolarTimeSeriesSimulator(pipeline)
    pq = {iid: PQCapability(10.0, 10.0) for iid in pipeline.inverter_ids}
    q = {iid: 8.0 for iid in pipeline.inverter_ids}
    for index, row in enumerate(rows):
        simulator.step(SolarIntervalInput(
            start_utc=row.start_utc, end_utc=row.end_utc, weather=row.weather,
            grid_available=index != 2,
            pq_capabilities=pq, reactive_requests_kvar=q,
        ))
    # Build into a sibling temp location; publish only when fully formed.
    import os
    import uuid
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + '_incomplete_' + uuid.uuid4().hex + '.sqlite3')
    try:
        writer = SolarHistorian(tmp)
        writer.save_simulation(simulator,
                               scenario='SYNTHETIC_GES_V20_DEMO_NO_OT',
                               inverter_snapshot_payloads=build_integrated_snapshots(pipeline))
        inspect_history(tmp)
        # Avoid touching an existing database if a concurrent launcher won the race.
        if path.exists():
            return inspect_history(path)
        os.replace(tmp, path)
        return inspect_history(path)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=None, help='Output .sqlite3 (never overwrite)')
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args(argv)
    report = (inspect_history(args.db or default_history_path()) if args.check_only
              else ensure_synthetic_ges_history(args.db))
    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
