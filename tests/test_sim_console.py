"""Local opt-in GES/RES simulation console tests; no PLC/SCADA connected."""
from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.sim_console_api import create_sim_console_router
from app.sim_runtime import SimulatorSessions
from app.docs_ui import create_docs_router
from simulator.hydro import HydroPlantSimulator


@pytest.fixture()
def harness(monkeypatch):
    monkeypatch.delenv('APP_SIM_CONSOLE_WRITES', raising=False)
    sessions=SimulatorSessions()
    hydro=HydroPlantSimulator()
    hydro.set_auto_tick(False)
    app=FastAPI(docs_url=None)
    app.include_router(create_sim_console_router(sessions,hydro))
    app.include_router(create_docs_router())
    return TestClient(app), sessions, hydro


def _post(client, url, **kwargs):
    return client.post(url,headers={'X-Sim-Console-Confirm':'SIMULATION_ONLY'},**kwargs)


def test_initial_status_is_idle_without_initializing_physics(harness):
    client,sessions,_=harness
    for kind in ('ges','res'):
        data=client.get('/api/v1/sim-console/'+kind).json()
        assert data['running'] is False
        assert data['historian_written'] is False
        assert data['intervals']==0
    assert sessions.ges._engine is None and sessions.res._engine is None


def test_disabled_by_default(harness):
    client,_,_=harness
    assert _post(client,'/api/v1/sim-console/res/start').status_code==403
    assert client.get('/api/v1/sim-console/res').status_code==200


def test_confirmation_header_is_required(harness,monkeypatch):
    client,_,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    assert client.post('/api/v1/sim-console/res/start').status_code==403


def test_reject_cross_origin_requests(harness,monkeypatch):
    client,_,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    r=client.post('/api/v1/sim-console/res/start',headers={
        'X-Sim-Console-Confirm':'SIMULATION_ONLY',
        'Origin':'https://attacker.example',
    })
    assert r.status_code==403


def test_wind_engine_steps_two_turbines_and_energy(harness,monkeypatch):
    client,sessions,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    assert _post(client,'/api/v1/sim-console/res/start').status_code==200
    step=_post(client,'/api/v1/sim-console/res/step')
    assert step.status_code==200
    data=step.json()
    assert data['intervals']==1 and data['energy_kwh']>=0
    assert len(data['units'])==2
    assert data['last_end_utc'].startswith('2026-01-01')
    assert data['historian_written'] is False


def test_wind_fault_and_grid_loss_are_simulated(harness,monkeypatch):
    client,_,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    _post(client,'/api/v1/sim-console/res/mode',json={'mode':'GRID_LOSS'})
    state=_post(client,'/api/v1/sim-console/res/step').json()
    assert state['last_power_kw']==0
    _post(client,'/api/v1/sim-console/res/mode',json={'mode':'NORMAL'})
    next_state=_post(client,'/api/v1/sim-console/res/step').json()
    assert next_state['last_power_kw']>0


def test_invalid_mode_rejected_without_changing_state(harness,monkeypatch):
    client,_,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    response=_post(client,'/api/v1/sim-console/res/mode',json={'mode':'SITE_PLC_CONTROL'})
    assert response.status_code==409
    assert client.get('/api/v1/sim-console/res').json()['mode']=='NORMAL'


def test_step_pause_reset_and_restart(harness,monkeypatch):
    client,_,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    _post(client,'/api/v1/sim-console/res/start')
    _post(client,'/api/v1/sim-console/res/step')
    state=_post(client,'/api/v1/sim-console/res/pause').json()
    assert state['running'] is False
    state=_post(client,'/api/v1/sim-console/res/reset').json()
    assert state['intervals']==0 and state['energy_kwh']==0
    assert _post(client,'/api/v1/sim-console/res/start').status_code==200


def test_auto_clock_advances_only_running_sessions(harness,monkeypatch):
    client,sessions,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    _post(client,'/api/v1/sim-console/res/start')
    sessions.auto_step()
    assert sessions.res.index==0
    sessions.auto_step()
    assert sessions.res.index==1
    _post(client,'/api/v1/sim-console/res/pause')
    sessions.auto_step(); sessions.auto_step()
    assert sessions.res.index==1


def test_hes_simulator_route_does_not_control_devices(harness,monkeypatch):
    client,_,hydro=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    r=_post(client,'/api/v1/sim-console/hes/unit/start',json={'unit_id':'UNIT_1'})
    assert r.status_code==200 and r.json()['accepted'] is True
    assert client.get('/api/v1/sim-console/hes').json()['plant']=='HES'
    assert _post(client,'/api/v1/sim-console/hes/auto',params={'active':'false'}).status_code==200
    assert hydro.auto_tick_enabled is False


def test_unknown_plant_returns_404(harness):
    client,_,_=harness
    assert client.get('/api/v1/sim-console/wrong').status_code==404


def test_docs_has_get_execute_but_no_unrestricted_post(harness):
    client,_,_=harness
    html=client.get('/docs').text
    assert 'Try it out · Execute' in html
    assert 'X-Sim-Console-Confirm' in html
    assert 'canExecute(op)' in html
    assert 'Sadece yerel sentetik simülasyon' in html
    paths=client.get('/openapi.json').json()['paths']
    assert '/api/v1/sim-console/{plant}/step' in paths


def test_solar_session_state_machine_with_stubbed_physics(harness,monkeypatch):
    """GES controls are tested separately from the actual pvlib physics tests."""
    client,sessions,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    monkeypatch.setattr(sessions.ges,'_prepare',lambda: setattr(sessions.ges,'_engine',object()))
    monkeypatch.setattr(sessions.ges,'_compute',lambda index: {
        'power_kw':4.0,'energy_kwh':1.0,
        'end_utc':'2026-06-21T00:15:00+00:00',
        'units':[{'id':'INV_1','kw':4,'status':'RUNNING'}],
    })
    assert _post(client,'/api/v1/sim-console/ges/start').status_code==200
    report=_post(client,'/api/v1/sim-console/ges/step').json()
    assert report['intervals']==1 and report['energy_kwh']==1.0
    assert report['historian_written'] is False


def test_physics_failure_latches_until_reset(harness,monkeypatch):
    client,sessions,_=harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    monkeypatch.setattr(sessions.ges,'_prepare',lambda: setattr(sessions.ges,'_engine',object()))
    def broken(index):
        raise ValueError('Internal detail never returned to clients')
    monkeypatch.setattr(sessions.ges,'_compute',broken)
    result=_post(client,'/api/v1/sim-console/ges/step')
    assert result.status_code==422
    assert 'Internal detail' not in result.text
    state=client.get('/api/v1/sim-console/ges').json()
    assert state['running'] is False and state['error']=='ValueError'
    assert _post(client,'/api/v1/sim-console/ges/start').status_code==409
    assert _post(client,'/api/v1/sim-console/ges/reset').status_code==200


def test_ges_real_integrated_physics_one_step_if_pvlib_installed(harness,monkeypatch):
    """Exercises the genuine GES v0.5 physics pipeline when dependencies exist."""
    pytest.importorskip('pvlib')
    client, _, _ = harness
    monkeypatch.setenv('APP_SIM_CONSOLE_WRITES','1')
    started=_post(client,'/api/v1/sim-console/ges/start')
    assert started.status_code==200, started.text
    reply=_post(client,'/api/v1/sim-console/ges/step')
    assert reply.status_code==200, reply.text
    state=reply.json()
    assert state['intervals']==1
    assert state['energy_kwh']>=0
    assert len(state['units'])==2
    assert state['last_end_utc'].startswith('2026-06-21T00:15:00')
