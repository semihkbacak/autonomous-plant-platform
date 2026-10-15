"""Unified, read-only simulator dashboard for HES + GES + RES.

No control endpoints. Historic runs can cover different time periods and may
not be added into one real-time plant total. Existing historians are opened
SQLite read-only and are never created or migrated by this module.
"""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


@contextmanager
def _reader(path: Path):
    # SQLite URI handles spaces/non-ASCII characters and never creates a DB.
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    try:
        yield connection
    finally:
        connection.close()


def _value(value: object, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError(f"Invalid {label}")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"Invalid {label}")
    return number


def _unavailable(kind: str, status: str) -> dict:
    return {
        "plant": kind,
        "available": False,
        "status": status,
        "source_kind": "SIMULATOR_ONLY",
        "latest_run": None,
        "samples": [],
    }


def _load_hes(db: sqlite3.Connection) -> dict:
    run = db.execute(
        "SELECT id,scenario,sample_count,duration_s,energy_mwh,source_kind "
        "FROM hydro_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if run is None:
        return _unavailable("HES", "NO_RUNS")

    stats = db.execute(
        "SELECT COUNT(*) AS n, MAX(power_mw) AS peak "
        "FROM hydro_samples WHERE run_id=?", (run["id"],)
    ).fetchone()
    if stats["n"] != run["sample_count"] or stats["n"] < 2:
        raise ValueError("HES historian sample count mismatch")

    records = db.execute(
        "SELECT simulation_time_s,power_mw FROM hydro_samples "
        "WHERE run_id=? ORDER BY simulation_time_s DESC LIMIT 160",
        (run["id"],),
    ).fetchall()
    points = [
        {"label": f"{float(r['simulation_time_s']):g} s", "kw": _value(r["power_mw"], "HES power") * 1000}
        for r in reversed(records)
    ]
    return {
        "plant": "HES", "available": True, "status": "HISTORICAL",
        "source_kind": run["source_kind"],
        "latest_run": {
            "id": run["id"], "scenario": run["scenario"],
            "energy_kwh": _value(run["energy_mwh"], "HES energy") * 1000,
            "peak_kw": _value(stats["peak"], "HES peak") * 1000,
            "last_recorded_kw": points[-1]["kw"],
            "sample_count": stats["n"],
            "time_description": f"{float(run['duration_s']):g} simulated seconds",
        },
        "samples": points,
    }


def _load_ges(db: sqlite3.Connection) -> dict:
    run = db.execute(
        "SELECT id,scenario,interval_count,total_energy_kwh "
        "FROM simulation_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if run is None:
        return _unavailable("GES", "NO_RUNS")

    stats = db.execute(
        "SELECT COUNT(*) AS n, MAX(dispatched_power_kw) AS peak "
        "FROM production_intervals WHERE run_id=?", (run["id"],)
    ).fetchone()
    if stats["n"] != run["interval_count"] or stats["n"] < 1:
        raise ValueError("GES historian interval count mismatch")

    records = db.execute(
        "SELECT end_utc,dispatched_power_kw FROM production_intervals "
        "WHERE run_id=? ORDER BY start_utc DESC LIMIT 160",
        (run["id"],),
    ).fetchall()
    points = [
        {"label": r["end_utc"], "kw": _value(r["dispatched_power_kw"], "GES power")}
        for r in reversed(records)
    ]
    return {
        "plant": "GES", "available": True, "status": "HISTORICAL",
        "source_kind": "SYNTHETIC_SIMULATION_ONLY",
        "latest_run": {
            "id": run["id"], "scenario": run["scenario"],
            "energy_kwh": _value(run["total_energy_kwh"], "GES energy"),
            "peak_kw": _value(stats["peak"], "GES peak"),
            "last_recorded_kw": points[-1]["kw"],
            "sample_count": stats["n"],
            "time_description": f"{stats['n']} recorded 15-minute intervals",
        },
        "samples": points,
    }


def _load_res(db: sqlite3.Connection) -> dict:
    run = db.execute(
        "SELECT id,scenario,interval_count,energy_kwh,source_kind "
        "FROM wind_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if run is None:
        return _unavailable("RES", "NO_RUNS")

    stats = db.execute(
        "SELECT COUNT(*) AS n, MAX(dispatched_kw) AS peak "
        "FROM wind_intervals WHERE run_id=?", (run["id"],)
    ).fetchone()
    if stats["n"] != run["interval_count"] or stats["n"] < 1:
        raise ValueError("RES historian interval count mismatch")

    records = db.execute(
        "SELECT end_utc,dispatched_kw FROM wind_intervals "
        "WHERE run_id=? ORDER BY end_utc DESC LIMIT 160",
        (run["id"],),
    ).fetchall()
    points = [
        {"label": r["end_utc"], "kw": _value(r["dispatched_kw"], "RES power")}
        for r in reversed(records)
    ]
    return {
        "plant": "RES", "available": True, "status": "HISTORICAL",
        "source_kind": run["source_kind"],
        "latest_run": {
            "id": run["id"], "scenario": run["scenario"],
            "energy_kwh": _value(run["energy_kwh"], "RES energy"),
            "peak_kw": _value(stats["peak"], "RES peak"),
            "last_recorded_kw": points[-1]["kw"],
            "sample_count": stats["n"],
            "time_description": f"{stats['n']} recorded 15-minute intervals",
        },
        "samples": points,
    }


def _safe_read(path: Path, plant: str, reader) -> dict:
    if not path.is_file():
        return _unavailable(plant, "DATABASE_MISSING")
    try:
        with _reader(path) as db:
            return reader(db)
    except (sqlite3.Error, ValueError, TypeError, OSError):
        # No filesystem paths or underlying SQL exceptions leaked to clients.
        return _unavailable(plant, "DATABASE_INVALID_OR_INCOMPATIBLE")


def create_platform_router(
    *, hydro_db: str | Path, solar_db: str | Path, wind_db: str | Path
) -> APIRouter:
    """Create routes using fixed, server-configured local historian paths."""
    paths = {"HES": Path(hydro_db), "GES": Path(solar_db), "RES": Path(wind_db)}
    router = APIRouter(tags=["Unified simulation dashboard"])

    @router.get("/api/v1/platform/overview")
    def overview():
        results = {
            "HES": _safe_read(paths["HES"], "HES", _load_hes),
            "GES": _safe_read(paths["GES"], "GES", _load_ges),
            "RES": _safe_read(paths["RES"], "RES", _load_res),
        }
        return {
            "mode": "SIMULATOR_ONLY_READ_ONLY",
            "power_unit": "kW",
            "energy_unit": "kWh",
            "historical_runs_may_not_be_time_aligned": True,
            "combined_total_suppressed": True,
            "plants": results,
        }

    @router.get("/platform/dashboard", response_class=HTMLResponse)
    def dashboard():
        return HTMLResponse(DASHBOARD_HTML)

    return router




DASHBOARD_HTML = r'''<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autonomous Plant Platform | Birleşik Kontrol Paneli</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Arial,sans-serif}
*{box-sizing:border-box}
body{margin:0;background:#0b1320;color:#e8effb}
a{color:#92c9ff;text-decoration:none}a:hover{text-decoration:underline}
header{background:#131f30;border-bottom:1px solid #304258;padding:20px max(18px,calc((100vw - 1360px)/2))}
main{max-width:1360px;margin:auto;padding:24px 18px 60px}
h1{font-size:25px;margin:4px 0}h2{font-size:18px;margin:0}h3{font-size:16px;margin:0}
.small{font-size:12px;line-height:1.55}.muted{color:#9bafc9}
.eyebrow{font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#93a9c7}
.notice{border:1px solid #40536b;background:#19283b;padding:15px;border-radius:10px;margin-bottom:20px;font-size:13px;line-height:1.6}
.section-head,.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px}
.section-head{margin:24px 0 12px}.card-head{margin-bottom:18px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.panel{background:#1a293d;border:1px solid #344c68;border-radius:12px;padding:18px;min-width:0}
.live-card{border-top:3px solid #4ecdc4}.live-card.ges{border-top-color:#f3bb67}.live-card.res{border-top-color:#84aaff}
.tag{font-size:11px;border:1px solid #4a6580;border-radius:20px;padding:4px 9px;color:#c7daf5;white-space:nowrap}
.metric{font-size:27px;letter-spacing:-.5px;font-weight:750;margin:6px 0}
.units{margin:8px 0;min-height:18px;overflow-wrap:anywhere}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin:15px 0}.stats strong{display:block;color:#fff;font-size:15px}
svg{display:block;background:#111e2f;width:100%;height:160px;border-radius:8px;margin:12px 0}
.twin-actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:13px}
button,select{font:inherit;font-size:12px;border:1px solid #527dae;border-radius:7px;background:#24496f;color:#f1f7ff;padding:8px 10px}
button{cursor:pointer}button:hover:not(:disabled){background:#336694}button:disabled{opacity:.46;cursor:not-allowed}
button.danger{background:#61373e;border-color:#986168}
.twin-actions select{max-width:100%;background:#14283e}
.foot{border-top:1px solid #344b66;margin-top:14px;padding-top:12px;display:flex;justify-content:space-between;align-items:center;gap:10px}
.dates{display:flex;justify-content:space-between;gap:8px}.dates span{font-size:10px;color:#95aac7;max-width:48%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.banner{min-height:18px;color:#b5cbea;font-size:13px;margin-top:15px}
@media(max-width:1050px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:720px){.grid{grid-template-columns:1fr}h1{font-size:21px}}
</style>
</head>
<body>
<header>
  <div class="eyebrow">Autonomous Plant Platform</div>
  <h1>HES + GES + RES · Birleşik Simülasyon Paneli</h1>
  <div class="small muted">Canlı dijital ikizler · Yerel simülasyon kontrolü · Geçmiş analitiği</div>
</header>
<main>
  <div class="notice">
    Yalnızca <strong>sentetik simülasyon</strong> amaçlıdır; gerçek PLC/SCADA sistemlerine komut göndermez.
    Her santralin canlı saati farklı ilerleyebilir. Aşağıdaki kayıtlı senaryolar farklı tarihlere ait olabilir;
    bu nedenle enerji değerleri tek bir eşzamanlı toplam olarak gösterilmez.
  </div>

  <div class="section-head">
    <h2>Canlı dijital ikizler</h2><a href="/platform/alarms">
  ⚠ Merkezi Alarm Merkezi →
</a><span class="tag">HES · GES · RES</span>
  </div>
  <div class="grid" id="live-plants">
    <article class="panel live-card hes">
      <div class="card-head"><h3>HES · Hidroelektrik</h3><span class="tag">1 sn/adım</span></div>
      <div class="eyebrow">Canlı tesis gücü</div>
      <div class="metric" id="live-power">—</div>
      <div class="small muted" id="live-status">HES durumu sorgulanıyor…</div>
      <div class="small muted units" id="hes-unit-details">Üniteler yükleniyor…</div>
      <div class="small muted" id="hes-clock-details"></div>
      <div class="twin-actions" id="hes-controls">
        <button type="button" data-hes-action="start" data-unit="UNIT_1">Ünite 1 Başlat</button>
        <button type="button" data-hes-action="stop" data-unit="UNIT_1">Ünite 1 Durdur</button>
        <button type="button" data-hes-action="start" data-unit="UNIT_2">Ünite 2 Başlat</button>
        <button type="button" data-hes-action="stop" data-unit="UNIT_2">Ünite 2 Durdur</button>
        <button type="button" data-hes-action="auto-on">Otomatik saat Aç</button>
        <button type="button" data-hes-action="auto-off">Otomatik saat Kapat</button>
        <button type="button" data-hes-action="tick">1 saniye ilerlet</button>
      </div>
      <div class="foot"><span class="small muted">Sentetik HES</span><a href="/hydro/dashboard">Detaylı panel →</a></div>
    </article>

    <article class="panel live-card ges">
      <div class="card-head"><h3>GES · Güneş</h3><span class="tag">15 dk/adım</span></div>
      <div class="eyebrow">Canlı inverter gücü</div>
      <div class="metric" id="live-ges-power">—</div>
      <div class="small muted" id="live-ges-info">Oturum sorgulanıyor…</div>
      <div class="small muted units" id="live-ges-units"></div>
      <svg id="live-ges-chart" viewBox="0 0 610 185" role="img" aria-label="GES canlı güç grafiği"></svg>
      <div class="twin-actions" data-plant="ges">
        <button type="button" data-action="start" disabled>Başlat</button>
        <button type="button" data-action="pause" disabled>Duraklat</button>
        <button type="button" data-action="step" disabled>1 adım</button>
        <button type="button" data-action="reset" class="danger" disabled>Sıfırla</button>
        <select id="live-ges-mode" aria-label="GES senaryosu" disabled><option>NORMAL</option></select>
        <button type="button" data-action="mode" disabled>Senaryoyu uygula</button>
      </div>
      <div class="foot"><span class="small muted">Sentetik GES</span><a href="/solar/analytics/dashboard">Detaylı panel →</a></div>
    </article>

    <article class="panel live-card res">
      <div class="card-head"><h3>RES · Rüzgâr</h3><span class="tag">15 dk/adım</span></div>
      <div class="eyebrow">Canlı türbin gücü</div>
      <div class="metric" id="live-res-power">—</div>
      <div class="small muted" id="live-res-info">Oturum sorgulanıyor…</div>
      <div class="small muted units" id="live-res-units"></div>
      <svg id="live-res-chart" viewBox="0 0 610 185" role="img" aria-label="RES canlı güç grafiği"></svg>
      <div class="twin-actions" data-plant="res">
        <button type="button" data-action="start" disabled>Başlat</button>
        <button type="button" data-action="pause" disabled>Duraklat</button>
        <button type="button" data-action="step" disabled>1 adım</button>
        <button type="button" data-action="reset" class="danger" disabled>Sıfırla</button>
        <select id="live-res-mode" aria-label="RES senaryosu" disabled><option>NORMAL</option></select>
        <button type="button" data-action="mode" disabled>Senaryoyu uygula</button>
      </div>
      <div class="foot"><span class="small muted">Sentetik RES</span><a href="/wind/dashboard">Detaylı panel →</a></div>
    </article>
  </div>

  <div class="banner" id="control-feedback" role="status"></div>
  <div class="section-head"><h2>En son kayıtlı simülasyonlar</h2>
    <button id="refresh" type="button">Geçmişi yenile</button>
  </div>
  <div class="small muted" id="feedback" role="status"></div>
  <div class="grid" id="plants" style="margin-top:12px"></div>
</main>

<script>
'use strict';
const $ = id => document.getElementById(id);
const colors = {HES:'#4ecdc4', GES:'#f3bb67', RES:'#84aaff'};
const links = {HES:'/hydro/dashboard', GES:'/solar/analytics/dashboard', RES:'/wind/dashboard'};
const fmt = (value, digits=2) => Number(value).toLocaleString('tr-TR',{maximumFractionDigits:digits});
const safe = value => typeof value === 'string' ? value : JSON.stringify(value);

async function getJSON(url){
  const response = await fetch(url,{cache:'no-store'});
  if(!response.ok) throw Error('HTTP '+response.status);
  return response.json();
}
function element(tag,cls,text){
  const item=document.createElement(tag);
  if(cls) item.className=cls;
  if(text!==undefined) item.textContent=String(text);
  return item;
}
function graph(svg,points,color){
  svg.replaceChildren();
  const valid=(points||[]).filter(p=>Number.isFinite(Number(p.kw)) && Number(p.kw)>=0);
  if(!valid.length)return;
  const ns='http://www.w3.org/2000/svg';
  const top=Math.max(1,...valid.map(p=>Number(p.kw)))*1.08;
  const poly=document.createElementNS(ns,'polyline');
  poly.setAttribute('fill','none');poly.setAttribute('stroke',color);
  poly.setAttribute('stroke-width','2.5');poly.setAttribute('stroke-linejoin','round');
  poly.setAttribute('points',valid.map((p,i)=>
    `${12+i*586/Math.max(1,valid.length-1)},${167-Math.min(top,Number(p.kw))*145/top}`
  ).join(' '));
  svg.append(poly);
}

function historicalCard(plant){
  const card=element('article','panel');
  const head=element('div','card-head');
  head.append(element('h3','',plant.plant+' · '+({HES:'Hidroelektrik',GES:'Güneş',RES:'Rüzgâr'}[plant.plant])));
  head.append(element('span','tag',plant.available?'Kayıtlı simülasyon':'Veri bulunamadı'));
  card.append(head);
  if(!plant.available){card.append(element('p','muted',plant.status));return card;}
  const run=plant.latest_run;
  card.append(element('div','eyebrow','Senaryo AC enerjisi'));
  card.append(element('div','metric',fmt(run.energy_kwh)+' kWh'));
  card.append(element('div','small muted',run.scenario+' · '+run.time_description));
  const stats=element('div','stats');
  for(const [label,val] of [
    ['Tepe güç',fmt(run.peak_kw)+' kW'],
    ['Son kayıtlı güç',fmt(run.last_recorded_kw)+' kW'],
    ['Örnek sayısı',run.sample_count]
  ]){
    const item=element('div','small muted',label);
    item.append(element('strong','',val));stats.append(item);
  }
  card.append(stats);
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox','0 0 610 185');
  svg.setAttribute('role','img');
  svg.setAttribute('aria-label',plant.plant+' kayıtlı üretim grafiği');
  graph(svg,plant.samples,colors[plant.plant]);card.append(svg);
  const dates=element('div','dates');
  dates.append(element('span','',plant.samples[0]?.label||''));
  dates.append(element('span','',plant.samples.at(-1)?.label||''));card.append(dates);
  const foot=element('div','foot');foot.append(element('span','small muted','Sentetik · Geçmiş'));
  const a=element('a','','Detaylı panel →');a.href=links[plant.plant];foot.append(a);
  card.append(foot);
  return card;
}
async function refreshHistory(){
  $('feedback').textContent='Geçmiş senaryolar yükleniyor…';
  try{
    const response=await getJSON('/api/v1/platform/overview');
    const grid=$('plants');grid.replaceChildren();
    for(const name of ['HES','GES','RES']) grid.append(historicalCard(response.plants[name]));
    $('feedback').textContent='Kayıtlı senaryolar yüklendi.';
  }catch(error){$('feedback').textContent='Geçmiş sorgusu başarısız: '+error.message;}
}

async function updateHES(){
  try{
    const [plant,runtime]=await Promise.all([
      getJSON('/api/v1/plant'),getJSON('/api/v1/sim/runtime')
    ]);
    const units=plant.units||[];
    const kw=units.reduce((sum,u)=>sum+Number(u.active_power_mw||0)*1000,0);
    $('live-power').textContent=fmt(kw)+' kW';
    $('live-status').textContent='Simülasyon süresi: '+fmt(plant.simulation_time_s,0)+' sn';
    $('hes-clock-details').textContent='Otomatik saat: '+(runtime.auto_tick_enabled?'Açık':'Kapalı');
    // If the separate read-only HES live API has been installed, prefer it.
    let details=units.map(u=>u.unit_id+': '+u.status+' ('+fmt(Number(u.active_power_mw||0)*1000)+' kW)');
    try{
      const live=await getJSON('/api/v1/hes/live/units');
      details=(live.units||[]).map(u=>u.unit_id+': '+u.status+' ('+fmt(u.active_power_kw)+' kW)');
    }catch(_){}
    $('hes-unit-details').textContent=details.join(' · ');
  }catch(error){$('live-status').textContent='HES verisi alınamadı: '+error.message;}
}

const liveSeries={ges:[],res:[]};
const previousIndex={ges:-1,res:-1};
async function updateTwin(plant){
  const group=document.querySelector('.twin-actions[data-plant="'+plant+'"]');
  try{
    const state=await getJSON('/api/v1/sim-console/'+plant);
    group.dataset.available='true';
    group.querySelectorAll('button,select').forEach(control=>control.disabled=false);
    const idx=Number(state.intervals??0);
    const power=Number(state.last_power_kw??0);
    const modes=state.available_modes||['NORMAL'];
    const select=$('live-'+plant+'-mode');
    const current=Array.from(select.options,o=>o.value);
    if(current.join('|')!==modes.join('|')){
      const old=select.value;select.replaceChildren();
      for(const mode of modes){const option=document.createElement('option');option.value=mode;option.textContent=mode;select.append(option);}
      select.value=modes.includes(old)?old:state.mode;
    }
    $('live-'+plant+'-power').textContent=fmt(power)+' kW';
    $('live-'+plant+'-info').textContent=
      (state.error?'Model hatası: '+state.error:state.running?'Çalışıyor':'Duraklatıldı')+
      ' · '+state.mode+' · '+idx+'/96 adım · '+fmt(state.energy_kwh)+' kWh';
    $('live-'+plant+'-units').textContent=(state.units||[]).map(u=>u.id+': '+fmt(u.kw)+' kW ('+u.status+')').join(' · ');
    if(idx<previousIndex[plant]||idx===0)liveSeries[plant]=[];
    if(idx>0&&idx!==previousIndex[plant])liveSeries[plant].push({kw:power,index:idx});
    previousIndex[plant]=idx;
    liveSeries[plant]=liveSeries[plant].slice(-96);
    graph($('live-'+plant+'-chart'),liveSeries[plant],colors[plant.toUpperCase()]);
  }catch(error){
    group.dataset.available='false';
    group.querySelectorAll('button,select').forEach(control=>control.disabled=true);
    $('live-'+plant+'-info').textContent='Konsol erişilemiyor: '+error.message;
  }
}
let updating=false;
async function refreshLive(){
  if(updating)return;
  updating=true;
  try{await Promise.allSettled([updateHES(),updateTwin('ges'),updateTwin('res')]);}
  finally{updating=false;}
}

async function sendCommand(url,payload){
  const headers={'X-Sim-Console-Confirm':'SIMULATION_ONLY'};
  if(payload!==undefined)headers['Content-Type']='application/json';
  const response=await fetch(url,{
    method:'POST',headers,credentials:'same-origin',
    ...(payload!==undefined?{body:JSON.stringify(payload)}:{})
  });
  const data=await response.json().catch(()=>({}));
  if(!response.ok||data.accepted===false){
    const detail=data.detail??data.message??('HTTP '+response.status);
    throw Error(safe(detail));
  }
  return data;
}
function feedback(text){$('control-feedback').textContent=text;}

$('hes-controls').addEventListener('click',async event=>{
  const button=event.target.closest('button[data-hes-action]');
  if(!button)return;
  const action=button.dataset.hesAction;
  const unit=button.dataset.unit;
  let path,body;
  if((action==='start'||action==='stop')&&(unit==='UNIT_1'||unit==='UNIT_2')){
    path='/api/v1/sim-console/hes/unit/'+action;
    body={unit_id:unit};
  }else if(action==='auto-on'||action==='auto-off'){
    path='/api/v1/sim-console/hes/auto?active='+(action==='auto-on'?'true':'false');
  }else if(action==='tick'){
    path='/api/v1/sim-console/hes/tick';
  }else return;
  if(!confirm('HES · '+button.textContent+' · yalnızca sentetik simülasyona uygulansın mı?'))return;
  button.disabled=true;
  try{await sendCommand(path,body);feedback('HES · '+button.textContent+' isteği kabul edildi.');await updateHES();}
  catch(error){feedback('HES komutu reddedildi: '+error.message);}
  finally{button.disabled=false;}
});

for(const group of document.querySelectorAll('.twin-actions[data-plant]')){
  group.addEventListener('click',async event=>{
    const button=event.target.closest('button[data-action]');
    if(!button||group.dataset.available!=='true')return;
    const plant=group.dataset.plant;
    const action=button.dataset.action;
    if(!confirm(plant.toUpperCase()+' · '+button.textContent+' · sentetik simülasyona uygulansın mı?'))return;
    button.disabled=true;
    try{
      const payload=action==='mode'?{mode:$('live-'+plant+'-mode').value}:undefined;
      await sendCommand('/api/v1/sim-console/'+plant+'/'+action,payload);
      feedback(plant.toUpperCase()+' · '+button.textContent+' uygulandı.');
      await updateTwin(plant);
    }catch(error){feedback('Komut reddedildi: '+error.message);}
    finally{button.disabled=false;}
  });
}
$('refresh').addEventListener('click',refreshHistory);
refreshHistory();refreshLive();
setInterval(refreshLive,2500);
</script>
</body>
</html>'''
