"""RES v0.1-v1.0 model, scenario, historian, API and quality gates."""
from __future__ import annotations
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import isclose
from pathlib import Path
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.wind_analytics_api import create_wind_analytics_router
from res_v10_release import create_matrix, release
from simulator.wind_history import WindHistorian
from simulator.wind_physics import (
    WindControl, WindFarm, WindTurbine, WindWeather,
    air_density_kg_m3, synthetic_power_kw,
)
from simulator.wind_suite import CASES, default_farm, long_horizon, run_scenario

T0 = datetime(2026, 1, 1, tzinfo=timezone.utc)


def w(speed=8, minutes=15, direction=0):
    return WindWeather(T0 + timedelta(minutes=minutes), speed, direction)


@pytest.fixture(scope='module')
def matrix(tmp_path_factory):
    p = tmp_path_factory.mktemp('res_matrix')
    assert create_matrix(p)['passed']
    return p


def test_v01_density_temperature_pressure():
    assert 1.20 < air_density_kg_m3(15, 101325) < 1.23
    assert air_density_kg_m3(0, 101325) > air_density_kg_m3(35, 101325)
    assert air_density_kg_m3(15, 90000) < air_density_kg_m3(15, 101325)


def test_v01_cut_in_rated_and_cut_out():
    t=WindTurbine('T')
    assert synthetic_power_kw(t, 2, 1.225) == 0
    assert 0 < synthetic_power_kw(t, 8, 1.225) < 3000
    assert synthetic_power_kw(t, 12, 1.225) == 3000
    assert synthetic_power_kw(t, 25, 1.225) == 0


def test_v01_bad_inputs_fail_closed():
    with pytest.raises(ValueError): WindTurbine('T', cut_out_m_s=10)
    with pytest.raises(ValueError): WindWeather(T0.replace(tzinfo=None), 7, 0)
    with pytest.raises(ValueError): WindWeather(T0, float('nan'), 0)
    with pytest.raises(ValueError): WindFarm((WindTurbine('T'),WindTurbine('T')))


def test_v02_wake_directional_and_deterministic():
    a=default_farm().step(w(direction=0))
    b=default_farm().step(w(direction=270))
    assert b.farm_available_kw < a.farm_available_kw
    assert b.turbines[1].wake_loss_fraction > 0
    assert a.turbines[1].wake_loss_fraction == pytest.approx(0)


def test_v02_shear_increases_hub_speed():
    a=default_farm().step(w(8))
    assert all(x.hub_wind_m_s > 8 for x in a.turbines)


def test_v03_yaw_and_icing_reduce_power():
    original=default_farm().step(w())
    yaw=default_farm().step(w(),WindControl(yaw_error_deg={'WT_1':40}))
    ice=default_farm().step(w(),WindControl(icing_fraction={'WT_2':0.5}))
    assert yaw.farm_available_kw < original.farm_available_kw
    assert ice.farm_available_kw < original.farm_available_kw


def test_v03_dispatch_energy_and_unserved():
    low=default_farm().step(w(),WindControl(target_kw=400))
    assert low.farm_dispatched_kw == pytest.approx(400)
    assert low.energy_kwh == pytest.approx(100)
    assert low.farm_curtailed_kw > 0
    high=default_farm().step(w(),WindControl(target_kw=1e6))
    assert high.unserved_target_kw > 0


def test_v04_trip_latch_and_restart():
    farm=default_farm()
    trip=farm.step(w(35))
    assert all(u.high_wind_latched for u in trip.turbines)
    middle=farm.step(w(22,30))
    assert all(u.status == 'HIGH_WIND_LATCHED' for u in middle.turbines)
    restart=farm.step(w(8,45))
    assert all(u.status == 'RUNNING' for u in restart.turbines)


def test_v04_grid_and_estop_block():
    for control in (WindControl(grid_available=False), WindControl(emergency_stop=True)):
        x=default_farm().step(w(),control)
        assert x.farm_dispatched_kw == 0
        assert all(u.status == 'BLOCKED' for u in x.turbines)


def test_v04_rejects_invalid_control_without_advancing():
    farm=default_farm()
    with pytest.raises(ValueError): farm.step(w(),WindControl(yaw_error_deg={'ZZ':3}))
    with pytest.raises(ValueError): farm.step(w(),WindControl(icing_fraction={'WT_2':2}))
    x=farm.step(w())
    assert x.farm_dispatched_kw > 0
    with pytest.raises(ValueError): farm.step(w(minutes=45))


def test_v05_matrix_atomic_counts_and_energy(matrix):
    h=WindHistorian(matrix/'wind_history.sqlite3',read_only=True)
    audit=h.audit(set(CASES))
    assert audit['passed'],audit['issues']
    assert audit['run_count']==12
    runs=h.runs()
    assert len(runs)==12
    assert len(h.intervals(runs[0]['id']))==96
    assert len(h.turbines(runs[0]['id']))==192


def test_v05_rollback_on_bad_interval(tmp_path):
    db=WindHistorian(tmp_path/'bad.sqlite3')
    intervals=run_scenario('BASELINE')[:2]
    intervals[1]=replace(intervals[1],energy_kwh=12345.0)
    with pytest.raises(ValueError): db.save_run('BROKEN',intervals)
    assert db.runs()==[]


def test_v05_detect_energy_tampering(matrix,tmp_path):
    import shutil
    copy=tmp_path/'copy.db'
    shutil.copy2(matrix/'wind_history.sqlite3',copy)
    with sqlite3.connect(copy) as db:
        db.execute('UPDATE wind_intervals SET interval_kwh=interval_kwh+1 WHERE rowid=(SELECT rowid FROM wind_intervals LIMIT 1)')
    assert not WindHistorian(copy,read_only=True).audit(set(CASES))['passed']


def test_v06_scenario_matrix_behavior():
    results={n:sum(r.energy_kwh for r in run_scenario(n)) for n in CASES}
    assert len(results)==12
    assert results['LOW_WIND']==0
    assert results['WAKE_DOWNWIND'] < results['BASELINE']
    assert results['YAW_MISALIGNMENT'] < results['BASELINE']
    assert results['GRID_LOSS'] < results['BASELINE']
    assert results['ACTIVE_CURTAILMENT'] < results['BASELINE']
    assert results['HIGH_WIND_RESTART'] > 0


def test_v07_high_wind_event_and_recovery():
    rows=run_scenario('HIGH_WIND_RESTART')
    assert rows[40].farm_dispatched_kw==0
    assert rows[40].turbines[0].high_wind_latched
    assert rows[70].farm_dispatched_kw>0


def test_v08_api_dashboard_read_only(matrix,tmp_path):
    app=FastAPI()
    app.include_router(create_wind_analytics_router(matrix/'wind_history.sqlite3'))
    c=TestClient(app)
    assert len(c.get('/api/v1/wind/runs').json())==12
    run_id=c.get('/api/v1/wind/runs').json()[0]['id']
    assert len(c.get(f'/api/v1/wind/runs/{run_id}/intervals').json())==96
    assert len(c.get(f'/api/v1/wind/runs/{run_id}/turbines').json())==192
    assert c.get('/wind/dashboard').status_code==200
    assert c.get('/api/v1/wind/runs/999999/intervals').status_code==404
    missing=tmp_path/'missing.db'
    bad=FastAPI()
    bad.include_router(create_wind_analytics_router(missing))
    assert TestClient(bad).get('/api/v1/wind/runs').status_code==503
    assert not missing.exists()


def test_v09_long_year_and_invalid_days():
    result=long_horizon(365)
    assert result['passed']
    assert result['interval_count']==35040
    assert result['energy_kwh']>0
    with pytest.raises(ValueError): long_horizon(366)
    with pytest.raises(ValueError): long_horizon(True)


def test_v10_release_gate_requires_regression_and_year(matrix):
    r=release(matrix/'wind_history.sqlite3',annual_days=2,regression=False)
    assert not r['software_acceptance_passed']
    assert r['scenario_audit']['passed']
    assert not r['oem_power_curve_calibrated']
    assert not r['site_validation']


def test_v10_release_refuses_overwrite(matrix):
    with pytest.raises(FileExistsError): create_matrix(matrix)
