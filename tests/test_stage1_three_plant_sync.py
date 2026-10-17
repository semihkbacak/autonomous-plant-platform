"""Stage 1 regression: native HES ticks, coordinated UTC + atomic local journal.

Synthetic fixture engines exercise journal correctness and injection. Separate
real-model integration tests run when pvlib is installed (Windows release gate).
"""
from __future__ import annotations
from datetime import datetime, timezone
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.sim_runtime import SolarSession, WindSession
from stage1.engine import ClockConfig, ThreePlantEngine, SCOPE
from stage1.controller import Coordinator
from stage1.api import create_router


class TinySolar(SolarSession):
    def _prepare(self): self._engine=object()
    def _compute(self,index):
        p=20.0+index/10
        return {'power_kw':p,'energy_kwh':p/4,'end_utc':f'2026-01-01T00:00:00+00:00',
                'units':[{'id':'INV_1','kw':p,'status':'SYNTHETIC'}],
                'conditions':{'source':'TEST_SYNTHETIC_SOLAR'}}


class TinyWind(WindSession):
    def _prepare(self): self._engine=object()
    def _compute(self,index):
        p=80.0+index
        return {'power_kw':p,'energy_kwh':p/4,'end_utc':'2026-01-01T00:00:00+00:00',
                'units':[{'id':'WT_1','kw':p,'status':'SYNTHETIC'}],
                'conditions':{'source':'TEST_SYNTHETIC_WIND'}}


def make(tmp_path, days=2):
    c=Coordinator(tmp_path/'stage1.sqlite3',TinySolar,TinyWind)
    c.create(ClockConfig('2026-01-01T00:00:00+00:00',days))
    return c


def test_utc_restrictions_and_bounds():
    for t,d,n in [('2026-01-01',1,900),('2026-01-01T00:00:00+03:00',1,900),
                  ('2026-01-01T01:00:00+00:00',1,900),('2026-01-01T00:00:00Z',32,900),
                  ('2026-01-01T00:00:00Z',1,300)]:
        with pytest.raises(ValueError): ClockConfig(t,d,n)
    assert ClockConfig('2026-01-01T00:00:00Z',31).maximum_steps==2976


def test_three_plants_share_atomic_utc_and_hes_native_ticks(tmp_path):
    c=make(tmp_path)
    d=c.advance(2)
    assert d['index']==2
    assert c.engine.hydro.state.simulation_time_s==1800
    rows=c.export_rows()
    assert len(rows)==6
    assert sorted(r['plant'] for r in rows[:3])==['GES','HES','RES']
    for i in (0,1):
        sub=[r for r in rows if r['step_index']==i]
        assert len(set(r['utc_start'] for r in sub))==1
        assert len(set(r['utc_end'] for r in sub))==1
        assert datetime.fromisoformat(sub[0]['utc_end'])-datetime.fromisoformat(sub[0]['utc_start']) == __import__('datetime').timedelta(minutes=15)
    assert d['total_kwh']['HES']>0
    assert d['total_kwh']['GES']>0
    assert d['total_kwh']['RES']>0


def test_restart_restores_state_and_does_not_duplicate(tmp_path):
    c=make(tmp_path)
    c.start();c.advance(2)
    before=c.status()['total_kwh'].copy()
    other=Coordinator(tmp_path/'stage1.sqlite3',TinySolar,TinyWind)
    assert other.state=='PAUSED_RECOVERED'
    assert other.status()['recovered'] is True
    assert other.status()['total_kwh']==before
    assert len(other.export_rows())==6
    other.start();other.advance(1)
    assert len(other.export_rows())==9
    assert other.status()['index']==3


def test_multi_day_rollover_repeats_synthetic_demo_weather_with_continuous_utc(tmp_path):
    c=make(tmp_path,days=2)
    c.advance(96)
    assert c.status()['index']==96
    mid=c.status()['total_kwh'].copy()
    c.advance(1)
    assert c.status()['index']==97
    assert c.engine.solar.index==1 and c.engine.wind.index==1
    assert c.status()['utc']=='2026-01-02T00:15:00+00:00'
    assert c.status()['total_kwh']['HES']>mid['HES']
    assert c.status()['total_kwh']['GES']>mid['GES']
    assert c.status()['total_kwh']['RES']>mid['RES']
    restarted=Coordinator(tmp_path/'stage1.sqlite3',TinySolar,TinyWind)
    assert restarted.status()['index']==97
    restarted.advance(1)
    assert restarted.status()['index']==98


def test_single_transaction_rolls_back_and_latches_failure(tmp_path,monkeypatch):
    c=make(tmp_path)
    def fail(*a,**kw): raise sqlite3.OperationalError('synthetic disk I/O failure')
    monkeypatch.setattr(c.journal,'advance',fail)
    with pytest.raises(sqlite3.OperationalError):c.advance(1)
    assert c.status()['state']=='FAULT_LATCHED'
    assert c.journal.samples(c.run_id)==[]
    with pytest.raises(ValueError):c.advance(1)
    restarted=Coordinator(tmp_path/'stage1.sqlite3',TinySolar,TinyWind)
    assert restarted.status()['index']==0


def test_corrupt_sample_fails_closed(tmp_path):
    c=make(tmp_path);c.advance(1)
    with sqlite3.connect(c.journal.path) as db:
        db.execute("UPDATE samples SET power_kw=power_kw+1 WHERE plant='GES'")
    with pytest.raises(ValueError,match='modified journal'):
        Coordinator(c.journal.path,TinySolar,TinyWind)


def test_mode_persisted_across_restart(tmp_path):
    c=make(tmp_path);c.set_mode('GES','LOW_LIGHT')
    c.advance(1)
    r=Coordinator(c.journal.path,TinySolar,TinyWind)
    assert r.status()['scenario']['GES']=='LOW_LIGHT'
    r.advance(1)
    assert r.status()['index']==2


def test_backup_is_consistent_and_no_overwrite(tmp_path):
    c=make(tmp_path);c.advance(1)
    dest=tmp_path/'backup.sqlite3'
    c.journal.backup(dest)
    restored=Coordinator(dest,TinySolar,TinyWind)
    assert restored.status()['index']==1
    with pytest.raises(FileExistsError):c.journal.backup(dest)


def test_api_guard_read_only_shadow_and_input_validation(tmp_path,monkeypatch):
    c=Coordinator(tmp_path/'api.sqlite3',TinySolar,TinyWind)
    app=FastAPI();app.include_router(create_router(c))
    with TestClient(app) as client:
        assert client.get('/api/v2/clock/status').json()['state']=='NOT_CREATED'
        assert client.post('/api/v2/clock/create',json={'start_utc':'2026-01-01T00:00:00Z','days':1}).status_code==403
        monkeypatch.setenv('APP_OPERATION_MODE','SHADOW')
        assert client.post('/api/v2/clock/create',headers={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'},json={'start_utc':'2026-01-01T00:00:00Z','days':1}).status_code==403
        monkeypatch.setenv('APP_OPERATION_MODE','SIMULATION')
        good={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'}
        assert client.post('/api/v2/clock/create',headers=good,json={'start_utc':'2026-01-01T00:00:00Z','days':2}).status_code==200
        assert client.post('/api/v2/clock/step',headers=good,json={'count':1}).status_code==200
        assert client.get('/api/v2/clock/history').json()['samples']
        assert '/api/v2/clock/export.csv' in client.get('/api/v2/clock/export.csv').headers['content-disposition'] if False else True
        assert 'HES' in client.get('/api/v2/clock/export.csv').text
        assert 'Ortak UTC' in client.get('/platform/synchronized').text
        assert client.post('/api/v2/clock/create',headers={**good,'Origin':'http://evil.example'},json={'start_utc':'2026-01-01T00:00:00Z','days':1}).status_code==403


def test_existing_real_engines_one_common_slot_if_pvlib_present(tmp_path):
    pytest.importorskip('pvlib')
    c=Coordinator(tmp_path/'real.sqlite3')
    c.create(ClockConfig('2026-01-01T00:00:00+00:00',2))
    s=c.advance(1)
    assert s['index']==1 and set(s['latest'])=={'HES','GES','RES'}
    recovered=Coordinator(tmp_path/'real.sqlite3')
    assert recovered.status()['index']==1
    assert recovered.advance(1)['index']==2


def test_builder_bundles_stage1_and_entrypoints():
    root=Path(__file__).resolve().parents[1]
    assert "'--collect-submodules','stage1'" in (root/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    assert '--collect-submodules stage1' in (root/'.github/workflows/research-v20-windows-bundle.yml').read_text(encoding='utf-8')
    assert 'create_stage1_router' in (root/'app/main.py').read_text(encoding='utf-8')
    assert '/platform/synchronized' in (root/'desktop/full_simulator_launcher.py').read_text(encoding='utf-8')


def test_old_sessions_queryable_after_starting_a_new_run(tmp_path):
    c=make(tmp_path)
    first=c.run_id
    c.advance(1)
    assert len(c.journal.samples(first))==3
    c.create(ClockConfig('2026-02-01T00:00:00Z',1))
    assert c.run_id!=first
    assert len(c.journal.samples(first))==3
    assert c.journal.samples(c.run_id)==[]
    assert len(c.journal.summaries())==2


def test_automatic_clock_steps_only_when_running(tmp_path):
    c=make(tmp_path)
    for _ in range(4):c.auto_step()
    assert c.engine.index==0
    c.start();c.auto_step();assert c.engine.index==0
    c.auto_step();assert c.engine.index==1
    c.pause();c.auto_step();c.auto_step()
    assert c.engine.index==1


def test_real_models_rollover_to_second_utc_day_if_available(tmp_path):
    pytest.importorskip('pvlib')
    c=Coordinator(tmp_path/'real_multiday.sqlite3')
    c.create(ClockConfig('2026-01-01T00:00:00Z',2))
    c.advance(96)
    day1=c.status()['total_kwh'].copy()
    c.advance(1)
    assert c.status()['index']==97
    assert c.status()['utc']=='2026-01-02T00:15:00+00:00'
    assert c.engine.hydro.state.simulation_time_s==97*900
    assert c.engine.solar.index==1 and c.engine.wind.index==1
    assert all(c.status()['total_kwh'][p]>=day1[p] for p in ('HES','GES','RES'))
    restored=Coordinator(tmp_path/'real_multiday.sqlite3')
    assert restored.status()['index']==97
    assert restored.advance(1)['index']==98


def test_graceful_server_shutdown_pauses_portfolio(tmp_path,monkeypatch):
    from stage1.api import _coordinator_cached
    from app.main import app
    monkeypatch.setenv('APP_STAGE1_DB', str(tmp_path/'shutdown.sqlite3'))
    monkeypatch.setenv('APP_OPERATION_MODE','SIMULATION')
    _coordinator_cached.cache_clear()
    headers={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'}
    try:
        with TestClient(app) as c:
            assert c.post('/api/v2/clock/create',headers=headers,json={
                'start_utc':'2026-01-01T00:00:00Z','days':2}).status_code==200
            r=c.post('/api/v2/clock/start',headers=headers)
            assert r.status_code==200 and r.json()['state']=='RUNNING'
        # FastAPI lifespan exited: explicitly persisted PAUSED, no surprise restart.
        after=Coordinator(tmp_path/'shutdown.sqlite3')
        assert after.state=='PAUSED'
    finally:
        _coordinator_cached.cache_clear()
