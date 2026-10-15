"""Explicit no-go readiness gates for independently accepted plant deployment.

This report does not grant permits, assess an actual site or actuate equipment.
Evidence supplied by an operator remains UNVERIFIED until reviewed independently.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse

from app.site_shadow import ShadowStore
from simulator.telemetry_fault_lab import fault_matrix

GATES = (
    ("REQUIREMENTS", "Site-specific P&ID, asset inventory, command semantics and control philosophy"),
    ("OEM_PHYSICS", "OEM-certified device curves, parameter provenance and independent calibration"),
    ("SITE_DATA", "Authorized historian exports, calibrated meters and measured holdout validation"),
    ("PROCESS_SAFETY", "Site HAZOP/FMEA and independent PLC/protection relay/SIS review"),
    ("OT_CYBER", "IEC 62443 security zones, MFA/RBAC, audited access, secure remote connectivity"),
    ("COMMAND_GATEWAY", "Site-specific authorized adapters, fail-safe interlocks and command acknowledgments"),
    ("HIL_FAT", "Documented hardware-in-loop and factory acceptance test signed off"),
    ("SAT", "Site acceptance, negative-condition testing and commissioning sign-off"),
    ("OPS", "Backup, recovery, patch management, human on-call, escalation and maintenance plan"),
    ("LEGAL", "Grid-code, occupational safety and applicable licensing/compliance approvals"),
)


def readiness_report(evidence_dir: str | Path | None = None) -> dict[str, Any]:
    """Metadata collection, NOT a safety case or acceptance signature."""
    evidence_dir = Path(evidence_dir).expanduser() if evidence_dir else None
    gates = []
    for key, description in GATES:
        submitted = []
        if evidence_dir and evidence_dir.is_dir():
            folder = evidence_dir / key
            if folder.is_dir() and not folder.is_symlink():
                for item in sorted(folder.iterdir()):
                    if (item.is_file() and not item.is_symlink() and
                            item.suffix.lower() in ('.pdf', '.txt', '.csv', '.json') and
                            0 < item.stat().st_size <= 10_000_000):
                        digest = hashlib.sha256(item.read_bytes()).hexdigest()
                        submitted.append({"filename": item.name, "sha256": digest})
        gates.append({"gate": key, "requirement": description,
                      "evidence_submitted": submitted, "status": "INDEPENDENT_APPROVAL_NOT_VERIFIED"})
    return {"scope": "DOCUMENT_COLLECTION_ONLY_NOT_CERTIFICATION",
            "operation_mode_supported": ["SIMULATION", "SHADOW"],
            "can_connect_to_real_equipment": False,
            "real_control_authorized": False,
            "unverified_gates": len(gates), "gates": gates,
            "note": "Uploaded documents do not by themselves verify provenance, safety or sign-off."}


def create_site_readiness_router(shadow_db: str | Path, evidence_dir: str | Path | None = None) -> APIRouter:
    router = APIRouter(tags=["Offline site transition — read-only"])
    store = ShadowStore(shadow_db)

    @router.get('/api/v1/site/readiness')
    def readiness():
        return readiness_report(evidence_dir)

    @router.get('/api/v1/site/shadow/latest')
    def latest(site_id: str | None = Query(default=None, max_length=48)):
        try:
            return store.latest(site_id=site_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get('/api/v1/site/telemetry-fault-matrix')
    def telemetry_fault_matrix():
        return fault_matrix()

    @router.get('/platform/site-transition', response_class=HTMLResponse)
    def page():
        return HTML

    return router


HTML = r'''<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Site Transition Workbench — Autonomous Plant</title>
<style>body{background:#0c1725;color:#e6edf8;font:15px system-ui;margin:0}
header{background:#182c42;padding:24px max(20px,calc((100vw - 1100px)/2));border-bottom:1px solid #35506d}
main{max-width:1140px;margin:auto;padding:22px}.card{padding:18px;margin:12px 0;border:1px solid #405873;border-radius:12px;background:#1a2b40}
h1{font-size:23px}h2{font-size:17px}p,small{color:#abbed6}a{color:#79d7cb}
.warning{color:#ffd19b;border-color:#88633a}table{width:100%;border-collapse:collapse}td,th{padding:10px;text-align:left;border-bottom:1px solid #36516d}code{color:#a1d9f1}
@media(max-width:750px){table{display:block;overflow:auto}}</style></head><body>
<header><small>Autonomous Plant Platform · Saha geçişi araştırma merkezi</small>
<h1>Güvenli tesis entegrasyonu için kabul kapıları</h1><a href="/platform/dashboard">← Birleşik panele dön</a></header>
<main><div class="card warning"><b>GERÇEK KONTROL ETKİN DEĞİLDİR.</b>
Bu ekran bir tesisin işletime alınabileceğini kanıtlamaz. Gerçek komut adaptörü, bağımsız koruma doğrulaması, OEM ve saha kabulü yoktur.</div>
<div class="card"><h2>Kabul gereksinimleri</h2><table><thead><tr><th>Kapı</th><th>Kanıt / gereksinim</th><th>Durum</th></tr></thead><tbody id="gates"></tbody></table></div>
<div class="card"><h2>Salt-okunur offline SHADOW verileri</h2><p>Yalnızca yetkili kullanıcı tarafından dışa aktarılmış CSV. CSV dosyasındaki GOOD bilgisi bile kaynağın doğruluğunu kanıtlamaz.</p>
<p id="shadow">Yükleniyor...</p><table><thead><tr><th>Santral / ekipman</th><th>Ölçüm</th><th>Değer</th><th>Zaman kalitesi</th></tr></thead><tbody id="rows"></tbody></table></div>
<p id="status" role="status"></p></main><script>
'use strict';const by=id=>document.getElementById(id);
async function json(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}
function cell(value){const t=document.createElement('td');t.textContent=String(value);return t}
async function refresh(){try{const [r,s]=await Promise.all([json('/api/v1/site/readiness'),json('/api/v1/site/shadow/latest')]);
const g=by('gates');g.replaceChildren();for(const x of r.gates){const tr=document.createElement('tr');[x.gate,x.requirement,x.status].forEach(v=>tr.append(cell(v)));g.append(tr)}
by('shadow').textContent=s.status+' · '+s.measurements.length+' akış · Canlı bağlantı yok';
const m=by('rows');m.replaceChildren();for(const x of s.measurements){const tr=document.createElement('tr');
[x.plant+' / '+x.equipment_id,x.metric,x.value+' '+x.unit,x.quality+' / '+x.freshness].forEach(v=>tr.append(cell(v)));m.append(tr)}
by('status').textContent='Kumanda yetkisi: KAPALI · Kaynak doğrulama: YAPILMADI';
}catch(e){by('status').textContent='Veri alınamadı: '+e.message}}
refresh();setInterval(refresh,10000);
</script></body></html>'''
