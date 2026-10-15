"""Research/engineering dashboard on existing synthetic simulators.

No real equipment writes, OT adapters, credentials, field readiness assertions.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.engineering_core import inspect_telemetry, validate_synchronized_portfolio, generate_fault_matrix
from app.engineering_coverage import coverage
from app.engineering_audit import recent_attempts, database_path


class IntervalRow(BaseModel):
    plant: str
    start_utc: str
    end_utc: str
    mean_power_kw: float = Field(ge=0, allow_inf_nan=False)
    source_kind: str


class PortfolioInput(BaseModel):
    rows: list[IntervalRow] = Field(min_length=3, max_length=3000)


def create_engineering_router(hydro, sessions) -> APIRouter:
    router = APIRouter(tags=['Engineering research (simulation only)'])

    def state_report():
        states = {}
        try:
            snap = hydro.snapshot()
            states['HES'] = {'power_kw': sum(float(u.active_power_mw) * 1000 for u in snap.units),
                             'units': [{'id': u.unit_id, 'kw': float(u.active_power_mw) * 1000} for u in snap.units],
                             'error': None, 'source_kind': 'SYNTHETIC_DYNAMICS',
                             'local_sim_time_s': snap.simulation_time_s}
        except Exception:
            states['HES'] = None
        for name in ('GES', 'RES'):
            try:
                raw = sessions.session(name.lower()).status()
                states[name] = {'power_kw': raw.get('last_power_kw'), 'energy_kwh': raw.get('energy_kwh'),
                                'units': raw.get('units'), 'error': raw.get('error'),
                                'running': raw.get('running'), 'local_step': raw.get('intervals'),
                                'source_kind': raw.get('scope')}
            except Exception:
                states[name] = None
        evaluated = [inspect_telemetry(plant, states[plant]) for plant in ('HES','GES','RES')]
        return {
            'scope': 'SYNTHETIC_TELEMETRY_POSTCHECK_ONLY',
            'is_not_field_sensor_validation': True,
            'can_prove_freshness': False,
            'source_count': sum(states[p] is not None for p in states),
            'quality': evaluated,
            'states': states,
            'overall': ('INCOMPLETE' if any(x['quality'] == 'UNAVAILABLE' for x in evaluated)
                        else 'INVALID' if any(x['quality'] == 'INVALID' for x in evaluated)
                        else 'VALID_SYNTHETIC'),
        }

    @router.get('/api/v1/platform/engineering/readiness')
    def readiness():
        return coverage()

    @router.get('/api/v1/platform/engineering/quality')
    def quality():
        return state_report()

    @router.get('/api/v1/platform/engineering/fault-matrix')
    def fault_matrix():
        rows = generate_fault_matrix()
        return {'scope': 'SOFTWARE_VALIDATOR_INJECTION_NOT_PHYSICAL_FAULTS',
                'cases': rows, 'passed': all(r['passed'] for r in rows)}

    @router.post('/api/v1/platform/engineering/portfolio/study')
    def portfolio_study(body: PortfolioInput):
        try:
            return validate_synchronized_portfolio([r.model_dump() for r in body.rows])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @router.get('/api/v1/platform/engineering/command-attempts')
    def audit(limit: int = Query(default=30, ge=1, le=100)):
        return {'scope': 'LOCAL_HTTP_ATTEMPTS_NOT_TAMPER_PROOF_OT_AUDIT',
                'audit_db_exists': database_path().is_file(),
                'events': recent_attempts(limit)}

    @router.get('/platform/engineering', response_class=HTMLResponse)
    def page():
        return HTMLResponse(ENGINEERING_HTML)

    return router


ENGINEERING_HTML = r'''<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Autonomous Plant Platform · Mühendislik ve Güvenilirlik</title>
<style>
:root{color-scheme:dark;font-family:system-ui,-apple-system,Arial,sans-serif}
*{box-sizing:border-box}body{background:#0b1320;color:#e8f2fb;margin:0}
header{background:#152439;border-bottom:1px solid #374a61;padding:25px max(18px,calc((100vw - 1300px)/2))}
main{max-width:1300px;margin:auto;padding:20px 18px 70px}a{color:#80dcd2}
h1{font-size:25px;margin:5px 0}.muted{color:#9badc2}.caps{letter-spacing:1.5px;text-transform:uppercase;font-size:11px;color:#80dcd2}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.card{background:#19293d;border:1px solid #37516b;border-radius:12px;padding:17px;margin:12px 0;min-width:0}
.big{font-size:27px;font-weight:750;margin:7px 0}.kicker{font-size:11px;color:#98b1cd;text-transform:uppercase}
.note{background:#30291d;border:1px solid #806038;border-radius:10px;padding:14px;line-height:1.5}
h2{font-size:17px}table{width:100%;border-collapse:collapse;font-size:12px}td,th{padding:10px 8px;text-align:left;border-bottom:1px solid #35485a;vertical-align:top}
.good{color:#8cdbbb}.warn{color:#f2bc78}.bad{color:#f2979f}.tag{font-size:11px;border:1px solid #4b657d;border-radius:6px;padding:3px 7px}
button{background:#244d72;color:#fff;border:1px solid #527da4;border-radius:6px;padding:9px 14px;cursor:pointer}
pre{overflow-x:auto;white-space:pre-wrap;word-break:break-word;font-size:12px}
@media(max-width:800px){.grid{grid-template-columns:1fr}table{display:block;overflow-x:auto}}
</style></head><body>
<header><div class="caps">Autonomous Plant Platform · Engineering Lab</div><h1>Simülasyon Güvenilirliği ve Hazırlık Merkezi</h1>
<div class="muted">Canlı telemetri post-check · Senaryo boşlukları · Yerel HTTP komut denetimi</div>
<p><a href="/platform/dashboard">← Ortak panel</a> &nbsp; <a href="/platform/alarms">Alarm merkezi</a> &nbsp; <a href="/docs">API belgeleri</a></p></header>
<main><p class="note">Bu ekran <b>gerçek tesise hazır</b> onayı vermez. Zaman damgaları ölçüm kaynağından doğrulanmadığı için “freshness” ölçülmüş sayılmaz. Fiziksel korumalar, OEM doğrulaması, FAT/SAT ve siber güvenlik ayrıca gereklidir.</p>
<div class="grid"><div class="card"><div class="kicker">Sentetik telemetri</div><div id="quality" class="big">—</div></div>
<div class="card"><div class="kicker">Kaynak erişimi</div><div id="source" class="big">—</div></div>
<div class="card"><div class="kicker">QA hata enjeksiyonu</div><div id="matrix" class="big">—</div></div></div>
<div class="card"><h2>HES / GES / RES — Kalite denetimi</h2><table><thead><tr><th>Santral</th><th>Kalite</th><th>Sınırlama / sorun</th></tr></thead><tbody id="telemetry"></tbody></table></div>
<div class="card"><h2>Proje kapsamı ve açık doğrulama işleri</h2><p class="muted">IMPLEMENTED yalnızca yazılım/sentetik kapsam içindir.</p><div id="coverage-meta" class="muted"></div><table><thead><tr><th>Sistem</th><th>Özellik</th><th>Durum</th><th>Kanıt/sınır</th></tr></thead><tbody id="coverage"></tbody></table></div>
<div class="card"><h2>Yerel komut denetimi</h2><p class="muted">HTTP girişimleri kaydedilir; gerçek ekipman işleminin başarı kanıtı, kullanıcı kimlik doğrulaması veya değiştirilemez denetim kaydı değildir.</p>
<table><thead><tr><th>Zaman (UTC)</th><th>Yol</th><th>HTTP</th><th>Sonuç</th></tr></thead><tbody id="audit"></tbody></table></div>
<button id="refresh" type="button">Yenile</button><p id="feedback" role="status"></p>
</main><script>
'use strict';const by=id=>document.getElementById(id);
async function data(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function fill(id,rows,render){const dst=by(id);dst.replaceChildren();for(const row of rows){const tr=document.createElement('tr');for(const s of render(row)){const td=document.createElement('td');td.textContent=String(s);tr.append(td)}dst.append(tr)}}
let busy=false;async function refresh(){if(busy)return;busy=true;try{
const [q,c,m,a]=await Promise.all([data('/api/v1/platform/engineering/quality'),data('/api/v1/platform/engineering/readiness'),data('/api/v1/platform/engineering/fault-matrix'),data('/api/v1/platform/engineering/command-attempts')]);
by('quality').textContent=q.overall;by('source').textContent=q.source_count+'/3';by('matrix').textContent=m.cases.filter(x=>x.passed).length+'/'+m.cases.length;
fill('telemetry',q.quality,x=>[x.plant,x.quality,x.issues.join(', ')||'Sentetik değerler makul; güncellik doğrulanmadı']);
by('coverage-meta').textContent=Object.entries(c.totals).map(([k,v])=>k+': '+v).join(' · ');
fill('coverage',c.items,x=>[x.plant,x.feature,x.status,x.evidence_limit]);
fill('audit',a.events,x=>[x.utc,x.route,x.status,x.note]);
by('feedback').textContent='Yenilendi. Gerçek tesis doğrulaması yapılmadı.';
}catch(e){by('feedback').textContent='Veri yüklenemedi: '+e.message}finally{busy=false}}
by('refresh').addEventListener('click',refresh);refresh();setInterval(refresh,10000);
</script></body></html>'''
