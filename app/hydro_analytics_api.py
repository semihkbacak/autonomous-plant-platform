"""Read-only HES historian API and local SVG dashboard."""
from __future__ import annotations

from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from simulator.hydro_history import HydroHistorian


def create_hydro_analytics_router(db_path: str | Path) -> APIRouter:
    path = Path(db_path)
    router = APIRouter(tags=["HES simulated analytics"])

    def history() -> HydroHistorian:
        if not path.is_file():
            raise HTTPException(
                status_code=503,
                detail="HES scenario history not generated yet",
            )
        return HydroHistorian.for_reading(path)

    @router.get("/api/v1/hydro/runs")
    def runs():
        return history().runs()

    @router.get("/api/v1/hydro/runs/{run_id}/samples")
    def samples(run_id: int):
        return history().samples(run_id)

    @router.get("/api/v1/hydro/runs/{run_id}/units")
    def units(run_id: int):
        return history().units(run_id)

    @router.get("/api/v1/hydro/runs/{run_id}/alarms")
    def alarms(run_id: int):
        return history().alarms(run_id)

    @router.get("/api/v1/hydro/runs/{run_id}/summary")
    def summary(run_id: int):
        try:
            return history().summary(run_id)
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail="Unknown HES run",
            ) from exc

    @router.get(
        "/hydro/dashboard",
        response_class=HTMLResponse,
    )
    def dashboard():
        return HTMLResponse(DASHBOARD_HTML)

    return router


DASHBOARD_HTML = r"""
<!doctype html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Autonomous Plant Platform | HES</title>
<style>
:root {color-scheme:dark; font-family:system-ui,sans-serif}
body {margin:0; background:#101927; color:#e4edf7}
header {padding:18px 24px; background:#19283a; border-bottom:1px solid #344559}
main {max-width:1250px; margin:24px auto; padding:0 18px}
h2 {font-size:17px}
p,.sub {color:#9eafc2}
.cards {display:grid; grid-template-columns:repeat(auto-fit,minmax(175px,1fr)); gap:12px}
.card,.panel {background:#19283a; border:1px solid #35475d; border-radius:12px; padding:16px}
.val {font-size:25px; font-weight:750; margin-top:8px}
select,button {background:#243951; color:white; padding:9px; border:1px solid #60758c; border-radius:7px}
svg {display:block; width:100%; height:240px; background:#121f30; border-radius:8px}
table {width:100%; border-collapse:collapse}
td,th {padding:10px; border-bottom:1px solid #35475d; text-align:left; font-size:13px}
.layout {display:grid; grid-template-columns:2fr 1fr; gap:12px}
@media(max-width:760px) {.layout {grid-template-columns:1fr}}
pre {white-space:pre-wrap; word-break:break-word}
</style>
</head>
<body>
<header>
<strong>Autonomous Plant Platform · HES</strong>
<span class="sub"> · Simulator-only · v1.0 candidate</span>
</header>

<main>
<div class="cards">
  <div class="card">Canlı güç<div class="val" id="live-power">—</div></div>
  <div class="card">Simülasyon süresi<div class="val" id="live-time">—</div></div>
  <div class="card">Seçili koşu enerjisi<div class="val" id="energy">—</div></div>
  <div class="card">Alarm yükselmesi<div class="val" id="alarms">—</div></div>
</div>

<p id="status" role="status">Yükleniyor...</p>

<section class="panel">
  <label for="runs">Geçmiş senaryo: </label>
  <select id="runs"></select>
  <span class="sub">Grafikler kayıtlı saniyelik simülasyondan örneklenmiştir.</span>
</section>

<div class="layout">
  <section class="panel">
    <h2>Ünite üretimleri (MW)</h2>
    <svg id="power" role="img" viewBox="0 0 700 240"></svg>
    <h2>Governor hedef ve gerçek üretim (MW)</h2>
    <svg id="governor" role="img" viewBox="0 0 700 240"></svg>
  </section>
  <section class="panel">
    <h2>Canlı üniteler</h2>
    <table>
      <thead>
        <tr>
          <th>Ünite</th><th>Durum</th><th>MW</th>
          <th>Debi</th><th>RPM</th><th>°C</th><th>Titreşim</th>
        </tr>
      </thead>
      <tbody id="live-units"></tbody>
    </table>
    <h2>Olay geçmişi</h2>
    <table>
      <thead><tr><th>Zaman</th><th>Alarm</th><th>Geçiş</th></tr></thead>
      <tbody id="events"></tbody>
    </table>
  </section>
</div>

<div class="layout">
  <section class="panel">
    <h2>Ünite debileri (m³/s)</h2>
    <svg id="flows" role="img" viewBox="0 0 700 240"></svg>
    <h2>Rulman sıcaklıkları (°C)</h2>
    <svg id="temps" role="img" viewBox="0 0 700 240"></svg>
  </section>
  <section class="panel">
    <h2>Titreşimler (mm/s)</h2>
    <svg id="vibration" role="img" viewBox="0 0 700 240"></svg>
    <h2>Net düşü (m)</h2>
    <svg id="head" role="img" viewBox="0 0 700 240"></svg>
  </section>
</div>

<section class="panel">
  <h2>ML / Karar desteği — Salt okunur</h2>
  <button id="assess" type="button">Mevcut HES değerlendirmesini getir</button>
  <pre id="assessment"></pre>
</section>

<section class="panel">
  <h2>Güvenlik ve doğrulama sınırı</h2>
  <p>
    Değerler sentetiktir. Gerçek PLC/SCADA bağlantısı,
    OEM kalibrasyonu veya saha doğrulaması yoktur.
  </p>
</section>
</main>

<script>
const byId = id => document.getElementById(id);
const show = (id, value) => byId(id).textContent = value;

async function json(path) {
  const r = await fetch(path, {cache:"no-store"});
  if (!r.ok) throw Error(`${r.status} ${path}`);
  return r.json();
}

function cell(text) {
  const td = document.createElement("td");
  td.textContent = String(text);
  return td;
}

function draw(svgId, rows, fields) {
  const svg = byId(svgId);
  svg.replaceChildren();
  if (rows.length === 0) return;

  const ns = "http://www.w3.org/2000/svg";
  const width = 700, height = 240, pad = 20;
  const times = rows.map(r => +r.simulation_time_s);
  const xmin = Math.min(...times);
  const xmax = Math.max(...times);
  const values = rows.flatMap(
    r => fields.map(f => Number(r[f.key]) || 0)
  );
  const max = Math.max(1,...values) * 1.1;

  for (const f of fields) {
    const line = document.createElementNS(ns,"polyline");
    line.setAttribute("fill","none");
    line.setAttribute("stroke",f.color);
    line.setAttribute("stroke-width","2");

    line.setAttribute(
      "points",
      rows.map(r => {
        const x = pad +
          (+r.simulation_time_s-xmin) /
          Math.max(1,xmax-xmin)*(width-2*pad);

        const y = height-pad -
          (Number(r[f.key]) || 0) /
          max*(height-2*pad);

        return `${x},${y}`;
      }).join(" ")
    );
    svg.append(line);
  }
}

async function refreshLive() {
  try {
    const p = await json("/api/v1/plant");
    const mw = p.units.reduce(
      (s,u) => s+u.active_power_mw, 0
    );
    show("live-power",mw.toFixed(2)+" MW");
    show("live-time",p.simulation_time_s+" s");

    const target = byId("live-units");
    target.replaceChildren();

    for (const u of p.units) {
      const tr = document.createElement("tr");
      [
        u.unit_id,
        u.status,
        u.active_power_mw.toFixed(2),
        u.flow_m3_s.toFixed(2),
        u.rpm.toFixed(0),
        u.bearing_temperature_c.toFixed(1),
        u.vibration_mm_s.toFixed(2)
      ].forEach(v => tr.append(cell(v)));
      target.append(tr);
    }
  } catch(e) {
    show("live-power","Ulaşılamıyor");
  }
}

async function renderRun() {
  const id = byId("runs").value;
  if (!id) return;

  try {
    const [summary,units,alarms,samples] = await Promise.all([
      json(`/api/v1/hydro/runs/${id}/summary`),
      json(`/api/v1/hydro/runs/${id}/units`),
      json(`/api/v1/hydro/runs/${id}/alarms`),
      json(`/api/v1/hydro/runs/${id}/samples`)
    ]);

    show("energy",summary.energy_mwh.toFixed(4)+" MWh");
    show("alarms",summary.alarm_raises);

    const byTime = new Map();

    for (const u of units) {
      let r = byTime.get(u.simulation_time_s);
      if (!r) {
        r = {simulation_time_s:u.simulation_time_s};
        byTime.set(u.simulation_time_s,r);
      }

      r[u.unit_id] = u.power_mw;
      r[u.unit_id+"_target"] = u.target_power_mw;
      r[u.unit_id+"_flow"] = u.flow_m3_s;
      r[u.unit_id+"_temp"] = u.bearing_temperature_c;
      r[u.unit_id+"_vibration"] = u.vibration_mm_s;
    }

    const data = [...byTime.values()].sort(
      (a,b) => a.simulation_time_s-b.simulation_time_s
    );

    draw("power",data,[
      {key:"UNIT_1",color:"#37c9bb"},
      {key:"UNIT_2",color:"#75a7ff"}
    ]);

    draw("governor",data,[
      {key:"UNIT_1",color:"#37c9bb"},
      {key:"UNIT_1_target",color:"#ffce75"}
    ]);

    draw("flows",data,[
      {key:"UNIT_1_flow",color:"#37c9bb"},
      {key:"UNIT_2_flow",color:"#75a7ff"}
    ]);

    draw("temps",data,[
      {key:"UNIT_1_temp",color:"#ffce75"},
      {key:"UNIT_2_temp",color:"#f17b7b"}
    ]);

    draw("vibration",data,[
      {key:"UNIT_1_vibration",color:"#37c9bb"},
      {key:"UNIT_2_vibration",color:"#f17b7b"}
    ]);

    draw("head",samples,[
      {key:"net_head_m",color:"#75a7ff"}
    ]);

    const target = byId("events");
    target.replaceChildren();

    for (const a of alarms.slice(-15).reverse()) {
      const tr = document.createElement("tr");
      [
        a.simulation_time_s,
        a.code,
        a.transition
      ].forEach(x => tr.append(cell(x)));
      target.append(tr);
    }

    show(
      "status",
      "Kaydedilen koşu: "+summary.scenario+
      " · "+summary.sample_count+" örnek"
    );

  } catch(e) {
    show("status","Geçmiş okunamadı: "+e.message);
  }
}

async function init() {
  byId("assess").addEventListener("click",async () => {
    try {
      const result = await json("/api/v1/system/assessment");
      show("assessment",JSON.stringify(result,null,2));
    } catch(e) {
      show("assessment","Assessment unavailable: "+e.message);
    }
  });

  await refreshLive();

  try {
    const runs = await json("/api/v1/hydro/runs");
    const select = byId("runs");
    select.replaceChildren();

    for (const r of runs) {
      const opt = document.createElement("option");
      opt.value = r.id;
      opt.textContent = `#${r.id} ${r.scenario}`;
      select.append(opt);
    }

    select.addEventListener("change",renderRun);

    if (runs.length) await renderRun();
    else show("status","Henüz geçmiş yok.");

  } catch(e) {
    show("status","Geçmiş hazır değil: "+e.message);
  }

  setInterval(refreshLive,2000);
}

init();
</script>
</body>
</html>
"""