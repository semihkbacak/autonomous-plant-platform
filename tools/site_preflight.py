"""Local preflight diagnostics and strict honesty report (no field approval)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from datetime import datetime, timezone


def preflight(root: str | Path = '.') -> dict:
    root = Path(root).resolve()
    checks = []
    for relative in (
        'app/main.py', 'app/sim_runtime.py', 'simulator/hydro.py',
        'simulator/wind_physics.py', 'simulator/solar/ges_integrated.py',
        'app/site_shadow.py', 'app/site_readiness.py',
    ):
        checks.append({'name': 'SOURCE:' + relative, 'passed': (root/relative).is_file()})
    for pkg in ('fastapi', 'pydantic', 'pytest', 'pvlib', 'sklearn'):
        checks.append({'name': 'DEPENDENCY:' + pkg, 'passed': importlib.util.find_spec(pkg) is not None})
    mode = os.getenv('APP_OPERATION_MODE', 'SIMULATION').upper()
    checks.append({'name': 'KNOWN_NON_OT_OPERATION_MODE', 'passed': mode in ('SIMULATION', 'SHADOW')})
    checks.append({'name': 'SHADOW_HAS_NO_LOCAL_COMMANDS', 'passed': (mode != 'SHADOW' or os.getenv('APP_SIM_CONSOLE_WRITES') != '1')})
    checks.append({'name': 'LEGACY_MUTATION_ROUTES_BLOCKED', 'passed': os.getenv('APP_HARDEN_LEGACY') == '1'})
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(),
            'scope': 'LOCAL_SOFTWARE_PREFLIGHT_NOT_SITE_APPROVAL',
            'checks': checks,
            'software_environment_passed': all(item['passed'] for item in checks),
            'real_site_ready': False, 'real_control_authorized': False,
            'windows_exe_field_validated': False,
            'note': 'This does not validate OEM calibration, PLC protection, SAT or field connectivity.'}


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',type=Path,default=Path('.'))
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    body=preflight(args.project)
    contents=json.dumps(body,ensure_ascii=False,indent=2)
    print(contents)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(contents+'\n',encoding='utf-8')
    if not body['software_environment_passed']:
        raise SystemExit(2)


if __name__=='__main__':
    main()
