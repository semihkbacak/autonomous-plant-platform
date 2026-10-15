"""RES read-only historian API and local dashboard. No turbine controls."""
from __future__ import annotations
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from simulator.wind_history import WindHistorian


def create_wind_analytics_router(db_path: str | Path) -> APIRouter:
    path = Path(db_path)
    router = APIRouter(tags=['RES simulated analytics'])

    def history() -> WindHistorian:
        if not path.is_file():
            raise HTTPException(503, 'RES historian not generated')
        return WindHistorian(path, read_only=True)

    @router.get('/api/v1/wind/runs')
    def runs():
        return history().runs()

    @router.get('/api/v1/wind/runs/{run_id}/intervals')
    def intervals(run_id: int):
        if run_id not in {r['id'] for r in history().runs()}:
            raise HTTPException(404, 'Unknown RES run')
        return history().intervals(run_id)

    @router.get('/api/v1/wind/runs/{run_id}/turbines')
    def turbines(run_id: int):
        if run_id not in {r['id'] for r in history().runs()}:
            raise HTTPException(404, 'Unknown RES run')
        return history().turbines(run_id)

    @router.get('/api/v1/wind/audit')
    def audit():
        return history().audit()

    @router.get('/wind/dashboard', response_class=HTMLResponse)
    def dashboard():
        return HTMLResponse(WIND_DASHBOARD_HTML)

    return router


WIND_DASHBOARD_HTML = r'''<!doctype html>
<html lang="tr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autonomous Plant Platform | RES</title>
<style>
:root{color-scheme:dark;font-family:system-ui,sans-serif}
body{background:#101827;color:#e6ecf6;max-width:1100px;margin:25px auto;padding:0 18px}
main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:15px}
section{background:#1b293e;padding:15px;border:1px solid #34465e;border-radius:12px}
strong{font-size:22px}p{color:#a9b9cf}svg{width:100%;height:210px;background:#101d2d}
select{padding:10px;background:#263e59;color:white;border-radius:7px}
table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:7px;border-bottom:1px solid #405167;text-align:left}
</style></head><body>
<h1>RES — Rüzgâr Santrali</h1><p>Sentetik 15 dakikalık iki türbin simülasyonu. OEM/saha doğrulaması veya gerçek tesis bağlantısı yok.</p>
<label>Senaryo <select id="runs"></select></label><p id="info">Yükleniyor...</p>
<main>
<section><h3>Çiftlik AC güç (kW)</h3><strong id="energy">—</strong><svg id="power" viewBox="0 0 600 210"></svg></section>
<section><h3>İki türbin güç karşılaştırması</h3><svg id="turbines" viewBox="0 0 600 210"></svg></section>
<section><h3>Rüzgâr ve wake etkisi (m/s)</h3><svg id="wind" viewBox="0 0 600 210"></svg></section>
<section><h3>Türbin durumları</h3><table><thead><tr><th>Türbin</th><th>Durum</th><th>kW</th><th>Wake %</th></tr></thead><tbody id="states"></tbody></table></section>
</main><script>
const el=id=>document.getElementById(id);
async function get(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw Error(r.status+' '+path);return r.json()}
function plot(id,series){const svg=el(id),ns='http://www.w3.org/2000/svg';svg.replaceChildren();
 const top=Math.max(1,...series.flatMap(x=>x.values)),len=Math.max(2,...series.map(x=>x.values.length));
 for(const s of series){const poly=document.createElementNS(ns,'polyline');poly.setAttribute('fill','none');poly.setAttribute('stroke',s.color);poly.setAttribute('stroke-width','2');
 poly.setAttribute('points',s.values.map((v,i)=>`${12+i*576/(len-1)},${200-Math.max(0,v)*185/top}`).join(' '));svg.append(poly)}}
async function render(){const id=el('runs').value;if(!id)return;
 try{const [a,b]=await Promise.all([get(`/api/v1/wind/runs/${id}/intervals`),get(`/api/v1/wind/runs/${id}/turbines`)]);
 el('energy').textContent=a.reduce((v,x)=>v+x.interval_kwh,0).toFixed(1)+' kWh';
 plot('power',[{values:a.map(x=>x.dispatched_kw),color:'#58d6bc'}]);
 plot('turbines',['WT_1','WT_2'].map((t,i)=>({values:b.filter(x=>x.turbine_id===t).map(x=>x.dispatched_kw),color:i?'#ffbf72':'#61b4ff'})));
 plot('wind',['WT_1','WT_2'].map((t,i)=>({values:b.filter(x=>x.turbine_id===t).map(x=>x.effective_wind_m_s),color:i?'#ffbf72':'#61b4ff'})));
 const tbody=el('states');tbody.replaceChildren();for(const x of b.slice(-2)){const row=document.createElement('tr');for(const v of [x.turbine_id,x.status,x.dispatched_kw.toFixed(1),(100*x.wake_loss_fraction).toFixed(1)]){const td=document.createElement('td');td.textContent=v;row.append(td)}tbody.append(row)}
 el('info').textContent=a.length+' kayıt; 15 dakikalık simülasyon verisi';
 }catch(e){el('info').textContent='Veri okunamadı: '+e.message}}
async function init(){try{const runs=await get('/api/v1/wind/runs');for(const r of runs){const o=document.createElement('option');o.value=r.id;o.textContent=r.scenario;el('runs').append(o)}el('runs').addEventListener('change',render);if(runs.length)await render();else el('info').textContent='Henüz senaryo üretilmemiş'}catch(e){el('info').textContent=e.message}}
init();</script></body></html>'''
