"""New Stage 2-5 synthetic physics, persistence, API and provenance regression."""
from __future__ import annotations

from dataclasses import replace
from math import isfinite
import os
import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from advanced_v2.physics import SolarPhysics,WindPhysics,HydroPhysics,iv_curve,cp_approx,SCOPE
from advanced_v2.engine import ResearchConfig,AdvancedEngine,today_weather,dispatch,empirical_anomaly,benchmark_bounds
from advanced_v2.controller import Controller
from advanced_v2.validation import forecast,chronological_holdout,scenario_comparison,metrics
from advanced_v2.api import create_router


def make(tmp_path,**kw):
    c=Controller(tmp_path/'advanced.sqlite3')
    c.create(ResearchConfig(**kw))
    return c


def test_solar_iv_pv_curve_is_nonnegative_and_voltage_ordered():
    c=iv_curve(900,38,((1,1,1),(1,1,1)))
    assert len(c)==65
    assert c[0]['v']==0
    assert all(x['i']>=0 and x['p']>=0 for x in c)
    assert all(x['v']<=y['v'] for x,y in zip(c,c[1:]))
    assert max(x['p'] for x in c)>100


@pytest.mark.parametrize('algorithm',['PO','INC_COND','GLOBAL'])
def test_dynamic_mppt_and_inverter_work(algorithm):
    s=SolarPhysics()
    out=s.advance(950,25,algorithm=algorithm)
    assert 0<out['power_kw']<=1.0
    assert out['energy_kwh']==pytest.approx(out['power_kw']/4,abs=1e-5)
    assert out['mppt']==algorithm
    assert out['global_mpp_kw']>=out['dc_kw']-0.0002


def test_shading_changes_iv_and_global_mpp():
    clear=SolarPhysics().advance(900,22)
    shaded=SolarPhysics().advance(900,22,shade=((.25,1,1),(1,.1,1)))
    assert shaded['global_mpp_kw']<clear['global_mpp_kw']


def test_solar_no_irradiance_and_trip_are_zero():
    assert SolarPhysics().advance(0,20)['power_kw']==0
    assert SolarPhysics().advance(850,22,fault='GRID_LOSS')['power_kw']==0
    assert SolarPhysics().advance(850,22,fault='INVERTER_TRIP')['power_kw']==0


def test_solar_rejects_invalid_params():
    for kwargs in ({'algorithm':'UNSAFE'},{'fault':'ARC_PROTECTION_DISABLED'}):
        with pytest.raises(ValueError): SolarPhysics().advance(700,25,**kwargs)
    with pytest.raises(ValueError): SolarPhysics().advance(-1,25)


def test_wind_rotor_pitch_yaw_and_power_state():
    w=WindPhysics()
    out=w.advance(1,11,15)
    assert len(out['turbines'])==2 and 0<out['energy_kwh']
    assert all(0<=t['pitch_deg']<=90 and t['rotor_rpm']>0 for t in out['turbines'])
    assert all(out['turbines'][i]['power_kw']<=400 for i in (0,1))
    assert out['turbines'][1]['power_kw']<out['turbines'][0]['power_kw']
    frozen=w.checkpoint();restored=WindPhysics.recover(frozen)
    assert restored.advance(2,11)==w.advance(2,11)


def test_wind_betz_bound_and_faults():
    assert all(0<=cp_approx(t,2)<=16/27 for t in (1,3,7,9,15,25))
    assert WindPhysics().advance(0,13,fault='GRID_LOSS')['power_kw']==0
    assert WindPhysics().advance(0,13,fault='BRAKE')['power_kw']==0


def test_hydro_reservoir_and_governor_and_surge_model():
    h=HydroPhysics()
    before=h.state.reservoir_m3
    r=h.advance(2300,9)
    assert r['power_kw']>0 and 0<r['nozzle_m3s']<12
    assert r['frequency_hz']>0 and r['max_joukowsky_bar']>=0
    assert r['reservoir_m3']!=before
    saved=h.checkpoint();other=HydroPhysics.recover(saved)
    assert h.advance(1900)==other.advance(1900)


def test_hydro_load_rejection_and_grid_loss():
    assert HydroPhysics().advance(2200,fault='GRID_LOSS')['energy_kwh']==0
    assert HydroPhysics().advance(2200,fault='LOAD_REJECTION')['power_kw']==0


def test_energy_balance_and_anomaly_baseline():
    r=dispatch(200,80,100,50)
    assert r['served_kw']==200 and r['shortfall_kw']==0 and r['curtailment_kw']==30
    assert empirical_anomaly(400,[100]*10)['flag']
    assert not empirical_anomaly(400,[100]*4)['flag']


def test_advanced_three_physics_share_one_utc_slot_and_bounds(tmp_path):
    c=make(tmp_path)
    stat=c.advance(2)
    assert stat['index']==2
    history=c.history()
    assert len(history)==2
    assert set(history[0]['rows'])=={'HES','GES','RES'}
    assert all(x['independent_bounds']['wind_within_betz_bound'] for x in history)
    assert all(x['independent_bounds']['hydro_within_water_power_bound'] for x in history)
    assert all(x['independent_bounds']['solar_within_illustrative_ceiling'] for x in history)
    assert history[1]['utc_start']==history[0]['utc_end']
    for x in history:
        assert x['dispatch']['served_kw']<=x['dispatch']['demand_kw']+1e-5
        assert set(x['anomalies'])=={'HES','GES','RES'}


def test_two_day_no_weather_time_reset_and_checkpoint_resume(tmp_path):
    c=make(tmp_path,days=2)
    c.advance(96);c.advance(2)
    last=c.history()[-1]
    assert last['index']==97
    assert last['utc_start'].startswith('2026-01-02T00:15:00')
    recovery=Controller(c.journal.path)
    assert recovery.status()['state']=='PAUSED_RECOVERED'
    assert recovery.status()['index']==98
    recovery.advance(1)
    assert recovery.status()['index']==99
    assert len(recovery.history())==99
    assert all(isfinite(v) for v in recovery.engine.totals.values())


def test_atomic_db_failure_latches_and_no_orphan_slot(tmp_path,monkeypatch):
    c=make(tmp_path)
    def bad(*args,**kwargs):raise sqlite3.OperationalError('synthetic disk failure')
    monkeypatch.setattr(c.journal,'step',bad)
    with pytest.raises(sqlite3.OperationalError):c.advance()
    assert c.state=='FAULT_LATCHED'
    assert c.history()==[]
    recovered=Controller(c.journal.path)
    assert recovered.status()['index']==0
    recovered.advance()
    assert recovered.status()['index']==1


def test_tampered_history_rejected_on_restore(tmp_path):
    c=make(tmp_path);c.advance()
    with sqlite3.connect(c.journal.path) as db:
        db.execute("UPDATE research_steps SET payload=replace(payload,'HES','HEZ')")
    with pytest.raises(ValueError,match='Modified|integrity|chain|sample'):
        Controller(c.journal.path)


def test_bounded_config_and_unsupported_modes():
    for kwargs in ({'days':32},{'pv_blocks':0},{'mppt':'SECRET'},{'weather_mode':'LIVE'},
                   {'site_label':'REAL@SITE'},{'start_utc':'2026-10-16T10:00:00Z'}):
        with pytest.raises(ValueError):ResearchConfig(**kwargs)
    assert ResearchConfig(days=31).max_steps==2976


def test_weather_deterministic_and_distinct_next_day():
    assert today_weather(12)==today_weather(12)
    assert today_weather(50)['irradiance_wm2']>today_weather(0)['irradiance_wm2']
    assert today_weather(60)!=today_weather(156)
    assert today_weather(50,'CLOUDY')['irradiance_wm2']<today_weather(50)['irradiance_wm2']


def test_chronological_holdout_with_quality_and_no_leak(tmp_path):
    c=make(tmp_path);c.advance(12)
    hist=c.history()
    obs=[{'utc_end':r['utc_end'],'power_kw':r['rows']['HES']['power_kw']*.92,
          'quality':'GOOD','unit':'kW'} for r in hist]
    report=chronological_holdout(hist,obs,plant='HES',source_label='user-declared-offline-export')
    assert report['test_count']==4 and report['training_count']==8
    assert report['site_validated'] is False
    assert report['holdout_calibrated']['mae_kw']<report['holdout_uncalibrated']['mae_kw']
    with pytest.raises(ValueError):chronological_holdout(hist,list(reversed(obs)),plant='HES',source_label='synthetic')
    with pytest.raises(ValueError):chronological_holdout(hist,[*obs[:-1],{**obs[-1],'quality':'BAD'}],plant='HES',source_label='synthetic')


def test_forecast_and_scenario_comparison(tmp_path):
    c=make(tmp_path);c.advance(8)
    report=forecast(c.history(),4)
    assert all(len(x)==4 for x in report['forecasts'].values())
    assert report['uncertainty_type'].startswith('HEURISTIC')
    result=scenario_comparison(c.engine.config,[{'label':'shade','changes':{'shade_profile':'HEAVY'}},
                                                {'label':'cloud','changes':{'weather_mode':'CLOUDY'}}],steps=60)
    assert len(result['results'])==3
    assert result['site_validated'] is False
    assert result['results'][0]['steps']==60


def test_api_shadow_rejects_control_and_simulation_requires_confirm(tmp_path,monkeypatch):
    c=Controller(tmp_path/'api.sqlite3');app=FastAPI();app.include_router(create_router(c))
    cli=TestClient(app)
    payload={'start_utc':'2026-01-01T00:00:00Z','days':2}
    monkeypatch.setenv('APP_OPERATION_MODE','SHADOW')
    assert cli.post('/api/v2/advanced/create',json=payload,headers={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'}).status_code==403
    monkeypatch.setenv('APP_OPERATION_MODE','SIMULATION')
    assert cli.post('/api/v2/advanced/create',json=payload).status_code==403
    h={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'}
    assert cli.post('/api/v2/advanced/create',json=payload,headers=h).status_code==200
    assert cli.post('/api/v2/advanced/step',json={'count':1},headers={**h,'Origin':'http://evil.example'}).status_code==403
    assert cli.post('/api/v2/advanced/step',json={'count':2},headers=h).status_code==200
    assert len(cli.get('/api/v2/advanced/history').json()['steps'])==2
    assert 'SYNTHETIC_RESEARCH_NO_OT' in cli.get('/api/v2/advanced/export.csv').text
    assert 'Advanced Research Twin' in cli.get('/platform/advanced-twins').text
    assert cli.get('/api/v2/advanced/forecast').status_code==409
    assert cli.post('/api/v2/advanced/step',json={'count':2},headers=h).status_code==200
    assert cli.get('/api/v2/advanced/forecast').status_code==200


def test_database_backup_and_windows_handle_release(tmp_path):
    c=make(tmp_path);c.advance()
    dest=tmp_path/'backup.sqlite3'
    c.journal.backup(dest)
    assert Controller(dest).status()['index']==1
    with pytest.raises(FileExistsError):c.journal.backup(dest)
    # After last connection exits, Windows permits renaming the file.
    c.journal.rows(c.id)
    path=c.journal.path; renamed=path.with_suffix('.moved')
    path.rename(renamed);renamed.rename(path)


def test_python_windows_builder_and_gui_include_new_modules():
    root=Path(__file__).resolve().parents[1]
    assert "'--collect-submodules','advanced_v2'" in (root/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    assert '--collect-submodules advanced_v2' in (root/'.github/workflows/research-v20-windows-bundle.yml').read_text(encoding='utf-8')
    assert 'create_advanced_router' in (root/'app/main.py').read_text(encoding='utf-8')
    assert '/platform/advanced-twins' in (root/'desktop/full_simulator_launcher.py').read_text(encoding='utf-8')


def test_independent_pvlib_reference_and_physical_law_checks():
    pytest.importorskip('pvlib')
    from advanced_v2.references import pvlib_standard_irradiance_check,independent_law_checks
    r=pvlib_standard_irradiance_check()
    assert r['within_reference_tolerance']
    assert r['relative_error_pct']<12
    assert r['site_validated'] is False
    b=independent_law_checks()
    assert b['cp_below_16_27'] and b['hydro_ideal_kw_at_4m3s_130m']>0


def test_water_budget_optimizer_respects_power_energy_and_priority():
    from advanced_v2.optimization import optimize_water_budget
    # Water corresponding to exactly 100 kWh at 130m/0.83 efficiency.
    water=100*3_600_000/(1000*9.81*130*.83)
    r=optimize_water_budget([500,500],[0,0],available_water_m3=water,
                            max_hydro_kw=300,criticality=[1,10])
    assert r['hydro_schedule_kw'][1]>r['hydro_schedule_kw'][0]
    assert sum(r['hydro_schedule_kw'])*.25 <=100.0001
    assert r['hydro_water_equivalent_m3']<=water+.0001
    assert r['real_control_authorized'] is False

def test_optimization_guard_and_engine_route(tmp_path,monkeypatch):
    c=Controller(tmp_path/'optdb.sqlite3');app=FastAPI();app.include_router(create_router(c))
    cli=TestClient(app)
    assert cli.get('/api/v2/advanced/optimize').status_code==409
    c.create(ResearchConfig());c.advance(2)
    result=cli.get('/api/v2/advanced/optimize?horizon=2')
    assert result.status_code==200
    assert result.json()['site_validated'] is False
