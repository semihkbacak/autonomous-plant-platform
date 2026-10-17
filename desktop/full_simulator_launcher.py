"""Local all-in-one simulator desktop. Native Tkinter GUI, in-process Uvicorn.

Never binds beyond 127.0.0.1. No PLC, SCADA, OT adapters, or real site modes.
The viewer and simulator are bundled in the SAME Python process for PyInstaller.
"""
from __future__ import annotations
import argparse
import json
import os
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,build_opener,HTTPRedirectHandler
from urllib.error import URLError
import webbrowser

BASE='http://127.0.0.1:8000'
SCENARIOS={'GES':['NORMAL','GRID_LOSS','ESTOP','FAULT','LOW_LIGHT','CURTAIL_50'],
           'RES':['NORMAL','GRID_LOSS','ESTOP','FAULT','LOW_WIND','HIGH_WIND','WAKE','CURTAIL_50']}

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def http_json(path, *, method='GET', data=None, timeout=2.0):
    if not (path.startswith('/api/v1/') and '..' not in path):
        raise ValueError('Non-local simulator API path')
    if method not in ('GET','POST'):raise ValueError('Unsupported method')
    headers={'Accept':'application/json'}
    body=None
    if method=='POST':
        body=json.dumps(data).encode('utf-8') if data is not None else b''
        headers.update({'X-Sim-Console-Confirm':'SIMULATION_ONLY','Content-Type':'application/json'})
    req=Request(BASE+path,data=body,headers=headers,method=method)
    with build_opener(NoRedirect()).open(req,timeout=timeout) as r:
        if r.status!=200:raise RuntimeError('Bad server response')
        raw=r.read(256_001)
        if len(raw)>256_000:raise RuntimeError('Unexpected API response size')
        return json.loads(raw)

def _uvicorn_config(app, *, port=8000, log_level='warning'):
    """Use the same console-independent logging for GUI and release smoke tests.

    PyInstaller --windowed may set sys.stdout/sys.stderr to None. Uvicorn's
    default `uvicorn.logging.DefaultFormatter` calls sys.stdout.isatty(),
    which raises ValueError: Unable to configure formatter 'default'.
    No stdout/stderr handler or auto-colour formatter is installed here.
    """
    import uvicorn
    return uvicorn.Config(app, host='127.0.0.1', port=port,
                          access_log=False, log_level=log_level,
                          log_config=None)


def _configure_local_file_logging():
    """Record packaged-server failures without requiring a console handle."""
    log_dir = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'AutonomousPlantPlatform' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    logfile = log_dir / 'local_simulator.log'
    logger = logging.getLogger('uvicorn.error')
    if not any(getattr(h, '_app_owned', False) for h in logger.handlers):
        handler = RotatingFileHandler(logfile, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        handler._app_owned = True
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s: %(message)s'))
        logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    # Other packages may still emit diagnostics to stderr. Never keep
    # a None standard stream in a frozen --windowed application.
    if getattr(sys, 'frozen', False):
        if sys.stdout is None:
            sys.stdout = open(os.devnull, 'w', encoding='utf-8')
        if sys.stderr is None:
            sys.stderr = open(log_dir / 'python_errors.log', 'a', encoding='utf-8', buffering=1)
    return logfile


class LocalServer:
    """The SINGLE embedded server path used by GUI and native EXE smoke test."""
    def __init__(self):
        self.server = None
        self.thread = None
        self._startup_error = None

    def start(self, *, port=8000):
        if self.thread is not None and self.thread.is_alive():
            return False
        _configure_local_file_logging()
        os.environ['APP_OPERATION_MODE'] = 'SIMULATION'
        os.environ['APP_HARDEN_LEGACY'] = '1'
        os.environ['APP_SIM_CONSOLE_WRITES'] = '1'
        if not os.environ.get('GES_HISTORIAN_DB'):
            from tools.prepare_ges_history import default_history_path, ensure_synthetic_ges_history
            target = default_history_path()
            if getattr(sys, 'frozen', False):
                target = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'AutonomousPlantPlatform' / 'demo' / 'ges_synthetic_historian.sqlite3'
            ensure_synthetic_ges_history(target)
            os.environ['GES_HISTORIAN_DB'] = str(target.resolve())
        if not os.environ.get('RES_HISTORIAN_DB'):
            from tools.prepare_res_history import default_history_path as res_default, ensure_synthetic_res_history
            target = res_default()
            if getattr(sys, 'frozen', False):
                target = Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'AutonomousPlantPlatform' / 'demo' / 'res_synthetic_historian.sqlite3'
            ensure_synthetic_res_history(target)
            os.environ['RES_HISTORIAN_DB'] = str(target.resolve())
        from app.main import app
        if port == 8000:
            from socket import socket, AF_INET, SOCK_STREAM
            with socket(AF_INET, SOCK_STREAM) as probe:
                if probe.connect_ex(('127.0.0.1', port)) == 0:
                    raise RuntimeError('Port 8000 is already in use. Close the other service first.')
        self.server = __import__('uvicorn').Server(_uvicorn_config(app, port=port))
        self._startup_error = None
        def run_server():
            try:
                self.server.run()
            except BaseException as exc:
                self._startup_error = exc
                logging.getLogger('uvicorn.error').exception('Local simulator server terminated')
        self.thread = threading.Thread(target=run_server, daemon=True, name='APP-Local-Uvicorn')
        self.thread.start()
        # The GUI worker must not report "started" until localhost is serving.
        # In earlier builds failures in the daemon thread looked like success.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if self._startup_error is not None:
                reason = self._startup_error
                self.stop()
                raise RuntimeError('Local server failed to start; see local_simulator.log') from reason
            if self.server is not None and self.server.started:
                return True
            if self.thread is None or not self.thread.is_alive():
                self.stop()
                raise RuntimeError('Local server exited during startup; see local_simulator.log')
            time.sleep(.1)
        self.stop()
        raise TimeoutError('Local server did not become ready within 20 seconds; see local_simulator.log')

    def stop(self):
        if self.server is not None:
            self.server.should_exit = True
        if self.thread is not None and self.thread.is_alive():
            self.thread.join(timeout=8)
        self.server = None
        self.thread = None


def self_test():
    """Full dependency AND FastAPI import preflight, including frozen EXE.

    Earlier versions only checked URL strings, so a missing Uvicorn library
    passed their EXE self-test and failed after pressing Start.
    """
    _prepare_bundled_runtime()
    import uvicorn
    import fastapi
    import pvlib
    import sklearn
    import openpyxl
    import httpx
    from app.main import app
    from app.sim_runtime import SolarSession, WindSession
    from fastapi import FastAPI
    from app.sim_console_api import create_sim_console_router
    from app.live_twins_v20 import create_live_twins_router
    from app.sim_runtime import SimulatorSessions
    from simulator.hydro import HydroPlantSimulator
    assert BASE == 'http://127.0.0.1:8000'
    assert set(SCENARIOS) == {'GES', 'RES'}
    # Verify the real router constructors independently of app import order.
    # The native --smoke-server below checks the FULL app over actual HTTP.
    probe_app = FastAPI()
    sessions, hydro = SimulatorSessions(), HydroPlantSimulator()
    probe_app.include_router(create_sim_console_router(sessions, hydro))
    probe_app.include_router(create_live_twins_router(sessions, hydro))
    # Exercise the ASGI application instead of introspecting app.routes.
    # New FastAPI versions can store included routers as wrapper objects
    # without a .path attribute, even when endpoints are reachable.
    # A GET-only request also proves the response contract actually works.
    from fastapi.testclient import TestClient
    with TestClient(probe_app) as client:
        for path, expected_scope in (
            ('/api/v1/sim-console/ges', 'SYNTHETIC_IN_MEMORY_NO_OT'),
            ('/api/v1/sim-console/res', 'SYNTHETIC_IN_MEMORY_NO_OT'),
            ('/api/v1/live-twins/state', 'SYNTHETIC_LOCAL_SIMULATION_NOT_A_REAL_TIME_SITE_TWIN'),
        ):
            response = client.get(path)
            if response.status_code != 200:
                raise RuntimeError(f'Simulator API preflight failed: {path}: HTTP {response.status_code}')
            if response.json().get('scope') != expected_scope:
                raise RuntimeError(f'Simulator API preflight scope mismatch: {path}')
        page = client.get('/platform/live-twins')
        if page.status_code != 200 or 'text/html' not in page.headers.get('content-type', ''):
            raise RuntimeError('Synthetic live twins dashboard is not available')
    for bad in ['/../../', '/api/v1/../thing', 'http://example.org/']:
        try:
            http_json(bad)
        except ValueError:
            pass
        else:
            raise AssertionError('Bad URL allowed')
    solar = SolarSession(); wind = WindSession()
    solar.step(); wind.step()
    assert solar.status()['power_series'] and wind.status()['power_series']
    return {'status':'PASS','mode':'LOCAL_SIMULATION_UI','physical_control':False,
            'gui_tested':False,'uvicorn':uvicorn.__version__,
            'fastapi':fastapi.__version__, 'pvlib':pvlib.__version__,
            'solar_twin':'PASS','wind_twin':'PASS', 'bundled':bool(getattr(sys,'frozen',False))}


def smoke_server():
    """Run the SAME managed-server startup as the GUI on an ephemeral port.

    This is the native EXE release gate; independent Uvicorn code paths
    previously passed in build scripts while the real GUI start crashed.
    """
    _prepare_bundled_runtime()
    local = LocalServer()
    local.start(port=0)
    try:
        for _ in range(150):
            if local._startup_error is not None:
                raise RuntimeError('GUI server startup failed') from local._startup_error
            server = local.server
            if server and server.started and server.servers:
                sockets = server.servers[0].sockets
                if sockets:
                    port = sockets[0].getsockname()[1]
                    endpoints = ('/api/v1/sim-console/ges',
                                 '/api/v1/sim-console/res',
                                 '/api/v1/live-twins/state',
                                 '/api/v2/clock/status')
                    opener = build_opener(NoRedirect())
                    states = {}
                    for path in endpoints:
                        with opener.open(Request(f'http://127.0.0.1:{port}{path}', method='GET'), timeout=3) as res:
                            if res.status != 200:
                                raise RuntimeError(f'HTTP self-test failed: {path}: {res.status}')
                            states[path] = json.load(res)
                    if states[endpoints[0]].get('scope') != 'SYNTHETIC_IN_MEMORY_NO_OT':
                        raise RuntimeError('GES synthetic mode check failed')
                    if states[endpoints[1]].get('scope') != 'SYNTHETIC_IN_MEMORY_NO_OT':
                        raise RuntimeError('RES synthetic mode check failed')
                    if states[endpoints[2]].get('scope') != 'SYNTHETIC_LOCAL_SIMULATION_NOT_A_REAL_TIME_SITE_TWIN':
                        raise RuntimeError('Live twin scope check failed')
                    with opener.open(Request(f'http://127.0.0.1:{port}/api/v2/advanced/status', method='GET'), timeout=3) as advanced_response:
                        advanced_status = json.load(advanced_response)
                    if advanced_status.get('scope') != 'SYNTHETIC_RESEARCH_NO_OT':
                        raise RuntimeError('Advanced research portfolio contract failed')
                    if states[endpoints[3]].get('scope') != 'SYNTHETIC_THREE_PLANT_NO_OT':
                        raise RuntimeError('UTC synchronized stage1 contract failed')
                    return {'status':'PASS', 'smoke_server':True,
                            'gui_server_path_checked':True,
                            'endpoints_checked':4, 'physical_control':False}
            if local.thread is None or not local.thread.is_alive():
                raise RuntimeError('Managed Uvicorn exited before accepting requests')
            time.sleep(.1)
        raise RuntimeError('Managed Uvicorn did not start within 15 seconds')
    finally:
        local.stop()


def _prepare_bundled_runtime():
    # PyInstaller onedir resources are read-only application assets.
    # Persist optional research data in the user's profile, never in the bundle.
    if getattr(sys,'frozen',False):
        from pathlib import Path
        base=Path(getattr(sys,'_MEIPASS',Path(sys.executable).parent))
        # PyInstaller --collect-submodules only bundles Python modules, not
        # adjacent SQL resources accessed with Path(__file__).with_name().
        # Validate before the user presses Start, not after a SQLite traceback.
        essential_assets = (
            base/'models'/'hes_anomaly_iforest.joblib',
            base/'simulator'/'solar'/'ges_history_schema.sql',
            base/'app'/'static'/'solar_dashboard.html',
            base/'app'/'static'/'solar_inverter_dashboard.html',
        )
        missing_assets = [item.relative_to(base).as_posix() for item in essential_assets if not item.is_file()]
        if missing_assets:
            raise RuntimeError('Packaged application assets missing: ' + ', '.join(missing_assets) + '. Use the complete FIX11 distribution.')
        os.chdir(base)
        data=Path(os.environ.get('LOCALAPPDATA') or Path.home())/'AutonomousPlantPlatform'/'research'
        data.mkdir(parents=True,exist_ok=True)
        os.environ.setdefault('APP_RESEARCH_DB',str(data/'research.sqlite3'))

def run_gui():
    _prepare_bundled_runtime()
    import tkinter as tk
    from tkinter import ttk,messagebox
    class SimulatorDesktop(tk.Tk):
        def __init__(self):
            super().__init__()
            self.title('Autonomous Plant Platform — HES / GES / RES — Simulation Only')
            self.geometry('1060x710');self.minsize(840,580)
            self.local=LocalServer()
            self.pool=ThreadPoolExecutor(max_workers=2)
            self.pending=None;self.last={};self.trends={p:deque(maxlen=36) for p in ('HES','GES','RES')}
            self.running=False
            self.status=tk.StringVar(value='Local server not started')
            self.note=tk.StringVar(value='SYNTHETIC DATA ONLY · NO FIELD COMMANDS · 127.0.0.1')
            main=ttk.Frame(self,padding=13);main.pack(fill='both',expand=True)
            ttk.Label(main,text='AUTONOMOUS PLANT PLATFORM  |  RESEARCH SIMULATION',font=('Segoe UI',17,'bold')).pack(anchor='w')
            ttk.Label(main,textvariable=self.note,foreground='#98662c').pack(anchor='w',pady=(2,8))
            top=ttk.Frame(main);top.pack(fill='x')
            ttk.Button(top,text='Start local simulator',command=self.start).pack(side='left',padx=3)
            ttk.Button(top,text='Stop managed server',command=self.stop).pack(side='left',padx=3)
            ttk.Button(top,text='Open dashboard',command=lambda:webbrowser.open(BASE+'/platform/dashboard')).pack(side='left',padx=3)
            ttk.Button(top,text='Offline research / API',command=lambda:webbrowser.open(BASE+'/docs')).pack(side='left',padx=3)
            ttk.Button(top,text='GES / RES live twins',command=lambda:webbrowser.open(BASE+'/platform/live-twins')).pack(side='left',padx=3)
            ttk.Button(top,text='HES/GES/RES · UTC synchronized',command=lambda:webbrowser.open(BASE+'/platform/synchronized')).pack(side='left',padx=3)
            ttk.Button(top,text='Advanced physics + decisions',command=lambda:webbrowser.open(BASE+'/platform/advanced-twins')).pack(side='left',padx=3)
            ttk.Label(main,textvariable=self.status).pack(anchor='w',pady=(8,4))
            notebook=ttk.Notebook(main);notebook.pack(fill='both',expand=True)
            self.plants={}
            for plant in ('HES','GES','RES'):
                frame=ttk.Frame(notebook,padding=12);notebook.add(frame,text=f' {plant} synthetic simulator ')
                row=ttk.Frame(frame);row.pack(fill='x')
                value=tk.StringVar(value=f'{plant}: no data')
                ttk.Label(frame,textvariable=value,font=('Segoe UI',13,'bold')).pack(anchor='w',pady=(10,6))
                if plant=='HES':
                    for unit in ('UNIT_1','UNIT_2'):
                        for action in ('start','stop'):
                            ttk.Button(row,text=f'{unit} {action}',command=lambda u=unit,a=action:self.command(
                                '/api/v1/sim-console/hes/unit/'+a, {'unit_id':u})).pack(side='left',padx=2)
                    ttk.Button(row,text='Tick HES',command=lambda:self.command('/api/v1/sim-console/hes/tick')).pack(side='left',padx=3)
                else:
                    for action in ('start','pause','step','reset'):
                        ttk.Button(row,text=action.title(),command=lambda p=plant,a=action:self.command('/api/v1/sim-console/'+p.lower()+'/'+a)).pack(side='left',padx=2)
                    mode=tk.StringVar(value='NORMAL')
                    comb=ttk.Combobox(row,textvariable=mode,values=SCENARIOS[plant],state='readonly',width=14)
                    comb.pack(side='left',padx=4)
                    ttk.Button(row,text='Apply scenario',command=lambda p=plant,m=mode:self.command(
                        '/api/v1/sim-console/'+p.lower()+'/mode',{'mode':m.get()})).pack(side='left',padx=2)
                    if plant=='GES':
                        ttk.Button(row,text='Daylight >>',command=lambda:self.command(
                            '/api/v1/sim-console/ges/daylight')).pack(side='left',padx=2)
                trend=tk.Canvas(frame,bg='#102033',highlightthickness=0,height=290)
                trend.pack(fill='both',expand=True,pady=12)
                self.plants[plant]=(value,trend)
            self.protocol('WM_DELETE_WINDOW',self.close)
            self.after(700,self.refresh)
        def start(self):
            if self.running or getattr(self, '_starting', False):return
            self._starting=True
            self.status.set('Starting local FastAPI server; checking runtime modules ...')
            future=self.pool.submit(self.local.start)
            def complete():
                if not future.done():self.after(150,complete);return
                self._starting=False
                try:
                    self.running=bool(future.result())
                    self.status.set('Local synthetic simulation on 127.0.0.1:8000')
                except Exception as exc:
                    self.status.set('Server failed: '+str(exc))
                    messagebox.showerror('Local-only server',str(exc))
            self.after(150,complete)
        def stop(self):
            self.running=False
            self.local.stop()
            self.status.set('Managed server stopped')
        def command(self,path,data=None):
            if not self.running:
                messagebox.showwarning('SIMULATION ONLY','Start this app-managed local server first.');return
            def work():return http_json(path,method='POST',data=data)
            f=self.pool.submit(work)
            def done():
                if not f.done():self.after(100,done);return
                try:f.result();self.status.set('Synthetic simulator command accepted: '+path.rsplit('/',1)[-1])
                except Exception as exc:self.status.set('Synthetic simulator command rejected: '+str(exc)[:160])
            self.after(100,done)
        def refresh(self):
            if self.running and self.pending is None:
                self.pending=self.pool.submit(lambda:{p:http_json('/api/v1/sim-console/'+p.lower()) for p in ('HES','GES','RES')})
            if self.pending is not None and self.pending.done():
                try:
                    data=self.pending.result();self.last=data
                    for p,entry in data.items():
                        kw=float(entry.get('last_power_kw',0))
                        self.trends[p].append(kw)
                        info=f'{p}  |  {kw:,.1f} kW  |  '+str(entry.get('intervals',0))+' steps  |  '+('RUNNING' if entry.get('running') else 'PAUSED')
                        self.plants[p][0].set(info)
                        self.graph(self.plants[p][1],self.trends[p])
                    self.status.set('Synthetic live data · localhost port 8000')
                except Exception as exc:self.status.set('Waiting for local server: '+str(exc)[:130])
                finally:self.pending=None
            self.after(1000,self.refresh)
        @staticmethod
        def graph(canvas,values):
            canvas.delete('all');width=max(canvas.winfo_width(),200);height=max(canvas.winfo_height(),140)
            canvas.create_text(18,18,text='Last 36 polls / synthetic kW',fill='#cfe8ff',anchor='w')
            series=list(values)
            if len(series)<2:return
            upper=max(max(series)*1.1,1.0)
            xy=[]
            for i,v in enumerate(series):xy.extend((30+(width-60)*i/max(1,len(series)-1),height-30-(height-75)*v/upper))
            canvas.create_line(*xy,fill='#77d6bf',width=2,smooth=True)
            canvas.create_text(26,height-13,anchor='w',fill='#b5cad9',text='0 kW')
            canvas.create_text(width-16,43,anchor='e',fill='#b5cad9',text=f'{upper:,.1f} kW')
        def close(self):
            self.stop();self.pool.shutdown(wait=False,cancel_futures=True);self.destroy()
    SimulatorDesktop().mainloop()


def main(argv=None):
    parser=argparse.ArgumentParser()
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--smoke-server',action='store_true')
    args=parser.parse_args(argv)
    if args.self_test:
        print(json.dumps(self_test(),sort_keys=True));return 0
    if args.smoke_server:
        print(json.dumps(smoke_server(),sort_keys=True));return 0
    run_gui();return 0

if __name__=='__main__':raise SystemExit(main())
