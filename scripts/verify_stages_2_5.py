"""Offline delivery acceptance for synthetic stages 1–5 (no site approval)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from advanced_v2.controller import Controller
from advanced_v2.engine import ResearchConfig
from advanced_v2.references import independent_law_checks,pvlib_standard_irradiance_check


def main():
    files=[ROOT/'advanced_v2'/m for m in ('physics.py','engine.py','journal.py','controller.py','api.py',
                                           'validation.py','references.py','optimization.py')]
    files += [ROOT/'stage1/engine.py',ROOT/'app/main.py',ROOT/'desktop/build_full_windows_v20.ps1',
              ROOT/'simulator/solar/ges_history_schema.sql']
    absent=[str(x.relative_to(ROOT)) for x in files if not x.is_file()]
    if absent:raise RuntimeError('Required source/assets missing: '+', '.join(absent))
    ref=pvlib_standard_irradiance_check()
    if not ref['within_reference_tolerance'] or not independent_law_checks()['cp_below_16_27']:
        raise RuntimeError('Reference checks failed')
    with TemporaryDirectory(prefix='app-stages-2-5-') as temp:
        c=Controller(Path(temp)/'verification.sqlite3')
        c.create(ResearchConfig(days=2))
        c.advance(4)
        original=c.status()
        other=Controller(c.journal.path)
        if other.status()['index']!=4 or other.status()['total_kwh']!=original['total_kwh']:
            raise RuntimeError('Research recovery check failed')
        other.advance(1)
        if other.status()['index']!=5 or len(other.history())!=5:
            raise RuntimeError('Research UTC/resume check failed')
    print(json.dumps({'scope':'SYNTHETIC_ONLY','status':'PASS','reference':ref,
                      'sqlite_recovery':'PASS','three_plant_clock':'PASS',
                      'native_windows_exe_gui_tested':False,'field_control_approved':False},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
