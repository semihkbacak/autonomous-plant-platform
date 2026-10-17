"""Read-only state feed and opt-in, local-only synthetic live-twin research UI.

GES/RES sessions are NOT connected to hardware: a 15-minute simulated interval
advances every 2 seconds of wall time while a session is started. No real OT.
"""
from __future__ import annotations
from fastapi import APIRouter
from fastapi.responses import HTMLResponse


def create_live_twins_router(sessions, hydro) -> APIRouter:
    router=APIRouter(tags=['Local synthetic live twins — no OT'])

    @router.get('/api/v1/live-twins/state')
    def state():
        snap=hydro.snapshot()
        return {
            'scope':'SYNTHETIC_LOCAL_SIMULATION_NOT_A_REAL_TIME_SITE_TWIN',
            'clock':'GES/RES: 15 simulation minutes every 2 wall seconds while running',
            'hes':{'plant':'HES','running':hydro.auto_tick_enabled,
                   'units':[{'id':u.unit_id,'kw':u.active_power_mw*1000,'status':u.status.value}
                            for u in snap.units]},
            'ges':sessions.ges.status(),
            'res':sessions.res.status(),
        }

    @router.get('/platform/live-twins',response_class=HTMLResponse)
    @router.get('/platform/live-twins/{plant}',response_class=HTMLResponse)
    def page(plant: str | None=None):
        return HTML
    return router


HTML=r'''<!doctype html><html lang="tr"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>HES + GES + RES | Canlı sentetik ikizler</title>
<style>
:root{color-scheme:dark;font:15px system-ui,Segoe UI,Arial,sans-serif}
*{box-sizing:border-box}body{margin:0;background:#0b1221;color:#eff6ff}
header{padding:22px max(18px,calc((100vw - 1200px)/2));border-bottom:1px solid #243752;background:#111d30}
main{max-width:1240px;margin:0 auto;padding:20px}h1{font-size:24px;margin:0 0 8px}h2{font-size:19px;margin:0 0 12px}
.note{color:#aebfd4;font-size:13px}.alert{color:#ffc179;font-weight:600}
nav{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}a{color:#83e2d4}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:16px}
.card{background:#162338;border:1px solid #2d435c;border-radius:14px;padding:17px;min-width:0}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}
.metric{background:#101b2c;border-radius:9px;padding:12px;min-width:0}
.metric strong{display:block;font-size:20px;margin:5px 0}.metric span{color:#9eb2ce;font-size:12px}
button,select{background:#263a54;color:#f4f9ff;border:1px solid #4d6986;border-radius:8px;padding:8px 11px;font:inherit;cursor:pointer}
button:hover{background:#355575}button:focus,select:focus{outline:2px solid #82e0cd}
.actions{display:flex;gap:8px;flex-wrap:wrap}table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
th,td{padding:9px;text-align:left;border-bottom:1px solid #34465f}svg{width:100%;height:210px;background:#0c192b;border-radius:7px}
.state{font-size:12px;color:#9edcca;padding:4px 8px;border:1px solid #386a62;border-radius:20px}
#log{color:#ffc179;min-height:20px}.badge{padding:4px 8px;border:1px solid #946a43;color:#ffb97a;border-radius:20px;font-size:11px}
@media(max-width:650px){.cards{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}}
</style></head><body>
<header><h1>Autonomous Plant Platform · Live Research Twins</h1>
<div class="alert">SADECE SENTETİK SİMÜLASYON · Gerçek PLC/SCADA veya saha ölçümü bağlanmaz</div>
<div class="note">GES / RES simülatörleri: çalışırken 2 saniyede 15 dakikalık sentetik adım · Ekran 1 saniyede yenilenir.</div>
<nav><a href="/platform/dashboard">Birleşik panel</a><a href="/solar/analytics/dashboard">GES geçmiş analizi</a><a href="/wind/dashboard">RES geçmiş analizi</a><a href="/docs">API rehberi</a></nav></header>
<main><p id="log" role="status">Yerel sunucudan sentetik ölçümler alınıyor...</p>
<div class="cards">
<section class="card"><h2>☀ GES · Güneş Santrali <span id="ges-state" class="state">—</span></h2>
<div class="actions"><button data-plant="ges" data-action="start">Başlat</button><button data-plant="ges" data-action="pause">Duraklat</button><button data-plant="ges" data-action="step">+15 dk</button><button data-plant="ges" data-action="reset">Sıfırla</button><button data-plant="ges" data-action="daylight" title="Yalnızca sentetik günün gündüzüne hızlı ilerletir">☀ Gündüze İlerle</button><select id="ges-mode"><option>NORMAL</option><option>GRID_LOSS</option><option>ESTOP</option><option>FAULT</option><option>LOW_LIGHT</option><option>CURTAIL_50</option></select><button data-plant="ges" data-action="mode">Senaryoyu uygula</button></div>
<div class="metrics"><div class="metric"><span>Aktif güç</span><strong id="ges-kw">—</strong></div><div class="metric"><span>Enerji</span><strong id="ges-kwh">—</strong></div><div class="metric"><span>GHI / ışınım</span><strong id="ges-weather">—</strong></div></div>
<svg id="ges-graph" viewBox="0 0 600 210" role="img" aria-label="GES sentetik güç değişimi"></svg>
<div class="note" id="ges-time">Henüz simülasyon çalışmadı.</div><table><thead><tr><th>İnverter</th><th>Durum</th><th>Aktif güç (kW)</th></tr></thead><tbody id="ges-units"></tbody></table></section>
<section class="card"><h2>🌬 RES · Rüzgâr Santrali <span id="res-state" class="state">—</span></h2>
<div class="actions"><button data-plant="res" data-action="start">Başlat</button><button data-plant="res" data-action="pause">Duraklat</button><button data-plant="res" data-action="step">+15 dk</button><button data-plant="res" data-action="reset">Sıfırla</button><select id="res-mode"><option>NORMAL</option><option>GRID_LOSS</option><option>ESTOP</option><option>FAULT</option><option>LOW_WIND</option><option>HIGH_WIND</option><option>WAKE</option><option>CURTAIL_50</option></select><button data-plant="res" data-action="mode">Senaryoyu uygula</button></div>
<div class="metrics"><div class="metric"><span>Aktif güç</span><strong id="res-kw">—</strong></div><div class="metric"><span>Enerji</span><strong id="res-kwh">—</strong></div><div class="metric"><span>Rüzgâr</span><strong id="res-weather">—</strong></div></div>
<svg id="res-graph" viewBox="0 0 600 210" role="img" aria-label="RES sentetik güç değişimi"></svg><div class="note" id="res-time">Henüz simülasyon çalışmadı.</div>
<table><thead><tr><th>Türbin</th><th>Durum</th><th>Aktif güç (kW)</th></tr></thead><tbody id="res-units"></tbody></table></section>
</div></main><script>
'use strict';const el=id=>document.getElementById(id);const ns='http://www.w3.org/2000/svg';
async function read(url,opts){const r=await fetch(url,Object.assign({cache:'no-store'},opts||{}));if(!r.ok)throw Error('HTTP '+r.status+': '+(await r.text()).slice(0,140));return r.json()}
function plot(id,series){const svg=el(id);svg.replaceChildren();if(!series.length)return;const values=series.map(x=>Number(x.power_kw)||0),top=Math.max(1,...values)*1.1;const pts=values.map((v,i)=>`${25+i*550/Math.max(1,values.length-1)},${190-v*155/top}`).join(' ');
const poly=document.createElementNS(ns,'polyline');poly.setAttribute('points',pts);poly.setAttribute('fill','none');poly.setAttribute('stroke','#60dbc3');poly.setAttribute('stroke-width','3');svg.append(poly);}
function render(kind,x){el(kind+'-state').textContent=(x.running?'ÇALIŞIYOR':'DURDU')+' · '+x.mode;el(kind+'-kw').textContent=Number(x.last_power_kw||0).toFixed(1)+' kW';el(kind+'-kwh').textContent=Number(x.energy_kwh||0).toFixed(1)+' kWh';const c=x.conditions||{};
el(kind+'-weather').textContent=kind==='ges'?(c.irradiance_ghi_w_m2==null?'—':Number(c.irradiance_ghi_w_m2).toFixed(0)+' W/m²'):(c.wind_speed_m_s==null?'—':Number(c.wind_speed_m_s).toFixed(1)+' m/s');
el(kind+'-time').textContent=`${x.intervals}/96 sentetik aralık · ${x.last_end_utc||'Başlamadı'} · ${x.error||'Model hatası yok'}`+(kind==='ges'&&x.intervals&&Number(c.irradiance_ghi_w_m2||0)<1?' · GECE: 0 kW beklenen; Gündüze İlerle tuşunu kullanabilirsiniz.':'');plot(kind+'-graph',x.power_series||[]);
const tbody=el(kind+'-units');tbody.replaceChildren();for(const u of x.units||[]){const tr=document.createElement('tr');for(const v of [u.id,u.status,Number(u.kw||0).toFixed(1)]){const td=document.createElement('td');td.textContent=String(v);tr.append(td)}tbody.append(tr)}}
async function refresh(){try{const s=await read('/api/v1/live-twins/state');render('ges',s.ges);render('res',s.res);el('log').textContent='Canlı sentetik motor verileri · FİZİKSEL SAHA BAĞLANTISI YOK';}catch(e){el('log').textContent='Yerel API alınamadı: '+e.message}}
document.querySelectorAll('button[data-plant]').forEach(button=>button.addEventListener('click',async()=>{const kind=button.dataset.plant,action=button.dataset.action;
const body=action==='mode'?{mode:el(kind+'-mode').value}:undefined;try{await read(`/api/v1/sim-console/${kind}/${action}`,{method:'POST',headers:{'X-Sim-Console-Confirm':'SIMULATION_ONLY','Content-Type':'application/json'},body:body?JSON.stringify(body):''});await refresh()}catch(e){el('log').textContent='Komut reddedildi (yalnızca yerel SIMULATION modu): '+e.message}}));
refresh();setInterval(refresh,1000);
</script></body></html>'''
