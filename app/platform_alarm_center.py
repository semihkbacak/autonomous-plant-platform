
"""Read-only, simulator-only cross-plant alarm aggregation.

HES emits actual simulator alarms.
GES/RES scenario selections are not equipment alarms.
No PLC, SCADA or physical control.
"""
from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse


def create_platform_alarm_router(hydro, sessions) -> APIRouter:
    router = APIRouter(tags=["Unified simulator alarm center"])

    def collect() -> dict:
        alarms: list[dict] = []
        conditions: list[dict] = []
        sources: dict[str, str] = {}

        try:
            for item in hydro.active_alarms():
                alarms.append({
                    "plant": "HES",
                    "unit_id": item.unit_id,
                    "code": item.code,
                    "severity": item.severity.value,
                    "message": item.message,
                    "source": "HES_SIMULATOR_ALARM",
                })

            snapshot = hydro.snapshot()

            if snapshot.emergency_stop:
                conditions.append({
                    "plant": "HES",
                    "code": "E_STOP_ACTIVE",
                    "message": "Sentetik acil durdurma aktif",
                    "source": "SIMULATOR_STATE",
                })

            if snapshot.maintenance_lock:
                conditions.append({
                    "plant": "HES",
                    "code": "MAINTENANCE_LOCK_ACTIVE",
                    "message": "Sentetik bakım kilidi aktif",
                    "source": "SIMULATOR_STATE",
                })

            sources["HES"] = "AVAILABLE"

        except Exception:
            sources["HES"] = "UNAVAILABLE"

        for plant in ("GES", "RES"):
            try:
                state = sessions.session(
                    plant.lower()
                ).status()

                if state.get("error"):
                    alarms.append({
                        "plant": plant,
                        "unit_id": None,
                        "code": "SIMULATION_MODEL_ERROR",
                        "severity": "CRITICAL",
                        "message": (
                            "Sentetik model adımı başarısız: "
                            + str(state["error"])
                        ),
                        "source": "SIMULATION_RUNTIME_FAILURE",
                    })

                mode = str(
                    state.get("mode", "NORMAL")
                )

                if mode != "NORMAL":
                    conditions.append({
                        "plant": plant,
                        "code": "SELECTED_SCENARIO_" + mode,
                        "message": (
                            "Seçilmiş sentetik senaryo; "
                            "doğrulanmış saha alarmı değil"
                        ),
                        "source": "SIMULATOR_SCENARIO_SELECTION",
                    })

                sources[plant] = "AVAILABLE"

            except Exception:
                sources[plant] = "UNAVAILABLE"

        return {
            "scope": "SYNTHETIC_SIMULATOR_READ_ONLY",
            "independent_simulation_clocks": True,
            "sources": sources,
            "complete": (
                len(sources) == 3
                and all(
                    value == "AVAILABLE"
                    for value in sources.values()
                )
            ),
            "active_alarm_count": len(alarms),
            "scenario_condition_count": len(conditions),
            "alarms": alarms,
            "conditions": conditions,
        }

    @router.get("/api/v1/platform/alarms/live")
    def live_alarms() -> dict:
        return collect()

    @router.get("/api/v1/platform/alarms/events")
    def recent_events(
        limit: int = Query(default=50, ge=1, le=200),
    ) -> dict:
        events = []
        sources = {}

        try:
            for item in hydro.alarm_history():
                events.append({
                    "plant": "HES",
                    "type": "HES_ALARM_FIRST_SEEN",
                    "code": item.code,
                    "unit_id": item.unit_id,
                    "severity": item.severity.value,
                    "local_step": (
                        item.first_seen_simulation_time_s
                    ),
                    "local_clock_unit": "seconds",
                })

            sources["HES"] = "AVAILABLE"

        except Exception:
            sources["HES"] = "UNAVAILABLE"

        for plant in ("GES", "RES"):
            try:
                state = sessions.session(
                    plant.lower()
                ).status()

                for item in state.get("events", ()):
                    events.append({
                        "plant": plant,
                        "type": "SIMULATION_SESSION_EVENT",
                        "code": str(item["event"]),
                        "unit_id": None,
                        "severity": "INFO",
                        "local_step": item["interval"],
                        "local_clock_unit": "15_min_intervals",
                    })

                sources[plant] = "AVAILABLE"

            except Exception:
                sources[plant] = "UNAVAILABLE"

        # Do not invent one chronology across different clocks.
        groups = {
            plant: [
                event for event in events
                if event["plant"] == plant
            ][-limit:]
            for plant in ("HES", "GES", "RES")
        }

        return {
            "scope": "SYNTHETIC_VOLATILE_EVENTS_ONLY",
            "not_globally_time_ordered": True,
            "sources": sources,
            "events_by_plant": groups,
        }

    @router.get(
        "/platform/alarms",
        response_class=HTMLResponse,
    )
    def alarm_dashboard():
        return HTMLResponse(ALARM_DASHBOARD_HTML)

    return router


ALARM_DASHBOARD_HTML = r'''<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport"
      content="width=device-width,initial-scale=1">
<title>Autonomous Plant Platform — Alarm Merkezi</title>
<style>
:root {
  color-scheme: dark;
  font-family: system-ui, sans-serif;
}

* { box-sizing: border-box; }

body {
  background: #0b1320;
  color: #e6effb;
  margin: 0;
}

header {
  background: #152239;
  border-bottom: 1px solid #334b66;
  padding: 22px max(16px,calc((100vw - 1280px)/2));
}

main {
  max-width: 1280px;
  margin: auto;
  padding: 24px 16px;
}

h1 { font-size: 23px; margin: 6px 0; }
h2 { font-size: 17px; }

a { color: #93cbff; }
p, .muted { color: #a5bad2; }

.grid {
  display: grid;
  grid-template-columns: repeat(3,minmax(0,1fr));
  gap: 12px;
}

.card {
  background: #19293d;
  border: 1px solid #36516d;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 14px;
}

.big { font-size: 29px; font-weight: 800; }

button {
  background: #264d76;
  color: white;
  border: 1px solid #527ea8;
  border-radius: 7px;
  padding: 8px 12px;
  cursor: pointer;
}

.item {
  padding: 10px 0;
  border-bottom: 1px solid #34475c;
}

.tag { font-size: 12px; color: #9bbbe0; }
.status { font-size: 13px; }
strong { overflow-wrap: anywhere; }
.warn { color: #ffc477; }

@media (max-width:750px) {
  .grid { grid-template-columns: 1fr; }
}
</style>
</head>
<body>
<header>
  <div class="tag">
    AUTONOMOUS PLANT PLATFORM · SİMÜLASYON
  </div>

  <h1>Merkezi alarm ve senaryo durumu</h1>

  <a href="/platform/dashboard">
    ← Birleşik panele dön
  </a>
</header>

<main>
  <div class="card warn">
    Bu ekran yalnızca sentetik HES alarmlarını,
    GES/RES model hatalarını ve seçilmiş senaryo
    durumlarını gösterir. Gerçek saha koruması değildir.
    Saatler eşzamanlı değildir.
  </div>

  <div class="grid">
    <div class="card">
      <div class="muted">Etkin simülasyon alarmı</div>
      <div class="big" id="count">—</div>
    </div>

    <div class="card">
      <div class="muted">Senaryo/durum göstergesi</div>
      <div class="big" id="conditions-count">—</div>
    </div>

    <div class="card">
      <div class="muted">Kaynak erişimi</div>
      <div class="big status" id="sources">
        Yükleniyor…
      </div>
    </div>
  </div>

  <div class="card">
    <h2>Etkin alarmlar</h2>
    <div id="alarms" class="muted" role="status">
      Yükleniyor…
    </div>
  </div>

  <div class="card">
    <h2>Aktif sentetik koşullar (alarm değildir)</h2>
    <div id="conditions" class="muted">
      Yükleniyor…
    </div>
  </div>

  <div class="card">
    <h2>Oturum/Alarm geçmişi</h2>
    <div class="muted">
      Her tesisin yerel simülasyon saatine göre,
      tesis bazında gruplanmıştır.
    </div>
    <div id="events">Yükleniyor…</div>
  </div>

  <button id="refresh" type="button">
    Şimdi yenile
  </button>

  <p id="feedback" role="status"></p>
</main>

<script>
'use strict';

const by = id => document.getElementById(id);

async function read(url) {
  const response = await fetch(url, {
    cache: 'no-store'
  });

  if (!response.ok) {
    throw Error('HTTP ' + response.status);
  }

  return response.json();
}

function draw(id, items, formatter) {
  const target = by(id);
  target.replaceChildren();

  if (!items.length) {
    target.textContent = 'Kayıt yok';
    return;
  }

  for (const item of items) {
    const div = document.createElement('div');
    div.className = 'item';
    div.textContent = formatter(item);
    target.append(div);
  }
}

let busy = false;

async function refresh() {
  if (busy) return;
  busy = true;

  try {
    const [live, history] = await Promise.all([
      read('/api/v1/platform/alarms/live'),
      read('/api/v1/platform/alarms/events?limit=25')
    ]);

    by('count').textContent =
      live.active_alarm_count;

    by('conditions-count').textContent =
      live.scenario_condition_count;

    by('sources').textContent =
      Object.entries(live.sources)
        .map(([key, value]) => key + ': ' + value)
        .join(' · ');

    draw('alarms', live.alarms, alarm =>
      alarm.plant + ' · ' +
      alarm.severity + ' · ' +
      alarm.code +
      (alarm.unit_id ? ' · ' + alarm.unit_id : '') +
      ' — ' + alarm.message
    );

    draw('conditions', live.conditions, condition =>
      condition.plant + ' · ' +
      condition.code + ' — ' +
      condition.message
    );

    const events = Object.entries(
      history.events_by_plant
    ).flatMap(([plant, records]) =>
      records.slice(-10).reverse().map(event => ({
        plant,
        ...event
      }))
    );

    draw('events', events, event =>
      event.plant + ' · ' +
      event.code + ' · ' +
      event.local_step +
      ' (' + event.local_clock_unit + ')'
    );

    by('feedback').textContent = live.complete
      ? 'Tüm simülasyon kaynakları erişilebilir.'
      : 'Bir veya daha fazla kaynak okunamadı; ' +
        'sıfır alarm güvenli anlamına gelmez.';

  } catch (error) {
    by('feedback').textContent =
      'Alarm verisi alınamadı: ' + error.message;

  } finally {
    busy = false;
  }
}

by('refresh').addEventListener('click', refresh);

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>'''
