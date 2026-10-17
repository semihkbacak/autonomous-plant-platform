"""Fresh-browser lifecycle and API integration for P04 (synthetic only).

The browser harness in tools/p04_browser_acceptance.py can additionally be run
when a desktop/browser is available; it is not required in the dependency set.
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from stage1.api import create_router
from stage1.controller import Coordinator
from app.sim_runtime import SolarSession, WindSession

class Solar(SolarSession):
    def _prepare(self): self._engine=object()
    def _compute(self, i):
        return {'power_kw':20.0,'energy_kwh':5.0,'end_utc':'2026-01-01T00:15:00+00:00',
                'units':[{'id':'INV_1','kw':20.0,'status':'SYNTHETIC'}],
                'conditions':{'irradiance_ghi_w_m2':700.0,'source':'SYNTHETIC_TEST'}}

class Wind(WindSession):
    def _prepare(self): self._engine=object()
    def _compute(self, i):
        return {'power_kw':80.0,'energy_kwh':20.0,'end_utc':'2026-01-01T00:15:00+00:00',
                'units':[{'id':'WT_1','kw':80.0,'status':'SYNTHETIC'}],
                'conditions':{'wind_speed_m_s':8.0,'source':'SYNTHETIC_TEST'}}

HEAD={'X-Synthetic-Confirm':'SYNTHETIC_ONLY'}

def test_fresh_dashboard_complete_api_journey(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_OPERATION_MODE','SIMULATION')
    c=Coordinator(tmp_path/'fresh.sqlite3',Solar,Wind)
    app=FastAPI()
    app.include_router(create_router(c))
    with TestClient(app) as client:
        assert client.get('/api/v2/clock/status').json()['state']=='NOT_CREATED'
        build=client.get('/api/v2/clock/build').json()
        assert build['build']=='UTC_DISPATCH_P04' and build['physical_control'] is False
        html=client.get('/platform/synchronized').text
        assert 'async function ensureRun()' in html
        assert 'await ensureRun()' in html
        assert 'P04' in html
        assert client.post('/api/v2/clock/start',headers=HEAD).status_code==409  # raw API intentionally guarded
        created=client.post('/api/v2/clock/create',headers=HEAD,
            json={'start_utc':'2026-01-01T00:00:00+00:00','days':2})
        assert created.status_code==200,created.text
        run=created.json()['run_id']
        assert client.post('/api/v2/clock/plan',headers=HEAD,json={
            'plant':'GES','start_utc':'2026-01-01T00:00:00Z',
            'end_utc':'2026-01-01T01:00:00Z','target_kw':15.0,'interval_minutes':60}).status_code==200
        assert client.post('/api/v2/clock/setpoint',headers=HEAD,json={'plant':'GES','kw':7.0}).status_code==200
        started=client.post('/api/v2/clock/start',headers=HEAD)
        assert started.status_code==200 and started.json()['state']=='RUNNING'
        one=client.post('/api/v2/clock/step',headers=HEAD,json={'count':1})
        assert one.status_code==200,one.text
        latest=one.json()['latest']
        assert latest['GES']['power_kw']==7.0
        assert latest['GES']['conditions']['dispatch']['available_export_kw']==20.0
        assert client.get('/api/v2/clock/history').json()['samples']
        assert len(client.get('/api/v2/clock/plan-report').json()['report'])==1
        assert client.get('/api/v2/clock/dispatch-audit').json()['events']
        assert 'GES' in client.get('/api/v2/clock/export.csv').text
        paused=client.post('/api/v2/clock/pause',headers=HEAD)
        assert paused.status_code==200 and paused.json()['state']=='PAUSED'
        restored=Coordinator(tmp_path/'fresh.sqlite3',Solar,Wind)
        assert restored.run_id==run and restored.status()['index']==1

def test_shadow_dashboard_readonly(tmp_path,monkeypatch):
    monkeypatch.setenv('APP_OPERATION_MODE','SHADOW')
    c=Coordinator(tmp_path/'shadow.sqlite3',Solar,Wind)
    app=FastAPI();app.include_router(create_router(c))
    with TestClient(app) as client:
        assert client.get('/api/v2/clock/build').json()['mode']=='SHADOW'
        assert client.post('/api/v2/clock/create',headers=HEAD,json={
            'start_utc':'2026-01-01T00:00:00Z','days':1}).status_code==403
        assert c.state=='NOT_CREATED'

def test_p04_frontend_is_explicit_and_server_identity_checked():
    from stage1.api import HTML
    assert "post('create',newRunParameters())" in HTML
    assert "$('start').onclick=()=>cmd('start')" in HTML
    assert "$('step').onclick=()=>cmd('step',{count:1})" in HTML
    assert "async function verifyBuild()" in HTML
    assert "planStartEdited" in HTML
    assert "content='" not in HTML  # ensure no injected remote dependency

def test_windows_start_refuses_existing_server_first():
    src=(Path(__file__).resolve().parents[1]/'windows/windows_start.py').read_text(encoding='utf-8')
    assert "check.connect_ex(('127.0.0.1', 8000))" in src
    assert "info.get('build')=='UTC_DISPATCH_P04'" in src

