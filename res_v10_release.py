"""RES v1.0 software-only acceptance: scenario matrix, energy, regression, annual."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from simulator.wind_history import WindHistorian
from simulator.wind_suite import CASES, long_horizon, run_scenario


def create_matrix(path: Path) -> dict:
    path.mkdir(parents=True, exist_ok=True)
    db_path = path / 'wind_history.sqlite3'
    if db_path.exists():
        raise FileExistsError(f'Refusing to overwrite existing DB: {db_path}')
    history = WindHistorian(db_path)
    for scenario in CASES:
        rid = history.save_run(scenario, run_scenario(scenario))
        print(f'RES [{rid}/{len(CASES)}] {scenario}', flush=True)
    return history.audit(set(CASES))


def release(path: Path, *, annual_days: int = 0, regression: bool = False) -> dict:
    history = WindHistorian(path, read_only=True)
    audit = history.audit(set(CASES))
    annual = long_horizon(annual_days) if annual_days else {'status': 'NOT_RUN'}
    tests = {'status': 'NOT_RUN'}
    if regression:
        p = subprocess.run(
            [sys.executable, '-m', 'pytest', '-q', '--assert=plain'],
            text=True, capture_output=True, check=False,
        )
        tests = {'passed': p.returncode == 0, 'summary': (p.stdout + p.stderr).splitlines()[-12:]}
    accepted = audit['passed'] and annual.get('days') == 365 and annual.get('passed') is True and tests.get('passed') is True
    return {
        'release': 'RES_V1.0_SIMULATION_CANDIDATE',
        'scenario_audit': audit,
        'long_horizon': annual,
        'regression': tests,
        'software_acceptance_passed': bool(accepted),
        'oem_power_curve_calibrated': False,
        'wake_model_field_validated': False,
        'site_validation': False,
        'real_ot_control_enabled': False,
        'status': 'SIMULATOR_SOFTWARE_ACCEPTED_NOT_FIELD_VALIDATED' if accepted else 'CANDIDATE_INCOMPLETE',
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output', type=Path)
    group.add_argument('--existing-db', type=Path)
    parser.add_argument('--annual-days', type=int, default=0)
    parser.add_argument('--regression', action='store_true')
    args = parser.parse_args()
    if args.output:
        audit = create_matrix(args.output)
        db = args.output / 'wind_history.sqlite3'
    else:
        db = args.existing_db
    report = release(db, annual_days=args.annual_days, regression=args.regression)
    output = db.parent / 'res_v10_acceptance.json'
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print('Report:', output)
    return 0 if report['software_acceptance_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
