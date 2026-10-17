"""Local FastAPI surface for stages 2-5, explicitly synthetic and not OT."""
from __future__ import annotations

from functools import lru_cache
from io import StringIO
import csv
import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from advanced_v2.controller import Controller,default_path
from advanced_v2.engine import ResearchConfig
from advanced_v2.validation import chronological_holdout,forecast,scenario_comparison
from app.site_guard import operation_mode


@lru_cache(maxsize=2)
def _cached(path):return Controller(path)


def get_controller():return _cached(os.environ.get('APP_ADVANCED_DB',str(default_path())))


class CreateInput(BaseModel):
    start_utc: str = Field(default='2026-01-01T00:00:00+00:00',max_length=40)
    days: int=Field(default=2,ge=1,le=31)
    demand_kw: float=Field(default=2500.0,ge=0,le=100000)
    pv_blocks:int=Field(default=300,ge=1,le=10000)
    mppt:str='INC_COND'
    weather_mode:str='NORMAL'
    shade_profile:str='NONE'
    solar_fault:str='NONE'
    wind_fault:str='NONE'
    hydro_fault:str='NONE'
    site_label:str=Field(default='SYNTHETIC_LAB',max_length=48)


class StepInput(BaseModel):
    count:int=Field(default=1,ge=1,le=96)


class ChangeInput(BaseModel):
    label:str=Field(max_length=48)
    changes:dict[str,str|float|int]=Field(default_factory=dict)


class ComparisonInput(BaseModel):
    alternatives:list[ChangeInput]=Field(min_length=1,max_length=5)
    steps:int=Field(default=8,ge=1,le=96)


class Observation(BaseModel):
    utc_end:str
    power_kw:float=Field(ge=0)
    quality:str='GOOD'
    unit:str='kW'


class ValidateInput(BaseModel):
    plant:str
    source_label:str=Field(min_length=3,max_length=80)
    observations:list[Observation]=Field(min_length=10,max_length=2000)


def local_gate(request:Request,confirmation:str|None):
    if operation_mode()!='SIMULATION':raise HTTPException(403,'SIMULATION mode must be explicitly selected')
    if request.client is None or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Localhost only')
    if confirmation!='SYNTHETIC_ONLY':raise HTTPException(403,'X-Synthetic-Confirm required')
    origin=request.headers.get('origin')
    if origin:
        uri=urlsplit(origin)
        if uri.scheme not in ('http','https') or uri.hostname not in ('127.0.0.1','localhost','::1') or uri.port!=request.url.port:
            raise HTTPException(403,'Foreign browser origin rejected')


def create_router(controller:Controller|None=None):
    router=APIRouter(tags=['Stages 2-5 — Synthetic physics and decision support'])
    def runtime():return controller if controller is not None else get_controller()
    def guarded(fn):
        try:return fn()
        except (ValueError,RuntimeError,FileExistsError) as exc:
            raise HTTPException(409,str(exc)) from exc

    @router.get('/api/v2/advanced/status')
    def status():return runtime().status()

    @router.get('/api/v2/advanced/history')
    def history(limit:int=Query(180,ge=1,le=10000),after:int=Query(-1,ge=-1),run_id:str|None=Query(None,min_length=32,max_length=32)):
        return {'scope':'SYNTHETIC_RESEARCH_NO_OT','steps':runtime().history(limit,after,run_id)}

    @router.get('/api/v2/advanced/references')
    def references():
        from advanced_v2.references import independent_law_checks,pvlib_standard_irradiance_check
        return {'analytical':independent_law_checks(),'pvlib':pvlib_standard_irradiance_check()}

    @router.get('/api/v2/advanced/optimize')
    def optimize(horizon:int=Query(8,ge=1,le=96)):
        from advanced_v2.optimization import optimize_water_budget
        c=runtime()
        if not c.engine:raise HTTPException(409,'Create research run first')
        history=c.history(96)
        if len(history)<1:raise HTTPException(409,'No research history')
        last=history[-horizon:]
        demand=[x['dispatch']['demand_kw'] for x in last]
        variable=[x['rows']['GES']['power_kw']+x['rows']['RES']['power_kw'] for x in last]
        state=c.engine.hydro.state
        # Retain a demonstration minimum storage reserve; not a plant policy.
        available_water=max(0,state.reservoir_m3-380_000)
        return optimize_water_budget(demand,variable,available_water_m3=available_water,
                                     net_head_m=last[-1]['rows']['HES']['net_head_m'])

    @router.get('/api/v2/advanced/runs')
    def runs():return {'runs':runtime().journal.runs()}

    @router.get('/api/v2/advanced/export.csv')
    def export(run_id:str|None=Query(None,min_length=32,max_length=32)):
        c=runtime();rows=c.history(10000,run_id=run_id)
        f=StringIO();writer=csv.writer(f,lineterminator='\n')
        writer.writerow(['utc_start','utc_end','site_label','plant','power_kw','energy_kwh','scope'])
        for item in rows:
            for plant,payload in sorted(item['rows'].items()):
                writer.writerow([item['utc_start'],item['utc_end'],item['site_label'],plant,
                                 payload['power_kw'],payload['energy_kwh'],'SYNTHETIC_RESEARCH_NO_OT'])
        return Response(f.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="advanced_synthetic_portfolio.csv"'})

    @router.get('/api/v2/advanced/forecast')
    def predict(horizon:int=Query(8,ge=1,le=96)):
        c=runtime()
        if c.engine is None:raise HTTPException(409,'Create a research run first')
        return guarded(lambda:forecast(c.history(12,after=max(-1,c.engine.index-13))[-12:],horizon))

    @router.post('/api/v2/advanced/create')
    def create(data:CreateInput,request:Request,x_synthetic_confirm:str|None=Header(None)):
        local_gate(request,x_synthetic_confirm)
        return guarded(lambda:runtime().create(ResearchConfig(**data.model_dump())))

    @router.post('/api/v2/advanced/step')
    def step(data:StepInput,request:Request,x_synthetic_confirm:str|None=Header(None)):
        local_gate(request,x_synthetic_confirm)
        return guarded(lambda:runtime().advance(data.count))

    @router.post('/api/v2/advanced/start')
    def start(request:Request,x_synthetic_confirm:str|None=Header(None)):
        local_gate(request,x_synthetic_confirm);return guarded(runtime().start)

    @router.post('/api/v2/advanced/pause')
    def pause(request:Request,x_synthetic_confirm:str|None=Header(None)):
        local_gate(request,x_synthetic_confirm);return guarded(runtime().pause)

    @router.post('/api/v2/advanced/compare')
    def compare(data:ComparisonInput,request:Request,x_synthetic_confirm:str|None=Header(None)):
        local_gate(request,x_synthetic_confirm)
        c=runtime()
        if not c.engine:raise HTTPException(409,'Create a research run first')
        alts=[x.model_dump() for x in data.alternatives]
        return guarded(lambda:scenario_comparison(c.engine.config,alts,data.steps))

    @router.post('/api/v2/advanced/holdout')
    def holdout(data:ValidateInput,request:Request,x_synthetic_confirm:str|None=Header(None)):
        local_gate(request,x_synthetic_confirm)
        c=runtime();obs=[x.model_dump() for x in data.observations]
        return guarded(lambda:chronological_holdout(c.history(10000),obs,plant=data.plant,source_label=data.source_label))

    @router.get('/platform/advanced-twins',response_class=HTMLResponse)
    def page():return ADVANCED_HTML
    return router


ADVANCED_HTML=r'''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Advanced Digital Twin Research — HES · GES · RES</title><style>
:root{color-scheme:dark}*{box-sizing:border-box}body{background:#0c1322;color:#e6edf7;font:14px system-ui,Arial;margin:0}
header{padding:23px max(20px,calc((100vw - 1230px)/2));background:#15253a;border-bottom:1px solid #344765}
header strong{font-size:23px}h2{font-size:17px}p,.muted{color:#afc1d9}a{color:#68dcd0}
main{max-width:1280px;margin:auto;padding:22px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.card{border:1px solid #344a67;border-radius:12px;background:#17273b;padding:16px;min-width:0}.wide{grid-column:span 3}
select,input,button{border-radius:7px;border:1px solid #44627c;padding:9px;background:#0e1d30;color:#e7f3ff;max-width:100%}
button{background:#204d68;cursor:pointer;margin:2px}button:hover{background:#267187}
.controls{display:flex;flex-wrap:wrap;align-items:center;gap:8px}label{display:inline-flex;flex-direction:column;gap:5px;color:#bed0e5;font-size:12px}
.value{font-size:29px;font-weight:650}.notice{color:#facf8e}canvas{display:block;width:100%;height:160px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;color:#a9dbdd}
@media(max-width:850px){.grid{grid-template-columns:1fr}.wide{grid-column:span 1}}
</style></head><body>
<header><div><strong>HES · GES · RES — Advanced Research Twin</strong><p>Stages 2–5 · Synchronized 15 min UTC · Physics, forecast, decision support · <b class="notice">SYNTHETIC ONLY — NO REAL PLANT CONTROL</b></p>
<a href="/platform/synchronized">Aşama 1'e dön</a> · <a href="/platform/dashboard">Ana panele dön</a></div></header>
<main><section class="card"><h2>Çok günlük araştırma senaryosu</h2><div class="controls">
<label>Gün<input id="days" type="number" value="2" min="1" max="31"/></label>
<label>Talep kW<input id="demand" type="number" value="2500" min="0" max="100000"/></label>
<label>GES MPPT<select id="mppt"><option>INC_COND</option><option>PO</option><option>GLOBAL</option></select></label>
<label>Gölgeleme<select id="shade"><option>NONE</option><option>PARTIAL</option><option>HEAVY</option></select></label>
<label>Hava<select id="weather"><option>NORMAL</option><option>CLOUDY</option><option>STORM</option></select></label>
<button onclick="newRun()">Yeni sentetik oturum</button><button onclick="step(1)">15 dk ilerle</button><button onclick="step(96)">1 gün ilerle</button>
<button onclick="action('start')">Otomatik başlat</button><button onclick="action('pause')">Duraklat</button>
<a href="/api/v2/advanced/export.csv">CSV indir</a></div><p id="status" class="muted">Yükleniyor...</p><p id="error" class="notice"></p></section>
<section class="grid" style="margin-top:16px">
<div class="card"><h2>HES · Hidrolik + governor</h2><div id="hes" class="value">—</div><p id="hes_detail" class="muted"></p><canvas id="hchart" width="360" height="160"></canvas></div>
<div class="card"><h2>GES · PV I–V / MPPT</h2><div id="ges" class="value">—</div><p id="ges_detail" class="muted"></p><canvas id="gchart" width="360" height="160"></canvas><div class="muted">P–V eğrisi (tek sentetik 1 kW blok)</div><canvas id="ivchart" width="360" height="160"></canvas></div>
<div class="card"><h2>RES · Rotor / pitch / yaw</h2><div id="res" class="value">—</div><p id="res_detail" class="muted"></p><canvas id="rchart" width="360" height="160"></canvas></div>
<div class="card wide"><h2>Ortak karar destek ve fizik doğruluk kontrolleri</h2><pre id="decisions">Veri yok</pre><h2>Kısa dönem tahmin</h2><pre id="forecast">Dört zaman adımından sonra tahmin oluşturulur</pre><h2>Su bütçesi araştırma optimizasyonu</h2><button onclick="optimize()">Su bütçeli üretim planla</button><pre id="optimization">Optimizasyon çalıştırılmadı</pre><h2>Senaryo karşılaştırması</h2><button onclick="compare()">Normal / bulutlu / gölgeli karşılaştır</button><pre id="compare">Karşılaştırma çalıştırılmadı</pre></div>
</section></main>
<script>
const Q=id=>document.getElementById(id);const H={'Content-Type':'application/json','X-Synthetic-Confirm':'SYNTHETIC_ONLY'};
async function req(url,payload){const r=await fetch(url,payload?{method:'POST',headers:H,body:JSON.stringify(payload)}:{cache:'no-store'});
let j=await r.json();if(!r.ok)throw Error(j.detail||'HTTP '+r.status);return j}
async function call(fn){try{Q('error').textContent='';await fn();await refresh()}catch(e){Q('error').textContent=String(e.message||e)}}
function newRun(){const d=new Date();d.setUTCHours(0,0,0,0);return call(()=>req('/api/v2/advanced/create',{
start_utc:d.toISOString(),days:+Q('days').value,demand_kw:+Q('demand').value,pv_blocks:300,
mppt:Q('mppt').value,shade_profile:Q('shade').value,weather_mode:Q('weather').value,site_label:'SYNTHETIC_LAB'}))}
function step(count){return call(()=>req('/api/v2/advanced/step',{count}))}
function action(name){return call(()=>req('/api/v2/advanced/'+name,{}))}
function draw(id,series,color){let c=Q(id),x=c.getContext('2d');x.clearRect(0,0,c.width,c.height);
x.strokeStyle='#375472';x.beginPath();x.moveTo(5,150);x.lineTo(356,150);x.stroke();if(!series.length)return;
let max=Math.max(0.1,...series),count=Math.max(1,series.length-1);x.strokeStyle=color;x.lineWidth=2;x.beginPath();
series.forEach((v,i)=>{let px=6+i*348/count,py=148-135*v/max;if(i)x.lineTo(px,py);else x.moveTo(px,py)});x.stroke();}
async function refresh(){try{let s=await req('/api/v2/advanced/status');Q('status').textContent='Durum: '+s.state+' | UTC: '+(s.utc||'—')+' | Adım: '+(s.index||0)+'/'+(s.max_steps||0)+' | Veri kaynağı: sentetik';
if(!s.latest)return;let r=s.latest.rows;Q('hes').textContent=r.HES.power_kw.toFixed(1)+' kW';Q('ges').textContent=r.GES.power_kw.toFixed(1)+' kW';Q('res').textContent=r.RES.power_kw.toFixed(1)+' kW';
Q('hes_detail').textContent='Net düşü '+r.HES.net_head_m+' m · Debi '+r.HES.nozzle_m3s+' m³/s · Frekans '+r.HES.frequency_hz+' Hz · Basınç değişimi '+r.HES.max_joukowsky_bar+' bar';
Q('ges_detail').textContent='Işınım '+r.GES.irradiance_wm2+' W/m² · Panel '+r.GES.cell_temperature_c+' °C · '+r.GES.mppt+' · '+r.GES.voltage_v+' V';
Q('res_detail').textContent='Rüzgâr '+r.RES.wind_ms+' m/s · Pitch '+r.RES.turbines[0].pitch_deg+'° · Rotor '+r.RES.turbines[0].rotor_rpm+' rpm';
Q('decisions').textContent=JSON.stringify({dispatch:s.latest.dispatch,anomalies:s.latest.anomalies,independent_bounds:s.latest.independent_bounds},null,2);
let data=(await req('/api/v2/advanced/history?limit=96&after='+Math.max(-1,(s.index||0)-97))).steps;
for(let [p,id,color] of [['HES','hchart','#4ebbed'],['GES','gchart','#ebbb58'],['RES','rchart','#64c6a6']])draw(id,data.map(x=>x.rows[p].power_kw),color);
draw('ivchart',r.GES.iv_curve.map(x=>x.p),'#ebbb58');
if(data.length>=4){try{let f=await req('/api/v2/advanced/forecast?horizon=4');Q('forecast').textContent=JSON.stringify(f.forecasts,null,2)}catch(e){Q('forecast').textContent=e.message}}
}catch(e){Q('error').textContent=e.message}}
function optimize(){return call(async()=>{let r=await req('/api/v2/advanced/optimize?horizon=16');Q('optimization').textContent=JSON.stringify(r,null,2)})}
function compare(){return call(async()=>{let c=await req('/api/v2/advanced/compare',{steps:16,alternatives:[{label:'cloudy',changes:{weather_mode:'CLOUDY'}},{label:'shaded',changes:{shade_profile:'PARTIAL'}}]});Q('compare').textContent=JSON.stringify(c.results,null,2)})}
refresh();setInterval(refresh,3000);
</script></body></html>'''
