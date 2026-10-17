"""FIX6: realistic synthetic GES/RES steps, read-only UI, recoverable demo data."""
from __future__ import annotations
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.live_twins_v20 import create_live_twins_router
from app.sim_runtime import SimulatorSessions
from app.sim_console_api import create_sim_console_router
from simulator.hydro import HydroPlantSimulator
from tools.prepare_res_history import ensure_synthetic_res_history, inspect_res_history


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    sessions=SimulatorSessions()
    hydro=HydroPlantSimulator()
    app=FastAPI()
    app.include_router(create_live_twins_router(sessions,hydro))
    app.include_router(create_sim_console_router(sessions,hydro))
    return TestClient(app),sessions


def test_live_twin_page_contains_both_plants_and_controls(client):
    c,_=client
    r=c.get('/platform/live-twins')
    assert r.status_code==200
    for text in ('GES', 'RES', 'ges-graph', 'res-graph', 'X-Sim-Console-Confirm',
                 'SADECE SENTETİK SİMÜLASYON', 'api/v1/live-twins/state'):
        assert text in r.text


def test_live_twin_initially_paused_without_real_data(client):
    c,_=client
    state=c.get('/api/v1/live-twins/state').json()
    assert state['scope']=='SYNTHETIC_LOCAL_SIMULATION_NOT_A_REAL_TIME_SITE_TWIN'
    for name in ('ges','res'):
        assert state[name]['running'] is False
        assert state[name]['power_series']==[]
        assert state[name]['conditions']=={}


@pytest.mark.parametrize('plant', ['ges','res'])
def test_true_live_sim_engine_steps_and_reports_conditions(client,plant):
    if plant=='ges':pytest.importorskip('pvlib')
    c,s=client
    hdr={'X-Sim-Console-Confirm':'SIMULATION_ONLY'}
    assert c.post(f'/api/v1/sim-console/{plant}/start',headers=hdr).status_code==200
    result=c.post(f'/api/v1/sim-console/{plant}/step',headers=hdr)
    assert result.status_code==200, result.text
    x=c.get('/api/v1/live-twins/state').json()[plant]
    assert x['intervals']==1 and len(x['power_series'])==1
    assert x['power_series'][0]['power_kw']==x['last_power_kw']
    assert len(x['units'])==2
    assert x['conditions']['source'].startswith('SYNTHETIC_')
    if plant=='ges':
        assert x['conditions']['irradiance_ghi_w_m2']>=0
    else:
        assert x['conditions']['wind_speed_m_s']>=0
    assert c.post(f'/api/v1/sim-console/{plant}/reset',headers=hdr).status_code==200
    assert c.get('/api/v1/live-twins/state').json()[plant]['power_series']==[]


def test_live_sim_protects_commands_when_not_opted_in(client,monkeypatch):
    c,_=client
    monkeypatch.delenv('APP_SIM_CONSOLE_WRITES')
    assert c.get('/api/v1/live-twins/state').status_code==200
    r=c.post('/api/v1/sim-console/ges/start',headers={'X-Sim-Console-Confirm':'SIMULATION_ONLY'})
    assert r.status_code==403


def test_res_history_generated_and_existing_file_not_overwritten(tmp_path):
    path=tmp_path/'demo'/'res.sqlite3'
    first=ensure_synthetic_res_history(path)
    assert first['runs']==1 and first['intervals']==96
    before=path.read_bytes()
    again=ensure_synthetic_res_history(path)
    assert first==again and before==path.read_bytes()
    assert inspect_res_history(path)['source']=='SYNTHETIC_WIND_NOT_REAL_SITE'


def test_res_history_broken_file_is_not_overwritten(tmp_path):
    path=tmp_path/'bad.sqlite3'
    path.write_bytes(b'corrupt')
    with pytest.raises(Exception):ensure_synthetic_res_history(path)
    assert path.read_bytes()==b'corrupt'


def test_native_windows_exe_build_must_test_uvicorn_and_server():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    source=(root/'desktop/full_simulator_launcher.py').read_text(encoding='utf-8')
    script=(root/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    assert 'import uvicorn' in source
    assert '--smoke-server' in script
    assert '--self-test' in script
    assert 'AutonomousPlantSimulatorV20_FIX11' in script


def test_ges_daylight_fast_forward_is_synthetic_only(client,monkeypatch):
    pytest.importorskip('pvlib')
    c,_=client
    hdr={'X-Sim-Console-Confirm':'SIMULATION_ONLY'}
    r=c.post('/api/v1/sim-console/ges/daylight',headers=hdr)
    assert r.status_code==200,r.text
    data=r.json()
    assert data['intervals'] <= 48 and data['intervals']>1
    assert data['conditions']['irradiance_ghi_w_m2'] >= 40
    assert len(data['power_series'])==data['intervals']
    monkeypatch.delenv('APP_SIM_CONSOLE_WRITES')
    assert c.post('/api/v1/sim-console/ges/daylight',headers=hdr).status_code==403
