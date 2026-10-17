"""New v2.0 research, safety-boundary and distribution tests."""
from __future__ import annotations
import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
import pytest
from fastapi.testclient import TestClient

from research_v2.workspace import ResearchStore
from research_v2.engine import ScreeningConfig,iterate_synthetic,run_into_store
from research_v2.benchmarks import chronological_holdout
from research_v2.provenance import validate_offline_csv
from desktop.full_simulator_launcher import self_test,http_json


def test_common_utc_three_plants_and_multi_day():
    cfg=ScreeningConfig(start_utc='2026-06-21T00:00:00Z',days=2,step_s=900)
    a={plant:list(iterate_synthetic(plant,cfg)) for plant in ('HES','GES','RES')}
    assert all(len(rows)==192 for rows in a.values())
    assert a['HES'][-1]['utc']==a['GES'][-1]['utc']==a['RES'][-1]['utc']
    assert a['HES'][0]['energy_kwh']>0
    assert a['GES'][0]['energy_kwh']==0
    assert all(x['source_kind']=='SYNTHETIC_SCREENING_NOT_OEM' for x in a['RES'])


def test_resumable_store_deterministic_and_atomic(tmp_path):
    db=tmp_path/'runs.sqlite3';st=ResearchStore(db)
    cfg=ScreeningConfig('2026-01-01T00:00:00Z',days=3)
    st.create('s01','site01','GES','NORMAL',cfg.start_utc,cfg.step_s)
    first=run_into_store(st,'s01',cfg,limit=10)
    assert len(first['samples'])==10
    assert len(run_into_store(ResearchStore(db),'s01',cfg,limit=10)['samples'])==20
    again=run_into_store(ResearchStore(db),'s01',cfg,limit=500)
    assert len(again['samples'])==288
    assert len(run_into_store(st,'s01',cfg,limit=100)['samples'])==288
    reference=list(iterate_synthetic('GES',cfg))
    assert [s['power_kw'] for s in again['samples']]==[v['power_kw'] for v in reference]


def test_atomic_concurrent_duplicate_step(tmp_path):
    st=ResearchStore(tmp_path/'sync.sqlite3')
    st.create('t','site','HES','NORMAL','2026-01-01T00:00:00Z')
    def writer(_):
        try:st.add('t',0,100);return True
        except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(writer,range(2)))
    assert sorted(results)==[False,True]
    assert len(st.get('t')['samples'])==1


def test_xlsx_bytes_and_formula_sanitization(tmp_path):
    st=ResearchStore(tmp_path/'s.sqlite3')
    st.create('xlsx','solar','GES','=HYPERLINK("https://bad.invalid")','2026-01-01T00:00:00Z')
    st.add('xlsx',0,25)
    assert "'=HYPERLINK" in st.export_csv('xlsx')
    from openpyxl import load_workbook
    book=load_workbook(BytesIO(st.export_xlsx('xlsx')),read_only=True)
    assert book['Synthetic samples']['D2'].value.startswith("'=HYPERLINK")
    assert book['Readme']['A1'].value.startswith('SIMULATION')


def test_input_screening_and_invalid_limits():
    with pytest.raises(ValueError):ScreeningConfig('2026-01-01',days=0)
    with pytest.raises(ValueError):ScreeningConfig('2026-01-01T00:00:00Z',res_cp=.9)
    with pytest.raises(ValueError):list(iterate_synthetic('HES',ScreeningConfig('2026-01-01T00:00:00Z'),from_step=-1))
    with pytest.raises(ValueError):ScreeningConfig('2026-01-01T00:00:00Z',step_s=7)


def test_readonly_csv_validation_source_is_not_approval():
    raw=(b'site_id,timestamp_utc,power_kw,quality\n'
         b'site1,2026-01-01T00:00:00Z,100,GOOD\n'
         b'site1,2026-01-01T00:15:00Z,200,GOOD\n')
    report=validate_offline_csv(raw,expected_site_id='site1',source_label='user-export',calibrated=True)
    assert report['sha256']==hashlib.sha256(raw).hexdigest()
    assert report['claimed_calibrated'] is True
    assert report['independently_verified'] is False
    assert report['status'].startswith('QUARANTINED')
    with pytest.raises(ValueError):validate_offline_csv(raw.replace(b'GOOD\nsite1',b'BAD\nsite1'),expected_site_id='site1',source_label='source')
    with pytest.raises(ValueError):validate_offline_csv(raw.replace(b'00:15:00',b'00:00:00'),expected_site_id='site1',source_label='source')


def test_holdout_chronological_not_leaking():
    pred=[10.,20.,30.,40.,50.,60.,70.,80.]
    real=[20.,40.,60.,80.,100.,120.,140.,160.]
    report=chronological_holdout(pred,real)
    assert report['scale']==2.0
    assert report['test_n']==2
    assert report['mae_kw']==0
    assert report['site_validated'] is False
    with pytest.raises(ValueError):chronological_holdout([10.]*4,[20.]*4)


def test_desktop_headless_no_remote_open():
    assert self_test()['status']=='PASS'
    assert self_test()['physical_control'] is False
    with pytest.raises(ValueError):http_json('https://evil.invalid/')


def test_research_api_local_only_and_shadow_read_only(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_RESEARCH_DB',str(tmp_path/'sample.sqlite3'))
    monkeypatch.setenv('APP_OPERATION_MODE','SIMULATION')
    from app.main import app
    with TestClient(app) as client:
        caps=client.get('/api/v2/research/capabilities').json()
        assert caps['real_control_ready'] is False
        p={'session_id':'test01','site_id':'site','plant':'GES','scenario':'LOW_LIGHT',
           'start_utc':'2026-06-21T00:00:00Z','step_s':900}
        r=client.post('/api/v2/research/sessions',json=p)
        assert r.status_code==200, r.text
        run=client.post('/api/v2/research/sessions/test01/run-offline',json={'start_utc':p['start_utc'],'days':1},params={'limit':3})
        assert run.status_code==200,run.text
        assert len(run.json()['samples'])==3
        report=client.get('/api/v2/research/sessions/test01/export.xlsx')
        assert report.status_code==200 and report.content[:2]==b'PK'
        shadow_path='/api/v2/research/sessions'
        monkeypatch.setenv('APP_OPERATION_MODE','SHADOW')
        deny=client.post(shadow_path,json=p)
        assert deny.status_code==403
        assert client.get('/api/v2/research/capabilities').status_code==200
