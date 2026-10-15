"""24-hour, mode-by-mode test of EXISTING GES/RES simulator physics engines.

Actual physics dependencies (including pvlib for GES) are required.
One 96-step virtual day is checked per mode. It is NOT OEM or field validation.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from app.sim_runtime import MODES, SimulatorSessions


def evaluate(plant: str, mode: str) -> dict:
    if plant not in MODES or mode not in MODES[plant]:
        raise ValueError('Unknown scenario')
    sessions=SimulatorSessions()
    session=sessions.session(plant)
    session.configure(mode)
    try:
        session.start()
        observed=[]
        for _ in range(96):
            state=session.step()
            observed.append(state['last_power_kw'])
        valid=(state['intervals']==96 and not state['running'] and
               state['error'] is None and state['energy_kwh']>=0 and
               math.isclose(state['energy_kwh'],math.fsum(observed)*.25,rel_tol=2e-6,abs_tol=1e-4) and
               all(math.isfinite(x) and x>=0 for x in observed))
        if mode in ('GRID_LOSS','ESTOP'):
            valid=valid and all(x==0 for x in observed)
        if plant=='res' and mode in ('LOW_WIND','HIGH_WIND'):
            valid=valid and all(x==0 for x in observed)
        return {'plant':plant.upper(),'scenario':mode,'passed':bool(valid),
                'steps':state['intervals'],'energy_kwh':state['energy_kwh'],
                'peak_kw':max(observed),'units':len(state['units']),
                'source_kind':'SYNTHETIC_15MIN_VIRTUAL_DAY_NOT_OEM_FIELD_TEST'}
    except Exception as exc:
        return {'plant':plant.upper(),'scenario':mode,'passed':False,
                'reason':type(exc).__name__,
                'source_kind':'SYNTHETIC_SCENARIO_FAILED'}


def run(plant: str = 'both') -> dict:
    selected=('ges','res') if plant=='both' else (plant,)
    if any(p not in MODES for p in selected):
        raise ValueError('Unknown plant')
    cases=[evaluate(p,mode) for p in selected for mode in MODES[p]]
    return {'scope':'LOCAL_SIMULATION_DAY_ACCEPTANCE_NO_FIELD_VALIDATION',
            'timestamp_utc':datetime.now(timezone.utc).isoformat(),
            'passed':all(x['passed'] for x in cases),
            'cases':cases,'case_count':len(cases),
            'oem_calibration':False, 'remote_control_authorized':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plant',choices=('ges','res','both'),default='both')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report=run(args.plant)
    data=json.dumps(report,ensure_ascii=False,indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(data+'\n',encoding='utf-8')
    print(data)
    if not report['passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
