"""Offline fail-closed safety/packaging invariants. Not a SAST or pen test."""
from __future__ import annotations
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from desktop.full_simulator_launcher import self_test
from research_v2.api import capabilities


def run():
    assert self_test()['physical_control'] is False
    assert capabilities()['field_control_authorized'] is False
    assert capabilities()['real_control_ready'] is False
    from app.site_readiness import readiness_report
    r=readiness_report()
    assert r['real_control_authorized'] is False
    assert r['can_connect_to_real_equipment'] is False
    assert r['unverified_gates']==10
    assert '127.0.0.1' in (ROOT/'desktop/full_simulator_launcher.py').read_text(encoding='utf-8')
    assert 'host=\'127.0.0.1\'' in (ROOT/'desktop/full_simulator_launcher.py').read_text(encoding='utf-8')
    for file in ['README.md','docs/V20_DELIVERY_AND_LIMITATIONS_TR.md']:
        assert (ROOT/file).is_file()
    print('SIMULATION / SHADOW invariant checks PASS; this is NOT an OT penetration test.')
if __name__=='__main__':run()
