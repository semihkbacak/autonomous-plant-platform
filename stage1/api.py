"""Local-only API and single-clock research dashboard. No field command API."""
from __future__ import annotations

from functools import lru_cache
import csv
from io import StringIO
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request, Query
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from stage1.controller import Coordinator, default_path
from stage1.engine import ClockConfig
from app.site_guard import operation_mode


def get_coordinator() -> Coordinator:
    """Lazily read a single path, no DB created by importing application."""
    return _coordinator_cached(os.environ.get('APP_STAGE1_DB',str(default_path())))


@lru_cache(maxsize=2)
def _coordinator_cached(path):
    return Coordinator(path)


class NewRun(BaseModel):
    start_utc: str = Field(max_length=40)
    days: int = Field(ge=1,le=31)


class Steps(BaseModel):
    count: int = Field(ge=1,le=96)


class Mode(BaseModel):
    plant: str
    mode: str


class ProductionPlan(BaseModel):
    plant: str
    start_utc: str
    end_utc: str
    target_kw: float
    interval_minutes: int = 15

class ManualPower(BaseModel):
    plant: str
    kw: float | None = None

class OperatorCommand(BaseModel):
    plant: str
    operation: str

class Speed(BaseModel):
    mode: str

class PlanRemoval(BaseModel):
    id: int = Field(ge=1)

def write_gate(request:Request, confirm:str|None):
    if operation_mode()!='SIMULATION':
        raise HTTPException(403,'Explicit SIMULATION mode required; SHADOW remains read-only')
    if request.client is None or request.client.host not in ('127.0.0.1','::1','testclient'):
        raise HTTPException(403,'Local access only')
    if confirm!='SYNTHETIC_ONLY':
        raise HTTPException(403,'Synthetic-only confirmation required')
    origin=request.headers.get('origin')
    if origin:
        from urllib.parse import urlsplit
        from_port=urlsplit(origin)
        if from_port.scheme not in ('http','https') or from_port.hostname not in ('localhost','127.0.0.1','::1') or from_port.port!=request.url.port:
            raise HTTPException(403,'Foreign origin')


def create_router(controller:Coordinator|None=None):
    router=APIRouter(tags=['Stage 1 — synchronized synthetic research'])
    def runtime():return controller if controller is not None else get_coordinator()

    @router.get('/api/v2/clock/build')
    def build():
        return {'build':'UTC_DISPATCH_P04','scope':'SYNTHETIC_THREE_PLANT_NO_OT',
                'mode':operation_mode(),'physical_control':False}

    @router.get('/api/v2/clock/status')
    def status():return runtime().status()

    @router.get('/api/v2/clock/history')
    def history(limit:int=Query(300,ge=1,le=10000),after:int=Query(-1,ge=-1),run_id:str|None=Query(None,min_length=32,max_length=32)):
        c=runtime()
        rid=run_id or c.run_id
        if not rid:return {'scope':'SYNTHETIC_THREE_PLANT_NO_OT','samples':[]}
        return {'scope':'SYNTHETIC_THREE_PLANT_NO_OT','samples':c.journal.samples(rid,limit,after)}

    @router.get('/api/v2/clock/runs')
    def runs():return {'runs':runtime().journal.summaries()}

    @router.get('/api/v2/clock/export.csv')
    def export_csv(run_id:str|None=Query(None,min_length=32,max_length=32)):
        c=runtime()
        rid=run_id or c.run_id
        rows=c.journal.samples(rid,limit=10000) if rid else []
        buff=StringIO()
        w=csv.writer(buff,lineterminator='\n')
        w.writerow(['run_id','step','plant','utc_start','utc_end','power_kw','energy_kwh','cumulative_kwh','scope','requested_kw','scheduled_kw','available_kw','deviation_kwh','reason'])
        for row in rows:
            w.writerow([rid,row['step_index'],row['plant'],row['utc_start'],row['utc_end'],
                        row['power_kw'],row['energy_kwh'],row['total_kwh'],'SYNTHETIC_THREE_PLANT_NO_OT',
                        row.get('conditions',{}).get('dispatch',{}).get('requested_kw'),
                        row.get('conditions',{}).get('dispatch',{}).get('scheduled_kw'),
                        row.get('conditions',{}).get('dispatch',{}).get('available_export_kw'),
                        row.get('conditions',{}).get('dispatch',{}).get('deviation_kwh'),
                        row.get('conditions',{}).get('dispatch',{}).get('reason')])
        return Response(buff.getvalue(),media_type='text/csv; charset=utf-8',
                        headers={'Content-Disposition':'attachment; filename="stage1_synthetic_utc.csv"'})

    def guard(call):
        try:return call()
        except (ValueError,RuntimeError) as exc:
            raise HTTPException(409,str(exc)) from exc

    @router.post('/api/v2/clock/create')
    def create(body:NewRun,request:Request,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().create(ClockConfig(body.start_utc,body.days)))

    @router.post('/api/v2/clock/start')
    def start(request:Request,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(runtime().start)

    @router.post('/api/v2/clock/pause')
    def pause(request:Request,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(runtime().pause)

    @router.post('/api/v2/clock/step')
    def step(request:Request,body:Steps,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().advance(body.count))

    @router.post('/api/v2/clock/mode')
    def mode(request:Request,body:Mode,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().set_mode(body.plant,body.mode))

    @router.get('/api/v2/clock/plans')
    def plans():
        c=runtime()
        return {'scope':'SYNTHETIC_THREE_PLANT_NO_OT','entries':c.journal.plans(c.run_id) if c.run_id else []}

    @router.get('/api/v2/clock/plan-report')
    def plan_report():
        c=runtime()
        if not c.engine:return {'scope':'SYNTHETIC_THREE_PLANT_NO_OT','report':[]}
        return {'scope':'SYNTHETIC_THREE_PLANT_NO_OT',
                'report':c.journal.plan_report(c.run_id,c.status()['utc'])}

    @router.get('/api/v2/clock/dispatch-audit')
    def dispatch_audit(limit:int=Query(200,ge=1,le=1000)):
        c=runtime()
        return guard(lambda:{'events':c.journal.audit_events(c.run_id,limit) if c.run_id else []})

    @router.post('/api/v2/clock/plan')
    def plan(request:Request,body:ProductionPlan,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().add_plan(body.plant,body.start_utc,body.end_utc,body.target_kw,body.interval_minutes))

    @router.post('/api/v2/clock/plan/remove')
    def remove_plan(request:Request,body:PlanRemoval,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().remove_plan(body.id))

    @router.post('/api/v2/clock/setpoint')
    def setpoint(request:Request,body:ManualPower,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().manual_setpoint(body.plant,body.kw))

    @router.post('/api/v2/clock/plant-command')
    def command(request:Request,body:OperatorCommand,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().operator_command(body.plant,body.operation))

    @router.post('/api/v2/clock/speed')
    def speed(request:Request,body:Speed,x_synthetic_confirm:str|None=Header(default=None)):
        write_gate(request,x_synthetic_confirm)
        return guard(lambda:runtime().set_speed(body.mode))

    @router.get('/platform/synchronized',response_class=HTMLResponse)
    def dashboard():
        return HTML
    return router


HTML = r'''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autonomous Plant P04 · Ortak UTC Dijital İkiz</title><style>
:root{color-scheme:dark;font:15px system-ui,Segoe UI,sans-serif}*{box-sizing:border-box}
body{background:#0b1422;color:#e8f2fd;margin:0}header{padding:20px 4%;background:#13253b;border-bottom:1px solid #38536c}
main{max-width:1200px;margin:auto;padding:24px}h1{font-size:23px;margin:0 0 8px}h2{font-size:19px}
small,.dim{color:#afc2d5}.warn{color:#ffc57c}button,input,select{color:#fff;background:#233953;border:1px solid #55718f;border-radius:8px;padding:9px;margin:4px;font:inherit}
button{cursor:pointer}button:hover{background:#365978}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}
.card{background:#17283c;border:1px solid #304b69;border-radius:12px;padding:16px;min-width:0;overflow:hidden}#unit-HES,#unit-GES,#unit-RES{overflow-wrap:anywhere;white-space:pre-line;font-size:12px;line-height:1.5;max-height:155px;overflow:auto}.value{font-size:25px;font-weight:700;margin:8px 0}
svg{width:100%;height:160px;background:#0e2034;border-radius:6px}table{width:100%;border-collapse:collapse}td,th{padding:7px;border-bottom:1px solid #37475a;text-align:left}
#msg{min-height:24px;color:#ffc57c}a{color:#92ecd5}
</style></head><body><header><h1>HES + GES + RES · Ortak UTC Dijital İkiz Çekirdeği</h1>
<div class="warn">YALNIZCA SENTETİK SİMÜLASYON · Gerçek PLC/SCADA / şebeke bağlantısı YOK</div>
<small id="build">P04 · UTC_DISPATCH_P04 · Yerel sentetik simülasyon</small><div></div><small>Her ortak adım 15 dakika UTC; HES 900 × 1 saniye, GES/RES 1 × 15 dakika. Her gün demo hava koşulları tekrarlanır.</small></header>
<main><section class="card"><label>Başlangıç (UTC 00:00): <input id="date" type="date" value="2026-01-01"></label><label>Gün: <input id="days" type="number" min="1" max="31" value="3"></label>
<button id="create">Yeni oturum / sıfırla</button><button id="start">Otomatik başlat</button><button id="pause">Duraklat</button><button id="step">+15 dk</button><button id="day">+1 gün (96 adım)</button>
<a href="/api/v2/clock/export.csv">CSV indir</a><p class="dim" id="firstUse">İlk kullanım: “Otomatik başlat” veya “+15 dk” doğrudan yeni sentetik oturum oluşturabilir. Veriler yalnızca yerel SQLite veritabanına kaydedilir.</p><div id="msg" role="status" aria-live="polite"></div><p id="clock">Yükleniyor…</p></section>
<p class="dim">Grafikler: yeşil çizgi gerçekleşen güç, kesikli sarı çizgi talep edilen setpoint (kW).</p><div class="grid" id="cards"></div><section class="card"><h2>Ortak UTC örnekleri</h2><table><thead><tr><th>UTC bitiş</th><th>Santral</th><th>Güç (kW)</th><th>Enerji (kWh)</th><th>Hedef (kW)</th><th>Sapma (kWh)</th></tr></thead><tbody id="samples"></tbody></table></section>
<section class="card"><h2>Üretim planı ve santral setpoint kontrolü</h2>
<p class="dim">UTC bazlı sentetik ihracat sınırı. Talep edilen güç gerçek üretim olarak gösterilmez; kullanılabilir fiziksel güç altında kalan hedefler kırpılır. Saha kumandası değildir.</p>
<label>Santral <select id="pPlant"><option>HES</option><option>GES</option><option>RES</option></select></label>
<label>UTC başlangıç <input id="pStart" type="datetime-local" value="2026-01-01T00:00"></label>
<label>Program aralığı <select id="pGran"><option value="15">15 dakika</option><option value="60">Saatlik</option><option value="1440">Günlük</option></select></label>
<label>Hedef <input id="pKw" type="number" step="0.1" min="0" value="100"></label>
<label>Birim <select id="pUnit"><option value="1">kW</option><option value="1000">MW</option></select></label>
<button id="pSave">UTC üretim hedefi ekle</button>
<button id="pManual">Manuel setpoint uygula</button><button id="pClear">Manuel setpoint temizle</button>
<button id="pStartCmd">Santral START</button><button id="pStopCmd">Santral STOP</button><button id="pAutoCmd">Santral AUTO</button>
<label>İlerleme <select id="pSpeed"><option value="NORMAL">Normal (2 s/adım)</option><option value="FAST">Hızlı (1 s/adım)</option><option value="MAX">Maksimum (4 adım/döngü)</option></select></label>
<button id="pSetSpeed">Hızı uygula</button>
<div id="pSummary" class="value"></div><p id="pProfile" class="dim"></p>
<h2>Plan UTC aralıkları</h2><div style="max-height:220px;overflow:auto"><table><thead><tr><th>Santral</th><th>Başlangıç UTC</th><th>Bitiş UTC</th><th>Hedef (kW)</th><th>Beklenen (kWh)</th><th>Gerçekleşen (kWh)</th><th>Sapma (kWh)</th><th>İşlem</th></tr></thead><tbody id="pPlans"></tbody></table></div>
<h2>Operatör ve reddedilen komut kayıtları</h2><div id="pAudit" class="dim"></div>
</section></main>
<script>const $=id=>document.getElementById(id),plants=['HES','GES','RES'];
for(const p of plants){const d=document.createElement('section');d.className='card';d.innerHTML='<h2>'+p+'</h2><div class="value" id="kw-'+p+'">—</div><div id="total-'+p+'">—</div><svg id="chart-'+p+'" viewBox="0 0 320 160"></svg><div id="unit-'+p+'"></div>'; $('cards').append(d)}
// A page load is deliberately read-only: creating a new run requires a user click.
// Any run-dependent action can bootstrap a PAUSED synthetic run explicitly from
 // the form. This prevents a confusing 409 when Start is the first button clicked.
let latest=[], busy=false, lastRunId=null, planStartEdited=false;
const apiRoot='/api/v2/clock/';
async function get(url,opts){
  let r;
  try { r=await fetch(url,Object.assign({cache:'no-store'},opts||{})); }
  catch(e){ throw Error('Yerel sunucuya erişilemiyor. P04 başlatıcısını açık tutun. ('+e.message+')'); }
  if(!r.ok){
    let raw=await r.text(),detail=raw;
    try{const doc=JSON.parse(raw);detail=doc.detail||raw;}catch(_ignored){}
    if(r.status===403)throw Error('Yazma işlemi yalnızca yerel sentetik SIMULATION modunda açık: '+detail);
    if(r.status===409)throw Error('İşlem yapılamadı: '+detail);
    throw Error('HTTP '+r.status+': '+detail.slice(0,300));
  }
  return r.json();
}
const post=(action,body)=>get(apiRoot+action,{method:'POST',headers:{'X-Synthetic-Confirm':'SYNTHETIC_ONLY','Content-Type':'application/json'},body:JSON.stringify(body||{})});
function syncRun(s){
  if(!s || !s.run_id)return;
  if(lastRunId!==s.run_id){lastRunId=s.run_id;planStartEdited=false;}
  if(!planStartEdited && s.utc) $('pStart').value=s.utc.slice(0,16);
}
function newRunParameters(){
  const date=$('date').value,days=Number($('days').value);
  if(!/^\d{4}-\d\d-\d\d$/.test(date) || !Number.isInteger(days)||days<1||days>31)
    throw Error('Başlangıç tarihi ve 1–31 gün aralığı gerekli.');
  return {start_utc:date+'T00:00:00+00:00',days};
}
async function ensureRun(){
  const s=await get(apiRoot+'status');
  if(s.state==='NOT_CREATED'){
    const created=await post('create',newRunParameters());
    syncRun(created);
    return created;
  }
  syncRun(s);
  if(s.state==='COMPLETE')throw Error('Bu simülasyon tamamlandı. Yeni oturum oluşturun.');
  if(s.state==='FAULT_LATCHED')throw Error('Önce kayıt/recovery hatasını giderin; mevcut oturumda ilerleme güvenlik nedeniyle engellendi.');
  return s;
}
async function cmd(action,body){
  if(busy)return;
  busy=true;
  $('msg').textContent='İşlem sürüyor: '+action+'…';
  try{
    if(action==='create'){
      const s=await post('create',newRunParameters());syncRun(s);
    }else if(action==='pause' && (await get(apiRoot+'status')).state==='NOT_CREATED'){
      $('msg').textContent='Henüz oturum yok; duraklatılacak bir simülasyon bulunmuyor.';
      return;
    }else{
      // Unlike the raw API, the browser makes an explicit first-action bootstrap.
      if(action!=='pause' && action!=='speed') await ensureRun();
      const s=await post(action,body);syncRun(s);
    }
    $('msg').textContent='Başarılı: '+action+' · UTC oturumu kaydedildi.';
    await Promise.all([refresh(),refreshProduction()]);
  }catch(e){$('msg').textContent=e.message;}
  finally{busy=false;}
}
$('create').onclick=()=>cmd('create');
$('start').onclick=()=>cmd('start');
$('pause').onclick=()=>cmd('pause');
$('step').onclick=()=>cmd('step',{count:1});
$('day').onclick=()=>cmd('step',{count:96});
$('pStart').addEventListener('change',()=>{planStartEdited=true});
function graph(id,values){const svg=$(id);svg.replaceChildren();if(!values.length)return;
const max=Math.max(1,...values.map(x=>Math.max(x.power_kw,x.conditions?.dispatch?.requested_kw||0)));
function line(numbers,color,dash){const poly=document.createElementNS('http://www.w3.org/2000/svg','polyline');poly.setAttribute('points',numbers.map((v,i)=>`${12+i*296/Math.max(1,values.length-1)},${148-130*v/max}`).join(' '));poly.setAttribute('stroke',color);poly.setAttribute('stroke-width','2.5');poly.setAttribute('fill','none');if(dash)poly.setAttribute('stroke-dasharray','6 4');svg.append(poly)}
if(values.length===1){
  const dot=document.createElementNS('http://www.w3.org/2000/svg','circle');
  dot.setAttribute('cx',12);dot.setAttribute('cy',148-130*values[0].power_kw/max);
  dot.setAttribute('r',4);dot.setAttribute('fill','#75edcd');svg.append(dot);
}
line(values.map(x=>x.power_kw),'#75edcd',false);
if(values.some(x=>x.conditions?.dispatch?.requested_kw!=null))line(values.map(x=>x.conditions?.dispatch?.requested_kw||0),'#ffc57c',true)}
function physInfo(p,r){
  const f=r.conditions||{},d=f.dispatch||{};
  const n=v=>Number(v).toFixed(1);
  let input='';
  if(p==='HES')input='Düşü: '+n(f.net_head_m||0)+' m · Debi: '+n(f.flow_m3_s||0)+' m³/s';
  if(p==='GES')input='Işınım: '+n(f.irradiance_ghi_w_m2||0)+' W/m²';
  if(p==='RES')input='Rüzgâr: '+n(f.wind_speed_m_s||0)+' m/s';
  const limit=d.available_export_kw==null?'':'\nFiziksel kullanılabilir: '+n(d.available_export_kw)+' kW · Talep: '+(d.requested_kw==null?'Yok':n(d.requested_kw)+' kW')+' · Durum: '+(d.reason||'—');
  const units=(r.units||[]).map(u=>u.id+': '+n(u.kw||0)+' kW').join(' · ');
  return 'Fizik girdileri: '+input+'\n'+units+limit;
}
async function refresh(){try{const [s,h]=await Promise.all([get('/api/v2/clock/status'),get('/api/v2/clock/history?limit=300&after='+Math.max(-1,(window.sIndex||0)-100))]);let samples=h.samples||[];window.sIndex=s.index||0;
syncRun(s);
$('clock').textContent=s.state==='NOT_CREATED'
 ? 'Hazır: henüz oturum oluşturulmadı. Yeni oturum veya Otomatik başlat / +15 dk düğmesine tıklayın; ilk işlem sentetik oturumu hazırlar.'
 : 'Durum: '+s.state+' · UTC: '+(s.utc||'—')+' · '+(s.index||0)+' / '+(s.max_steps||0)+' adım · '+(s.recovered?'Kurtarılan kayıt':'Yerel oturum');
for(const p of plants){const r=s.latest?.[p];$('kw-'+p).textContent=r?Number(r.power_kw).toFixed(2)+' kW':'—';$('total-'+p).textContent=Number(s.total_kwh?.[p]||0).toFixed(2)+' kWh';$('unit-'+p).textContent=r?physInfo(p,r):'Henüz hesaplanan güç yok';graph('chart-'+p,samples.filter(x=>x.plant===p).slice(-48))}
$('samples').replaceChildren();for(const x of samples.slice(-12).reverse()){const tr=document.createElement('tr');for(const value of [x.utc_end,x.plant,Number(x.power_kw).toFixed(1),Number(x.energy_kwh).toFixed(2),x.conditions?.dispatch?.requested_kw??'—',x.conditions?.dispatch?.deviation_kwh?.toFixed(2)??'—']){const td=document.createElement('td');td.textContent=value;tr.append(td)}$('samples').append(tr)}}catch(e){$('msg').textContent='API: '+e.message}}
// All user commands are local, explicit, and require the existing synthetic gate.
const planPlant=()=>$('pPlant').value;
const planPower=()=>Number($('pKw').value)*Number($('pUnit').value);
const planStart=()=>{
  const value=$('pStart').value;
  if(!value)throw Error('Plan için UTC başlangıç zamanını girin.');
  const t=new Date(value+'Z');
  if(!Number.isFinite(t.getTime())||t.getUTCMinutes()%15!==0)throw Error('Başlangıç UTC olarak 15 dakikalık hizaya uymalı.');
  return t;
};
$('pSave').onclick=()=>{
  try{const start=planStart(),mins=Number($('pGran').value);
    cmd('plan',{plant:planPlant(),start_utc:start.toISOString(),end_utc:new Date(start.getTime()+mins*60000).toISOString(),target_kw:planPower(),interval_minutes:mins});
  }catch(e){$('msg').textContent=e.message}
};
$('pManual').onclick=()=>cmd('setpoint',{plant:planPlant(),kw:planPower()});
$('pClear').onclick=()=>cmd('setpoint',{plant:planPlant(),kw:null});
$('pStartCmd').onclick=()=>cmd('plant-command',{plant:planPlant(),operation:'START'});
$('pStopCmd').onclick=()=>cmd('plant-command',{plant:planPlant(),operation:'STOP'});
$('pAutoCmd').onclick=()=>cmd('plant-command',{plant:planPlant(),operation:'AUTO'});
$('pSetSpeed').onclick=()=>cmd('speed',{mode:$('pSpeed').value});
async function refreshProduction(){try{
const [status,plans,audit,report]=await Promise.all([get('/api/v2/clock/status'),get('/api/v2/clock/plans'),get('/api/v2/clock/dispatch-audit?limit=12'),get('/api/v2/clock/plan-report')]);
const values=Object.values(status.latest||{});
$('pSummary').textContent='Toplam güç '+values.reduce((s,r)=>s+Number(r.power_kw),0).toFixed(2)+' kW · Toplam enerji '+Object.values(status.total_kwh||{}).reduce((s,v)=>s+Number(v),0).toFixed(2)+' kWh';
const pr=status.profile||{};
$('pProfile').textContent='Hız: '+(status.speed_mode||'—')+' · Hesaplama '+Number(pr.compute_s||0).toFixed(2)+' s · SQLite/checkpoint '+Number(pr.journal_s||0).toFixed(2)+' s ('+(pr.steps||0)+' adım); otomatik bekleme ayrı';
$('pPlans').replaceChildren();for(const x of plans.entries){const tr=document.createElement('tr');const r=report.report.find(e=>e.id===x.id);const vals=[x.plant,x.utc_start,x.utc_end,Number(x.target_kw).toFixed(1),(x.target_kw*x.interval_minutes/60).toFixed(2),Number(r?.actual_kwh||0).toFixed(2),Number(r?.deviation_elapsed_kwh||0).toFixed(2)];for(const v of vals){const td=document.createElement('td');td.textContent=v;tr.append(td)}const td=document.createElement('td');const b=document.createElement('button');b.textContent='Sil';b.onclick=()=>cmd('plan/remove',{id:x.id});td.append(b);tr.append(td);$('pPlans').append(tr)}
$('pAudit').replaceChildren();for(const x of audit.events.slice(0,8)){const d=document.createElement('div');d.textContent=x.event_utc+' · '+x.kind+' · '+x.payload_json;$('pAudit').append(d)}
}catch(e){$('pProfile').textContent='Üretim paneli: '+e.message}}
async function verifyBuild(){try{
const b=await get(apiRoot+'build');
if(b.build!=='UTC_DISPATCH_P04')throw Error('Eski uygulama sunucusu: '+b.build);
$('build').textContent='Sürüm: '+b.build+' · Mod: '+b.mode+' · Saha bağlantısı YOK';
}catch(e){$('msg').textContent='UYARI: Doğru P04 sunucusu doğrulanamadı. '+e.message}}
window.sIndex=0;verifyBuild();refresh();refreshProduction();setInterval(refresh,2500);setInterval(refreshProduction,5000);
</script></body></html>'''
