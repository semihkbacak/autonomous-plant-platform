"""Cross-platform scheduler / controls / journal / rollback / runtime regression.

No pvlib dependency; native HES simulator and deterministic GES/RES fixtures.
"""
from __future__ import annotations
import json
from datetime import timedelta
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import MethodType

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.sim_runtime import SolarSession, WindSession
from stage1.controller import Coordinator
from stage1.engine import ClockConfig
from stage1.api import create_router
from stage1.dispatch import power_kw
from tools.audit_repair_backup import backup_files

START='2026-01-01T00:00:00+00:00'
QUARTER='2026-01-01T00:15:00+00:00'
HOUR='2026-01-01T01:00:00+00:00'
NEXT_DAY='2026-01-02T00:00:00+00:00'

class FakeSolar(SolarSession):
    def _prepare(self):self._engine=object()
    def _compute(self,i):
        return {'power_kw':20.0,'energy_kwh':5.0,'end_utc':START,
                'units':[{'id':'INV_1','kw':20.0,'status':'SYNTHETIC'}],
                'conditions':{'irradiance_ghi_w_m2':600,'source':'DETERMINISTIC_TEST'}}

class FakeWind(WindSession):
    def _prepare(self):self._engine=object()
    def _compute(self,i):
        return {'power_kw':80.0,'energy_kwh':20.0,'end_utc':START,
                'units':[{'id':'WT_1','kw':80.0,'status':'SYNTHETIC'}],
                'conditions':{'wind_speed_m_s':8,'source':'DETERMINISTIC_TEST'}}

class NoSolar(FakeSolar):
    def _compute(self,i):
        d=super()._compute(i);d['power_kw']=d['energy_kwh']=0.0;d['units'][0]['kw']=0.0;return d

class NoWind(FakeWind):
    def _compute(self,i):
        d=super()._compute(i);d['power_kw']=d['energy_kwh']=0.0;d['units'][0]['kw']=0.0;return d

def coordinator(tmp_path,solar=FakeSolar,wind=FakeWind):
    c=Coordinator(tmp_path/'clock.sqlite3',solar,wind)
    c.create(ClockConfig(START,2))
    return c

def test_hourly_daily_quarter_hour_targets_and_overlap(tmp_path):
    c=coordinator(tmp_path)
    c.add_plan('HES',START,QUARTER,0,15)
    c.add_plan('GES',START,HOUR,10,60)
    c.add_plan('RES',START,NEXT_DAY,30,1440)
    assert len(c.journal.plans(c.run_id))==3
    with pytest.raises(ValueError,match='Overlapping'):
        c.add_plan('GES',START,QUARTER,9,15)
    assert c.journal.audit_events(c.run_id)[0]['kind']=='PLAN_REJECTED'
    a=c.advance()['latest']
    assert a['HES']['power_kw']==0
    assert a['HES']['conditions']['dispatch']['native_available_kw']>=0
    assert a['GES']['power_kw']==10 and a['GES']['energy_kwh']==2.5
    assert a['RES']['power_kw']==30 and a['RES']['energy_kwh']==7.5
    assert a['RES']['conditions']['dispatch']['deviation_kwh']==0
    assert c.status()['total_kwh']['GES']==2.5
    rep=c.journal.plan_report(c.run_id,c.status()['utc'])
    ges=next(r for r in rep if r['plant']=='GES')
    assert ges['expected_kwh']==10 and ges['actual_kwh']==2.5
    assert ges['elapsed_expected_kwh']==2.5 and ges['deviation_elapsed_kwh']==0
    with pytest.raises(ValueError,match='Past'):
        c.add_plan('HES',START,QUARTER,1,15)


def test_no_physical_resource_is_never_fabricated(tmp_path):
    c=coordinator(tmp_path,NoSolar,NoWind)
    c.add_plan('GES',START,QUARTER,100,15)
    c.add_plan('RES',START,QUARTER,100,15)
    out=c.advance()['latest']
    for p in ('GES','RES'):
        assert out[p]['power_kw']==out[p]['energy_kwh']==0
        assert out[p]['conditions']['dispatch']['reason']=='PHYSICAL_AVAILABILITY_LIMIT'
        assert out[p]['conditions']['dispatch']['deviation_kwh']==-25
    assert out['HES']['power_kw']>0  # legacy unscheduled HES unaffected


def test_manual_start_stop_override_and_audit(tmp_path):
    c=coordinator(tmp_path)
    c.add_plan('GES',START,QUARTER,15,15)
    c.manual_setpoint('GES',3)
    c.operator_command('GES','STOP')
    assert c.advance()['latest']['GES']['energy_kwh']==0
    c.operator_command('GES','AUTO')
    c.advance()
    assert c.status()['latest']['GES']['power_kw']==3
    c.manual_setpoint('GES',None)
    assert c.status()['dispatch']['GES']['target_kw']==0
    with pytest.raises(ValueError,match='START denied'):
        c.operator_command('GES','START')
    assert c.journal.audit_events(c.run_id)[0]['kind']=='COMMAND_REJECTED'
    c.operator_command('RES','START')  # no schedule: preserve opt-in legacy operation
    assert c.status()['dispatch']['RES']['operation']=='START'


def test_past_plan_removal_rejected_and_future_removed(tmp_path):
    c=coordinator(tmp_path)
    c.add_plan('HES',START,QUARTER,100,15)
    c.add_plan('HES',QUARTER,'2026-01-01T00:30:00+00:00',200,15)
    a,b=c.journal.plans(c.run_id)
    c.advance()
    with pytest.raises(ValueError,match='future'):
        c.remove_plan(a['id'])
    c.remove_plan(b['id'])
    assert len(c.journal.plans(c.run_id))==1
    assert c.journal.audit_events(c.run_id)[0]['kind']=='PLAN_REMOVED'


def test_setpoint_bounds_and_utc_validation(tmp_path):
    c=coordinator(tmp_path)
    for bad in (-1,float('nan'),float('inf'),40000,True):
        with pytest.raises(ValueError):c.manual_setpoint('HES',bad)
    for start,end,mins in [(START,QUARTER,60),('2026-01-01T03:00:00+03:00',QUARTER,15),
                            ('2026-01-01T00:05:00Z',QUARTER,15),(NEXT_DAY,START,15)]:
        with pytest.raises(ValueError):c.add_plan('HES',start,end,100,mins)
    assert power_kw(30_000,'HES')==30_000


def test_restart_dispatch_totals_audit_chain_and_corruption(tmp_path):
    c=coordinator(tmp_path)
    c.add_plan('GES',START,HOUR,5,60)
    c.manual_setpoint('RES',2)
    c.advance(2)
    expected=c.status()['total_kwh']
    d=Coordinator(c.journal.path,FakeSolar,FakeWind)
    assert d.status()['total_kwh']==expected
    assert d.status()['dispatch']['GES']['target_kw']==5
    d.advance()
    assert d.status()['latest']['GES']['power_kw']==5
    with sqlite3.connect(c.journal.path) as con:
        con.execute("UPDATE dispatch_audit SET payload_json='{}' WHERE id=1") if False else None
        # An append-only trigger is present, even for privileged sqlite connections.
        with pytest.raises(sqlite3.DatabaseError,match='append-only'):
            con.execute("DELETE FROM dispatch_audit WHERE id=1")
        con.execute('DROP TRIGGER dispatch_audit_immutable_update')
        con.execute("UPDATE dispatch_audit SET payload_json='{}' WHERE id=1")
    with pytest.raises(ValueError,match='audit chain'):
        Coordinator(c.journal.path,FakeSolar,FakeWind)


def test_slot_sqlite_failure_still_rewinds_to_last_commit(tmp_path,monkeypatch):
    c=coordinator(tmp_path)
    c.manual_setpoint('GES',4)
    c.advance()
    saved=c.status()['total_kwh']
    def fail(*a,**kw):raise sqlite3.OperationalError('disk failure injected')
    monkeypatch.setattr(c.journal,'advance',fail)
    with pytest.raises(sqlite3.OperationalError):c.advance()
    assert c.state=='FAULT_LATCHED'
    d=Coordinator(c.journal.path,FakeSolar,FakeWind)
    assert d.status()['total_kwh']==saved
    assert len(d.export_rows())==3
    d.advance()
    assert len(d.export_rows())==6


def test_fresh_corrupt_checkpoint_refuses_resume(tmp_path):
    c=coordinator(tmp_path);c.advance()
    with sqlite3.connect(c.journal.path) as con:
        con.execute("UPDATE runs SET checkpoint=X'0BAD' WHERE id=?",(c.run_id,))
    with pytest.raises(ValueError,match='Damaged run metadata'):
        Coordinator(c.journal.path,FakeSolar,FakeWind)


def test_speed_modes_profile_and_no_sleep(tmp_path):
    c=coordinator(tmp_path)
    assert c.status()['speed_mode']=='NORMAL'
    c.set_speed('MAX')
    assert c.status()['speed_mode']=='MAX'
    c.advance()
    assert c.profile['steps']==1
    assert c.profile['compute_s']>0 and c.profile['journal_s']>=0
    with pytest.raises(ValueError):c.set_speed('UNSAFE_INFINITE')
    c.pause();c.start()
    c.auto_step()
    assert c.status()['index']==5  # MAX => +4 native slots without sleep


def test_api_protected_and_operational(tmp_path,monkeypatch):
    c=coordinator(tmp_path)
    monkeypatch.setenv('APP_OPERATION_MODE','SIMULATION')
    app=FastAPI();app.include_router(create_router(c))
    with TestClient(app) as client:
        r=client.post('/api/v2/clock/setpoint',json={'plant':'HES','kw':100})
        assert r.status_code==403
        h={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'}
        r=client.post('/api/v2/clock/plan',headers=h,json={'plant':'GES','start_utc':START,'end_utc':QUARTER,'interval_minutes':15,'target_kw':10})
        assert r.status_code==200,r.text
        r=client.post('/api/v2/clock/setpoint',headers=h,json={'plant':'GES','kw':5})
        assert r.status_code==200
        r=client.post('/api/v2/clock/step',headers=h,json={'count':1})
        assert r.status_code==200 and r.json()['latest']['GES']['power_kw']==5
        assert client.get('/api/v2/clock/plans').json()['entries']
        assert client.get('/api/v2/clock/dispatch-audit').json()['events']
        rep=client.get('/api/v2/clock/plan-report').json()['report']
        assert rep[0]['actual_kwh']==1.25
        csv_result=client.get('/api/v2/clock/export.csv')
        assert 'requested_kw' in csv_result.text and 'deviation_kwh' in csv_result.text
        panel=client.get('/platform/synchronized').text
        assert 'pPlans' in panel and 'pSpeed' in panel and 'Fizik girdileri' in panel


def test_legacy_windows_backup_discovery_isolated(tmp_path):
    root=tmp_path/'research';(root/'tests').mkdir(parents=True)
    (root/'pytest.ini').write_text((Path(__file__).parent.parent/'pytest.ini').read_text(encoding='utf-8'), encoding='utf-8')
    (root/'tests'/'test_duplicate.py').write_text('def test_unique(): assert True\n', encoding='utf-8')
    old=root/'_WINDOWS_AUDIT_ONAR_YEDEK'/'20261016T230057Z'/'tests'
    old.mkdir(parents=True)
    (old/'test_duplicate.py').write_text('def test_unique(): assert False\n', encoding='utf-8')
    result=subprocess.run([sys.executable,'-m','pytest','-q','--collect-only'],cwd=root,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr
    assert result.stdout.count('test_duplicate.py::test_unique')==1
    result=subprocess.run([sys.executable,'-m','pytest','-q'],cwd=root,
                          capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def test_repair_backup_is_outside_root_and_keeps_bytes(tmp_path):
    root=tmp_path/'source';root.mkdir();(root/'tests').mkdir()
    (root/'tests'/'test_plant.py').write_bytes(b'def test_x(): assert True\r\n')
    with pytest.raises(ValueError,match='OUTSIDE'):
        backup_files(['tests/test_plant.py'],root=root,dest=root/'repair')
    out=backup_files(['tests/test_plant.py'],root=root)
    assert root not in out.parents
    assert (out/'tests'/'test_plant.py').read_bytes()==(root/'tests'/'test_plant.py').read_bytes()
    assert 'tests/test_plant.py' in json.loads((out/'MANIFEST_SHA256.json').read_text(encoding='utf-8'))


def test_resource_interlock_rejects_even_buggy_native_output():
    from stage1.dispatch import dispatch_row
    for plant,conditions,reason in (
        ('GES',{'irradiance_ghi_w_m2':0},'NO_SOLAR_IRRADIANCE'),
        ('RES',{'wind_speed_m_s':1.0},'WIND_OUTSIDE_SYNTHETIC_CUT_IN_OUT'),
        ('RES',{'wind_speed_m_s':30.0},'WIND_OUTSIDE_SYNTHETIC_CUT_IN_OUT'),
        ('HES',{'net_head_m':0,'flow_m3_s':1},'INSUFFICIENT_HYDRAULIC_RESOURCE')):
        row={'plant':plant,'power_kw':100,'energy_kwh':25,
             'units':[{'id':'X','kw':100}],'conditions':conditions}
        out=dispatch_row(row,{'target_kw':50,'manual_kw':None,'operation':'AUTO','plan_id':1})
        assert out['power_kw']==out['energy_kwh']==0
        assert out['conditions']['dispatch']['reason']==reason


def test_safety_scenario_blocks_start_even_if_plan_positive(tmp_path):
    c=coordinator(tmp_path)
    c.add_plan('GES',START,QUARTER,10,15)
    c.set_mode('GES','ESTOP')
    with pytest.raises(ValueError,match='blocked'):
        c.operator_command('GES','START')
    assert c.journal.audit_events(c.run_id)[0]['kind']=='COMMAND_REJECTED'


def test_manual_validation_rejection_is_audited(tmp_path):
    c=coordinator(tmp_path)
    with pytest.raises(ValueError): c.manual_setpoint('HES',float('inf'))
    r=c.journal.audit_events(c.run_id)
    assert r[0]['kind']=='COMMAND_REJECTED'
    assert c.status()['dispatch']['HES']['manual_kw'] is None


def test_mid_transaction_sqlite_abort_is_atomic(tmp_path):
    c=coordinator(tmp_path)
    c.add_plan('GES',START,QUARTER,100,15)  # available is 20 => DISPATCH_LIMITED audit event
    original_audit=len(c.journal.audit_events(c.run_id))
    with sqlite3.connect(c.journal.path) as con:
        con.execute('''CREATE TRIGGER fail_res_slot BEFORE INSERT ON samples
                       WHEN NEW.plant='RES'
                       BEGIN SELECT RAISE(ABORT,'synthetic-fail-third-record'); END''')
    with pytest.raises(sqlite3.IntegrityError,match='synthetic-fail-third-record'):
        c.advance(1)
    with sqlite3.connect(c.journal.path) as con:
        assert con.execute('SELECT COUNT(*) FROM samples').fetchone()[0]==0
        assert con.execute('SELECT step_index FROM runs WHERE id=?',(c.run_id,)).fetchone()[0]==0
        assert con.execute('SELECT COUNT(*) FROM dispatch_audit').fetchone()[0]==original_audit
        con.execute('DROP TRIGGER fail_res_slot')
    recovered=Coordinator(c.journal.path,FakeSolar,FakeWind)
    assert recovered.status()['index']==0
    recovered.advance()
    assert len(recovered.export_rows())==3
    assert recovered.journal.audit_events(recovered.run_id)[0]['kind']=='DISPATCH_LIMITED'


def test_legacy_unscheduled_power_is_byte_equivalent_to_native(tmp_path):
    from stage1.engine import ThreePlantEngine
    cfg=ClockConfig(START,1)
    standalone=ThreePlantEngine(cfg,FakeSolar,FakeWind)
    ref=standalone.advance()
    c=coordinator(tmp_path)
    out=c.advance()
    for p in ('HES','GES','RES'):
        x=next(r for r in ref if r['plant']==p)
        y=out['latest'][p]
        assert x==y
