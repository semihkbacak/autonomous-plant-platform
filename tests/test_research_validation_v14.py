"""v1.4 offline research-layer tests; never live control testing."""
from __future__ import annotations
import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from core.v14_model_validation import validate_csv
from core.v14_evidence_gates import inventory, REQUIREMENTS
from core.v14_pv_desoto import model_point
from app.v14_research_api import create_v14_router, BIBLIOGRAPHY

FIELDS = ['timestamp_utc','plant','site_id','equipment_id','observed_kw','predicted_kw','quality','source_kind','source_id','irradiance_w_m2','wind_speed_m_s','flow_m3_s']

def write_csv(path: Path, *, plant='GES', n=48, factor=1.1, origin='SYNTHETIC', mutate=None):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows=[]
    for j in range(n):
        power=5 + j * .1
        row=dict(timestamp_utc=(start+timedelta(minutes=j*15)).isoformat(),
                 plant=plant,site_id='DEMO',equipment_id='DEV1',
                 observed_kw=str(power*factor),predicted_kw=str(power),quality='GOOD',
                 source_kind=origin,source_id='EXAMPLE_NOT_ATTESTED',
                 irradiance_w_m2='800',wind_speed_m_s='7',flow_m3_s='2')
        rows.append(row)
    if mutate:mutate(rows)
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    return path

@pytest.mark.parametrize('plant', ['HES','GES','RES'])
def test_observation_holdout_good(tmp_path, plant):
    result=validate_csv(write_csv(tmp_path/'x.csv',plant=plant))
    g=result['groups'][0]
    assert g['quality_screen_passed']
    assert g['fitted_holdout']['mae_kw'] < g['baseline_holdout']['mae_kw']
    assert g['train_count'] == 36 and g['holdout_count'] == 12
    assert g['scale_train_only'] == pytest.approx(1.1)
    assert not result['site_validated'] and not result['real_control_ready']

def test_hash_changes_if_dataset_changes(tmp_path):
    a=validate_csv(write_csv(tmp_path/'x.csv',factor=1.1))['csv_sha256']
    b=validate_csv(write_csv(tmp_path/'x.csv',factor=1.15))['csv_sha256']
    assert a!=b

def test_declared_field_still_not_authenticated(tmp_path):
    result=validate_csv(write_csv(tmp_path/'x.csv',origin='AUTHORIZED_FIELD_EXPORT'))
    assert result['declared_source_kind']=='AUTHORIZED_FIELD_EXPORT'
    assert not result['source_authenticated']

def test_bad_data_rejected(tmp_path):
    def m(r):r[0]['quality']='BAD'
    with pytest.raises(ValueError,match='quality'):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_wrong_local_time_rejected(tmp_path):
    def m(r):r[0]['timestamp_utc']='2026-01-01T00:00:00'
    with pytest.raises(ValueError,match='UTC'):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_duplicate_time_rejected(tmp_path):
    def m(r):r[1]['timestamp_utc']=r[0]['timestamp_utc']
    with pytest.raises(ValueError,match='uniqueness'):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_out_of_order_rejected(tmp_path):
    def m(r):r[0],r[1]=r[1],r[0]
    with pytest.raises(ValueError,match='order'):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_no_mixing_synthetic_and_field(tmp_path):
    def m(r):r[4]['source_kind']='AUTHORIZED_FIELD_EXPORT'
    with pytest.raises(ValueError,match='cannot mix'):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_infinite_power_rejected(tmp_path):
    def m(r):r[0]['observed_kw']='inf'
    with pytest.raises(ValueError):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_bad_wind_speed_rejected(tmp_path):
    def m(r):r[2]['wind_speed_m_s']='900'
    with pytest.raises(ValueError,match='wind_speed'):
        validate_csv(write_csv(tmp_path/'x.csv',plant='RES',mutate=m))

def test_outlier_scale_refused(tmp_path):
    with pytest.raises(ValueError,match='Implausible'):
        validate_csv(write_csv(tmp_path/'x.csv',factor=3.0))

def test_holdout_drift_detected(tmp_path):
    def m(r):
        for row in r[-12:]:row['observed_kw']=str(float(row['predicted_kw'])*1.42)
    res=validate_csv(write_csv(tmp_path/'x.csv',mutate=m))
    assert not res['all_quality_screens_passed']

def test_bad_fraction_rejected(tmp_path):
    with pytest.raises(ValueError):validate_csv(write_csv(tmp_path/'x.csv'),holdout_fraction=.05)

def test_not_enough_records_rejected(tmp_path):
    with pytest.raises(ValueError):validate_csv(write_csv(tmp_path/'x.csv',n=8))

def test_hourly_gap_rejected(tmp_path):
    def m(r):
        for j,row in enumerate(r[3:],3):row['timestamp_utc']=(datetime(2026,1,4,tzinfo=timezone.utc)+timedelta(minutes=j*15)).isoformat()
    with pytest.raises(ValueError,match='Gap'):
        validate_csv(write_csv(tmp_path/'x.csv',mutate=m))

def test_evidence_missing_is_not_approval():
    d=inventory(None)
    assert len(d['requirements'])>=12 and not d['site_control_authorized']
    assert set(d['missing_file_kinds'])==set(d['requirements'])

def test_evidence_pdf_exists_but_unverified(tmp_path):
    (tmp_path/'FAT_RESULTS.pdf').write_bytes(b'%PDF-1.4\nsynthetic example')
    d=inventory(tmp_path)
    assert d['requirements']['FAT_RESULTS']['file_present']
    assert len(d['requirements']['FAT_RESULTS']['sha256'])==64
    assert not d['requirements']['FAT_RESULTS']['independently_reviewed']
    assert not d['site_control_authorized']

def test_evidence_plant_filter():
    d=inventory(None,required_plants=('GES',))
    assert 'GES_DC_PROTECTION' in d['requirements']
    assert 'HES_TRANSIENT_STUDY' not in d['requirements']

def test_evidence_invalid_plant():
    with pytest.raises(ValueError):inventory(None,required_plants=('NUCLEAR',))

def test_pv_missing_params_rejected():
    with pytest.raises(ValueError,match='Missing'):
        model_point({},1000,25)

def test_pv_nonphysical_param_rejected():
    with pytest.raises(ValueError,match='Nonphysical'):
        model_point(dict(alpha_sc=.001,a_ref=0,I_L_ref=6,I_o_ref=1e-10,R_sh_ref=200,R_s=.3),1000,25)

def test_pv_optional_dependency_when_available():
    pytest.importorskip('pvlib')
    r=model_point(dict(alpha_sc=.004,a_ref=1.7,I_L_ref=5.5,I_o_ref=2e-10,R_sh_ref=300,R_s=.4),1000,25)
    assert r['dc_module_mpp_w']>0 and not r['external_parameter_provenance_verified']

def test_research_api_read_only():
    app=FastAPI();app.include_router(create_v14_router());client=TestClient(app)
    r=client.get('/api/v1/research/v14/sources')
    assert r.status_code==200 and len(r.json()['references'])>=10
    assert client.get('/platform/research').status_code==200
    assert client.get('/api/v1/research/v14/gates').json()['site_control_authorized'] is False
    paths=client.get('/openapi.json').json()['paths']
    assert set(paths['/api/v1/research/v14/sources'])=={'get'}
    assert client.post('/api/v1/research/v14/sources').status_code==405

from core.v14_physics_benchmarks import (
    hydro_efficiency_screen, solar_pr_screen, wind_bin_screen,
)

def test_hydro_efficiency_physical_limit():
    output=hydro_efficiency_screen(8000,300,3)
    assert output['physically_plausible'] and output['apparent_efficiency'] < 1
    assert not output['site_validated']

def test_hydro_impossible_eta_detected():
    assert not hydro_efficiency_screen(100000,300,3)['physically_plausible']

def test_hydro_no_flow_rejected():
    with pytest.raises(ValueError):hydro_efficiency_screen(0,0,5)

def test_solar_pr_screen_non_certified():
    report=solar_pr_screen(7000,1000,10)
    assert report['ac_performance_ratio_proxy']==.7
    assert not report['site_validated']

def test_solar_pr_impossible_flag():
    assert not solar_pr_screen(15000,1000,10)['screening_plausible']

def test_solar_pr_invalid():
    with pytest.raises(ValueError):solar_pr_screen(100,0,10)

def test_wind_bins_no_iec_claim():
    report=wind_bin_screen([(7.1,100),(7.2,110),(7.3,120),(9.1,300),(9.2,310),(9.3,320)])
    assert len(report['bins'])==2
    assert report['bins'][0]['mean_power_kw']==110
    assert not report['site_validated']

def test_wind_bins_reject_nan():
    with pytest.raises(ValueError):wind_bin_screen([(float('nan'),100)]*6)

def test_wind_bins_require_coverage():
    with pytest.raises(ValueError):wind_bin_screen([(i,100) for i in range(6)])
