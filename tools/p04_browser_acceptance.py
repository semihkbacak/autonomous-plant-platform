"""Optional live browser smoke test of P04's actual HTML and synthetic API.

Requires playwright and an installed Chromium; not part of the product dependencies.
Never connects to or controls a real plant.
"""
from __future__ import annotations
import argparse
import importlib.util
import os
from pathlib import Path
import socket
import tempfile
import threading
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument('--screenshot',default=None)
    parser.add_argument('--chromium',default=None)
    opt=parser.parse_args()
    os.environ['APP_OPERATION_MODE']='SIMULATION'
    from fastapi import FastAPI
    from stage1.api import create_router
    from stage1.controller import Coordinator
    from fastapi.testclient import TestClient
    from stage1.api import HTML
    from playwright.sync_api import sync_playwright

    spec=importlib.util.spec_from_file_location('p04_acceptance_fixtures',ROOT/'tests/test_p04_dashboard_operational.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='app_p04_browser_') as temp:
        c=Coordinator(Path(temp)/'browser.sqlite3',module.Solar,module.Wind)
        app=FastAPI();app.include_router(create_router(c))
        with TestClient(app) as client, sync_playwright() as pw:
            browser=pw.chromium.launch(headless=True,executable_path=opt.chromium,
                    args=['--no-sandbox'] if opt.chromium else [])
            page=browser.new_page(viewport={'width':1280,'height':960})
            errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            # Chromium in this sandbox is blocked from visiting localhost.
            # Use genuine browser JS/DOM and route fetch to the actual FastAPI
            # TestClient process, preserving methods/headers/JSON/SQLite behavior.
            def api_bridge(source,request):
                r=client.request(request.get('method','GET'),request['url'],
                    headers=request.get('headers') or {},content=request.get('body'))
                return {'ok':r.is_success,'status':r.status_code,'body':r.text}
            page.expose_binding('bridgeApi',api_bridge)
            page.evaluate('''window.fetch=async (url,opts={})=>{
                const r=await window.bridgeApi({url:String(url),method:opts.method||'GET',
                   headers:opts.headers||{},body:opts.body||null});
                return {ok:r.ok,status:r.status,text:async()=>r.body,
                    json:async()=>JSON.parse(r.body)};
            }''')
            page.set_content(HTML,wait_until='load')
            page.get_by_text('henüz oturum oluşturulmadı').wait_for(timeout=15000)
            assert c.run_id is None
            page.locator('#start').click()
            page.get_by_text('Başarılı: start').wait_for(timeout=12000)
            assert c.state=='RUNNING' and c.run_id
            page.locator('#pause').click()
            page.get_by_text('Başarılı: pause').wait_for(timeout=10000)
            page.locator('#pPlant').select_option('GES')
            page.locator('#pKw').fill('12')
            page.locator('#pGran').select_option('60')
            page.locator('#pSave').click()
            page.get_by_text('Başarılı: plan').wait_for(timeout=10000)
            assert len(c.journal.plans(c.run_id))==1
            page.locator('#pManual').click()
            page.get_by_text('Başarılı: setpoint').wait_for(timeout=10000)
            page.locator('#step').click()
            page.get_by_text('Başarılı: step').wait_for(timeout=10000)
            assert c.engine.index==1
            assert c.status()['latest']['GES']['power_kw']==12
            assert not errors,errors
            if opt.screenshot:page.screenshot(path=opt.screenshot,full_page=True)
            browser.close()
    print('P04 browser smoke: PASS (first-click Start, Pause, plan, setpoint, +15m, SQLite)')
    return 0

if __name__=='__main__':raise SystemExit(main())
