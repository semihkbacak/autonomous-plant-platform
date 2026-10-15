"""No physical OT, no real telemetry trust: research/shadow tests."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.site_guard import OperationModeFence, operation_mode
from app.site_readiness import create_site_readiness_router, readiness_report
from app.site_shadow import ShadowStore, FIELDS, validate_reading
from simulator.telemetry_fault_lab import fault_matrix, simulate_case, BASE, FAULTS, NOW


def row(**changes):
    x = {"site_id": "DEMO", "plant": "HES", "equipment_id": "UNIT_1",
         "metric": "active_power_kw", "unit": "kW", "timestamp_utc": (NOW-timedelta(seconds=30)).isoformat(),
         "value": "3000", "quality": "GOOD", "source_ref": "TEST_NO_FIELD_DATA"}
    x.update(changes)
    return x


def csvfile(path: Path, rows):
    with path.open('w', encoding='utf8', newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    return path


def test_shadow_valid_csv_and_not_control_ready(tmp_path):
    store=ShadowStore(tmp_path/'shadow.db')
    result=store.import_csv(csvfile(tmp_path/'in.csv',[row()]),now=NOW)
    assert result['rows_imported']==1
    output=store.latest(now=NOW)
    assert output['all_usable_for_study'] is True
    assert output['ready_for_plant_control'] is False
    assert output['source_independently_verified'] is False
    assert output['telemetry_live'] is False


def test_shadow_filter_and_qualifier(tmp_path):
    db=ShadowStore(tmp_path/'s.db')
    db.import_csv(csvfile(tmp_path/'f.csv', [
        row(), row(site_id='TEST2', plant='RES',equipment_id='WT_1',quality='BAD',value='900')
    ]),now=NOW)
    assert len(db.latest(now=NOW)['measurements'])==2
    assert not db.latest(site_id='TEST2',now=NOW)['all_usable_for_study']
    assert len(db.latest(site_id='DEMO',now=NOW)['measurements'])==1


def test_batch_atomic_rollback(tmp_path):
    store=ShadowStore(tmp_path/'s.db')
    path=csvfile(tmp_path/'broken.csv',[row(),row(value='nan',timestamp_utc=(NOW+timedelta(seconds=5)).isoformat())])
    with pytest.raises(ValueError): store.import_csv(path,now=NOW)
    assert store.latest(now=NOW)['status']=='NO_DATA'


def test_existing_not_silently_overwritten(tmp_path):
    store=ShadowStore(tmp_path/'s.db')
    p=csvfile(tmp_path/'f.csv',[row()]);store.import_csv(p,now=NOW)
    with pytest.raises(ValueError,match='duplicate'):
        store.import_csv(p,now=NOW)
    assert len(store.latest(now=NOW)['measurements'])==1


@pytest.mark.parametrize('bad,fragment', [
    ({'unit':'MW'},'Wrong unit'),
    ({'value':'nan'},'Nonfinite'),
    ({'value':'inf'},'Nonfinite'),
    ({'value':'-1'},'Nonfinite'),
    ({'quality':'CALIBRATED'},'quality'),
    ({'timestamp_utc':'2026-10-15T18:00:00'},'UTC'),
    ({'timestamp_utc':(NOW+timedelta(minutes=10)).isoformat()},'Future'),
    ({'plant':'UNKNOWN'},'plant/metric'),
    ({'site_id':'../pwn'},'site_id'),
    ({'source_ref':''},'source'),
    ({'value':'10000000'},'Nonfinite'),
])
def test_field_rejection(bad,fragment):
    with pytest.raises(ValueError,match=fragment):
        validate_reading(row(**bad),now=NOW)


def test_stale_readings_never_promoted(tmp_path):
    s=ShadowStore(tmp_path/'db.db')
    s.import_csv(csvfile(tmp_path/'p.csv',[row(timestamp_utc=(NOW-timedelta(days=2)).isoformat())]),now=NOW)
    state=s.latest(now=NOW)
    assert state['measurements'][0]['freshness']=='STALE'
    assert not state['all_usable_for_study']


def test_bad_csv_is_not_created_as_data(tmp_path):
    s=ShadowStore(tmp_path/'db.db')
    csvfile(tmp_path/'p.csv',[])
    with pytest.raises(ValueError,match='Empty'): s.import_csv(tmp_path/'p.csv',now=NOW)
    assert not s.latest(now=NOW)['measurements']


def test_site_readiness_cannot_authorize_control():
    r=readiness_report()
    assert len(r['gates'])>=10
    assert not r['can_connect_to_real_equipment']
    assert not r['real_control_authorized']
    assert all(g['status']=='INDEPENDENT_APPROVAL_NOT_VERIFIED' for g in r['gates'])


def test_evidence_hash_does_not_become_approval(tmp_path):
    folder=tmp_path/'OEM_PHYSICS';folder.mkdir()
    (folder/'manufacturer_note.txt').write_text('synthetic, not checked',encoding='utf-8')
    r=readiness_report(tmp_path)
    gate=next(x for x in r['gates'] if x['gate']=='OEM_PHYSICS')
    assert len(gate['evidence_submitted'])==1
    assert gate['status']=='INDEPENDENT_APPROVAL_NOT_VERIFIED'
    assert not r['real_control_authorized']


def app_for_api(tmp_path):
    app=FastAPI();app.add_middleware(OperationModeFence)
    app.include_router(create_site_readiness_router(tmp_path/'offline.db'))
    @app.post('/api/v1/units/UNIT_1/start')
    def dangerous():return {'accepted':True}
    return TestClient(app)


def test_shadow_mode_never_mutates(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_OPERATION_MODE','SHADOW')
    client=app_for_api(tmp_path)
    assert client.get('/api/v1/site/readiness').status_code==200
    assert client.post('/api/v1/units/UNIT_1/start').status_code==403
    assert client.post('/api/v1/anything').status_code==403
    assert client.get('/platform/site-transition').status_code==200


def test_unknown_real_mode_fails_closed(monkeypatch):
    monkeypatch.setenv('APP_OPERATION_MODE','REAL')
    with pytest.raises(RuntimeError,match='NOT implemented'):
        operation_mode()


def test_nonlocal_rejected_even_reading(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_OPERATION_MODE','SHADOW')
    app=FastAPI();app.add_middleware(OperationModeFence)
    app.include_router(create_site_readiness_router(tmp_path/'x.db'))
    remote=TestClient(app, client=('203.0.113.50',4555))
    assert remote.get('/api/v1/site/readiness').status_code==403


def test_site_api_has_no_mutation_routes(tmp_path):
    c=app_for_api(tmp_path)
    spec=c.get('/openapi.json').json()
    for path,methods in spec['paths'].items():
        if path.startswith('/api/v1/site/'):
            assert set(methods)=={'get'}
    assert c.get('/api/v1/site/telemetry-fault-matrix').json()['case_count']==30


@pytest.mark.parametrize('plant',list(BASE))
@pytest.mark.parametrize('fault',list(FAULTS))
def test_thirty_telemetry_faults_are_caught(plant,fault):
    result=simulate_case(plant,fault)
    assert result['passed'],result
    assert result['scope']=='OFFLINE_TELEMETRY_QA_NOT_PHYSICAL_FAULT_MODEL'


def test_matrix_never_claims_physical_fault_coverage():
    result=fault_matrix()
    assert result['passed']
    assert result['case_count']==30
    assert result['physical_fault_coverage'] is False
    assert result['oem_field_validation'] is False
