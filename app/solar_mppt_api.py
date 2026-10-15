
"""Read-only GES MPPT and P-Q API."""
from __future__ import annotations

import json
import sqlite3

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse


def create_solar_mppt_router(
    db_path: str | Path,
) -> APIRouter:

    path = Path(db_path)

    router = APIRouter(
        prefix="/solar/mppt",
        tags=["Solar MPPT history"],
    )

    def connect() -> sqlite3.Connection:

        if not path.is_file():
            raise HTTPException(
                404,
                "Historian database not found",
            )

        db = sqlite3.connect(
            path.resolve().as_uri() + "?mode=ro",
            uri=True,
        )

        db.row_factory = sqlite3.Row

        return db

    @router.get(
        "/runs",
        operation_id="solar_mppt_runs_v04",
    )
    def runs():

        with connect() as db:

            try:
                records = db.execute("""
                    SELECT
                        sr.id,
                        sr.scenario,
                        sr.created_at_utc,
                        sr.interval_count,
                        sr.total_energy_kwh,
                        COUNT(mi.channel) AS mppt_record_count

                    FROM simulation_runs AS sr

                    JOIN ges_mppt_intervals AS mi
                        ON mi.run_id = sr.id

                    GROUP BY sr.id

                    ORDER BY sr.id DESC

                    LIMIT 100
                """).fetchall()

            except sqlite3.OperationalError as exc:
                raise HTTPException(
                    409,
                    "MPPT schema not initialized",
                ) from exc

        return [dict(row) for row in records]

    @router.get(
        "/runs/{run_id}/intervals",
        operation_id="solar_mppt_intervals_v04",
    )
    def intervals(
        run_id: int,
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
        inverter_id: str | None = None,
        channel: int | None = Query(None, ge=1),
    ):

        conditions = ["run_id = ?"]
        args: list = [run_id]

        if inverter_id is not None:
            conditions.append("inverter_id = ?")
            args.append(inverter_id)

        if channel is not None:
            conditions.append("channel = ?")
            args.append(channel)

        sql = (
            "SELECT * FROM ges_mppt_intervals WHERE "
            + " AND ".join(conditions)
            + " ORDER BY start_utc, inverter_id, channel "
            + "LIMIT ? OFFSET ?"
        )

        with connect() as db:

            existing = db.execute(
                "SELECT 1 FROM simulation_runs WHERE id = ?",
                (run_id,),
            ).fetchone()

            if existing is None:
                raise HTTPException(
                    404,
                    "Unknown simulation run",
                )

            try:
                records = db.execute(
                    sql,
                    (*args, limit, offset),
                ).fetchall()

            except sqlite3.OperationalError as exc:
                raise HTTPException(
                    409,
                    "MPPT schema not initialized",
                ) from exc

        result = []

        for row in records:
            item = dict(row)

            item["reasons"] = json.loads(
                item.pop("reasons_json")
            )

            item["warnings"] = json.loads(
                item.pop("warnings_json")
            )

            result.append(item)

        return result

    @router.get(
        "/runs/{run_id}/pq",
        operation_id="solar_pq_history_v04",
    )
    def pq_history(
        run_id: int,
        limit: int = Query(500, ge=1, le=5000),
    ):

        with connect() as db:

            try:
                records = db.execute("""
                    SELECT *
                    FROM ges_pq_intervals
                    WHERE run_id = ?
                    ORDER BY start_utc, inverter_id
                    LIMIT ?
                """, (
                    run_id,
                    limit,
                )).fetchall()

            except sqlite3.OperationalError as exc:
                raise HTTPException(
                    409,
                    "P-Q history schema not initialized",
                ) from exc

        values = []

        for row in records:

            item = dict(row)

            item["warnings"] = json.loads(
                item.pop("warnings_json")
            )

            item["reactive_value_kind"] = (
                "REQUEST_NOT_MEASURED"
            )

            values.append(item)

        return values

    @router.get(
        "/dashboard",
        response_class=HTMLResponse,
        operation_id="solar_mppt_dashboard_v04",
    )
    def dashboard():

        return HTMLResponse("""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>GES v0.4 - MPPT Kanal Geçmişi</title>
<style>
body {
    font: 15px system-ui;
    background: #111827;
    color: #e5e7eb;
    margin: 25px;
}
h1 { font-size: 23px; }
.panel {
    background: #1f2937;
    padding: 17px;
    border-radius: 12px;
}
input, button {
    padding: 9px;
    color: #e5e7eb;
    background: #374151;
    border: 1px solid #6b7280;
    border-radius: 5px;
}
table {
    border-collapse: collapse;
    width: 100%;
    font-size: 13px;
    margin-top: 14px;
}
td, th {
    border-bottom: 1px solid #374151;
    text-align: left;
    padding: 9px;
}
small { color: #9ca3af; }
.wrap { overflow: auto; }
</style>
</head>
<body>
<h1>GES – MPPT Kanal Geçmişi (v0.4)</h1>
<p>
<small>
Sentetik simülasyon · Kayıtlı DC verileri ·
Gerçek cihaz komutu yok · Q ölçümü yok
</small>
</p>
<div class="panel">
<label>
Run ID:
<input id="run" type="number" min="1" value="1">
</label>
<label>
İnverter:
<input id="inverter" placeholder="INV_1 (opsiyonel)">
</label>
<button id="load">Kayıtları getir</button>
<p id="status"></p>
<div class="wrap">
<table>
<thead>
<tr>
<th>Başlangıç UTC</th>
<th>İnverter</th>
<th>MPPT</th>
<th>Vmp (V)</th>
<th>Imp (A)</th>
<th>DC teklif (kW)</th>
<th>DC kabul (kW)</th>
<th>DC ret (kW)</th>
<th>Neden</th>
</tr>
</thead>
<tbody id="rows"></tbody>
</table>
</div>
</div>
<script>
const status = document.getElementById('status');
const rows = document.getElementById('rows');

const esc = s => String(s).replace(
    /[&<>"']/g,
    c => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[c])
);

async function load() {
    status.textContent = 'Yükleniyor...';
    rows.innerHTML = '';

    const run = document.getElementById('run').value;
    const inv = document.getElementById('inverter').value.trim();

    let url = `/solar/mppt/runs/${encodeURIComponent(run)}/intervals?limit=5000`;

    if (inv) {
        url += '&inverter_id=' + encodeURIComponent(inv);
    }

    try {
        const response = await fetch(url);
        const data = await response.json();

        if (!response.ok) {
            throw Error(JSON.stringify(data));
        }

        status.textContent =
            data.length + ' kanal kaydı gösteriliyor (en fazla 5000)';

        for (const x of data) {
            const tr = document.createElement('tr');

            const values = [
                x.start_utc,
                x.inverter_id,
                x.channel,
                x.vmp_v.toFixed(1),
                x.imp_a.toFixed(2),
                x.dc_offered_kw.toFixed(3),
                x.dc_accepted_kw.toFixed(3),
                x.dc_rejected_kw.toFixed(3),
                x.reasons.join(', ')
            ];

            tr.innerHTML = values
                .map(v => '<td>' + esc(v) + '</td>')
                .join('');

            rows.appendChild(tr);
        }

    } catch (error) {
        status.textContent = 'Hata: ' + error.message;
    }
}

document.getElementById('load').addEventListener(
    'click',
    load
);

load();
</script>
</body>
</html>""")

    return router
