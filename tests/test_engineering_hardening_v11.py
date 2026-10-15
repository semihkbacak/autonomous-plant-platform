"""Additive v1.1 tests: no industrial device commands."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from io import StringIO
import math
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.engineering_core import inspect_telemetry, generate_fault_matrix, validate_synchronized_portfolio
from app.engineering_coverage import coverage
from app.engineering_shadow import compare_stream
from app.engineering_api import create_engineering_router
from app.engineering_audit import LocalCommandAuditMiddleware, recent_attempts
from app.sim_runtime import SimulatorSessions
from simulator.hydro import HydroPlantSimulator


def records(*, delta=0, missing=None):
    start = datetime(2026, 6, 21, tzinfo=timezone.utc)
    rows=[]
    for i in range(2):
        a=(start + timedelta(minutes=15*i)).isoformat()
        b=(start + timedelta(minutes=15*(i+1))).isoformat()
        for plant in ('HES','GES','RES'):
            if (i,plant) == missing:
                continue
            rows.append({'plant':plant,'start_utc':a,'end_utc':b,
                         'mean_power_kw':10+i,'source_kind':'SYNTHETIC_ALIGNED'})
    if delta:
        rows[-1]['start_utc'] = (start+timedelta(minutes=delta)).isoformat()
    return rows


def test_good_quality():
    x=inspect_telemetry('HES', {'power_kw':12, 'energy_kwh':3, 'units':[{'id':'A','kw':5},{'id':'B','kw':7}]})
    assert x['quality']=='VALID_SYNTHETIC'
    assert x['freshness']=='UNVERIFIED'


@pytest.mark.parametrize('plant',('HES','GES','RES'))
def test_unavailable(plant):
    assert inspect_telemetry(plant,None)['quality']=='UNAVAILABLE'


@pytest.mark.parametrize('number',(float('nan'),float('inf'),-1, True, '12'))
def test_invalid_power(number):
    assert inspect_telemetry('GES',{'power_kw':number,'units':[]})['quality']=='INVALID'


def test_duplicate_ids():
    q=inspect_telemetry('RES',{'power_kw':2,'units':[{'id':'A','kw':1},{'id':'A','kw':1}]})
    assert 'DUPLICATE_UNIT_ID' in q['issues']


def test_inconsistent_units():
    q=inspect_telemetry('HES',{'power_kw':20,'units':[{'id':'A','kw':1}]})
    assert 'UNIT_POWER_MISMATCH' in q['issues']


def test_fault_matrix_all_expected():
    x=generate_fault_matrix()
    assert len(x)>=14 and all(item['passed'] for item in x)


def test_aligned_portfolio():
    p=validate_synchronized_portfolio(records(delta=0))
    assert p['interval_count']==2
    assert p['total_energy_kwh']==pytest.approx((10+11)*.25*3)
    assert not p['field_validation']


def test_portfolio_refuses_different_clocks():
    with pytest.raises(ValueError,match='differ'):
        validate_synchronized_portfolio(records(delta=7))


def test_portfolio_refuses_missing():
    with pytest.raises(ValueError,match='differ'):
        validate_synchronized_portfolio(records(delta=0,missing=(0,'HES')))


def test_portfolio_refuses_duplicate():
    with pytest.raises(ValueError,match='Duplicate'):
        validate_synchronized_portfolio(records(delta=0)+[records(delta=0)[0]])


def test_portfolio_refuses_naive_dates():
    rows=records(delta=0)
    rows[0]['start_utc']='2026-06-21T00:00:00'
    with pytest.raises(ValueError,match='UTC'):
        validate_synchronized_portfolio(rows)


def test_portfolio_refuses_real_or_unknown_provenance():
    rows=records(delta=0)
    rows[0]['source_kind']='FIELD_UNVERIFIED'
    with pytest.raises(ValueError,match='synthetic'):
        validate_synchronized_portfolio(rows)


def test_coverage_explicitly_not_field_ready():
    r=coverage()
    assert not r['field_ready']
    assert r['totals']['NOT_IMPLEMENTED'] >= 5
    assert any(x['feature']=='FULL_PARALLEL_BYPASS_SHADING' for x in r['items'])


def test_shadow_csv_metrics():
    csv='timestamp_utc,observed_kw,predicted_kw\n2026-01-01T00:00:00Z,10,12\n2026-01-01T00:15:00Z,20,18\n'
    report=compare_stream(StringIO(csv))
    assert report['mae_kw']==2
    assert report['bias_kw']==0
    assert not report['field_data_independently_verified']


def test_shadow_rejects_order():
    csv='timestamp_utc,observed_kw,predicted_kw\n2026-01-01T00:15:00Z,10,12\n2026-01-01T00:00:00Z,20,18\n'
    with pytest.raises(ValueError,match='increasing'):
        compare_stream(StringIO(csv))


def test_shadow_rejects_nan():
    csv='timestamp_utc,observed_kw,predicted_kw\n2026-01-01T00:00:00Z,nan,12\n2026-01-01T00:15:00Z,20,18\n'
    with pytest.raises(ValueError,match='Nonfinite'):
        compare_stream(StringIO(csv))


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv('APP_ENGINEERING_AUDIT_DB',str(tmp_path/'audit.db'))
    monkeypatch.delenv('APP_HARDEN_LEGACY',raising=False)
    app=FastAPI()
    hydro=HydroPlantSimulator(); hydro.set_auto_tick(False)
    app.include_router(create_engineering_router(hydro,SimulatorSessions()))
    app.add_middleware(LocalCommandAuditMiddleware)
    @app.post('/api/v1/units/UNIT_1/start')
    def old_command():
        return {'accepted':True}
    return TestClient(app)


def test_api_quality(client):
    r=client.get('/api/v1/platform/engineering/quality')
    assert r.status_code==200
    assert r.json()['source_count']==3


def test_api_readiness(client):
    assert client.get('/api/v1/platform/engineering/readiness').json()['readiness_to_control_actual_plant'] is False


def test_api_faults(client):
    assert client.get('/api/v1/platform/engineering/fault-matrix').json()['passed']


def test_api_portfolio(client):
    r=client.post('/api/v1/platform/engineering/portfolio/study',json={'rows':records(delta=0)})
    assert r.status_code==200
    assert r.json()['interval_count']==2


def test_api_portfolio_mismatch_422(client):
    r=client.post('/api/v1/platform/engineering/portfolio/study',json={'rows':records(delta=7)})
    assert r.status_code==422


def test_readonly_html(client):
    r=client.get('/platform/engineering')
    assert r.status_code==200 and 'Güvenilirliği' in r.text
    assert '/api/v1/platform/engineering/quality' in r.text


def test_legacy_hardening_opt_in(client,monkeypatch):
    assert client.post('/api/v1/units/UNIT_1/start').status_code==200
    monkeypatch.setenv('APP_HARDEN_LEGACY','1')
    assert client.post('/api/v1/units/UNIT_1/start').status_code==403
    logs=client.get('/api/v1/platform/engineering/command-attempts').json()['events']
    assert logs[0]['note']=='BLOCKED_LEGACY_MUTATION'
    assert logs[1]['status']==200


def test_audit_read_does_not_add_entry(client):
    assert client.get('/api/v1/platform/engineering/command-attempts').json()['events']==[]


def test_audit_does_not_store_body(client):
    client.post('/api/v1/units/UNIT_1/start',json={'password':'should-never-appear'})
    assert 'should-never-appear' not in str(client.get('/api/v1/platform/engineering/command-attempts').json())
