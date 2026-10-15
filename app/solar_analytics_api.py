
"""GES v0.5 – Salt okunur üretim ve MPPT analiz paneli.

Veri kaynağı: mevcut GES SQLite Historian.
Gerçek PLC/SCADA/OT bağlantısı veya kontrol işlemi yoktur.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse


PAGE = r"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>GES – Üretim Analiz Paneli</title>

<style>
:root {
    color-scheme: dark;
    font-family: system-ui, sans-serif;
}
body {
    margin: 0;
    background: #0d1422;
    color: #e5edf8;
}
main {
    max-width: 1300px;
    margin: auto;
    padding: 24px;
}
h1 {
    font-size: 25px;
    margin: 0 0 7px;
}
h2 {
    font-size: 17px;
    margin: 0 0 12px;
}
.muted {
    color: #97a9c2;
    font-size: 13px;
}
.controls, .stats, .charts {
    display: grid;
    gap: 14px;
}
.controls {
    grid-template-columns: repeat(auto-fit, minmax(185px, 1fr));
    margin: 24px 0;
}
.stats {
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    margin-bottom: 16px;
}
.charts {
    grid-template-columns: repeat(auto-fit, minmax(460px, 1fr));
}
section, .stat {
    background: #182436;
    border: 1px solid #2a3d57;
    border-radius: 12px;
    padding: 17px;
}
.stat strong {
    display: block;
    font-size: 24px;
    margin-top: 6px;
}
label {
    font-size: 13px;
    color: #bcd0e9;
}
select {
    display: block;
    width: 100%;
    margin-top: 7px;
    padding: 10px;
    background: #263751;
    color: white;
    border: 1px solid #506580;
    border-radius: 7px;
}
svg {
    display: block;
    width: 100%;
    height: auto;
    min-height: 170px;
}
.legend {
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    font-size: 12px;
    color: #cbd5e1;
}
.legend span::before {
    content: '● ';
    color: var(--c);
}
#status {
    min-height: 20px;
    margin-top: 10px;
    color: #b5c7e0;
}
@media (max-width: 520px) {
    main { padding: 12px; }
    .charts { grid-template-columns: 1fr; }
    h1 { font-size: 21px; }
}
</style>
</head>

<body>
<main>

<h1>GES – Üretim ve MPPT Analiz Paneli</h1>

<div class="muted">
Sentetik dijital ikiz · SQLite geçmişi ·
Gerçek PLC/SCADA komutu yok · Q yalnızca talep verisidir
</div>

<div class="controls">
    <label>
        Simülasyon çalışması
        <select id="run"></select>
    </label>

    <label>
        Gün (UTC)
        <select id="day"></select>
    </label>

    <label>
        MPPT / P–Q inverter filtresi
        <select id="inverter">
            <option value="">Tüm inverterler</option>
            <option value="INV_1">INV_1</option>
            <option value="INV_2">INV_2</option>
        </select>
    </label>
</div>

<div id="status" role="status"></div>

<div class="stats">
    <div class="stat">
        <div class="muted">Günlük AC enerji</div>
        <strong id="energy">—</strong>
    </div>
    <div class="stat">
        <div class="muted">Tepe tesis AC gücü</div>
        <strong id="peak">—</strong>
    </div>
    <div class="stat">
        <div class="muted">Kabul edilen MPPT DC enerji</div>
        <strong id="dc">—</strong>
    </div>
    <div class="stat">
        <div class="muted">AC kısıntı enerjisi</div>
        <strong id="curtail">—</strong>
    </div>
</div>

<div class="charts">

    <section>
        <h2>Tesis aktif gücü (kW)</h2>
        <svg id="ac" viewBox="0 0 760 240"></svg>
        <div class="legend" id="aclegend"></div>
    </section>

    <section>
        <h2>MPPT kanal DC gücü (kW)</h2>
        <svg id="mppt" viewBox="0 0 760 240"></svg>
        <div class="legend" id="mpptlegend"></div>
    </section>

    <section>
        <h2>MPPT reddedilen DC gücü (kW)</h2>
        <svg id="loss" viewBox="0 0 760 240"></svg>
        <div class="legend" id="losslegend"></div>
    </section>

    <section>
        <h2>P–Q kapasite taraması</h2>
        <svg id="pq" viewBox="0 0 760 240"></svg>
        <div class="legend" id="pqlegend"></div>
        <p class="muted">
            Aktif limit: kW · Reaktif talep: kVAr.
            Bu Q değeri gerçek ölçülen veya üretilen Q değildir.
        </p>
    </section>

</div>

<p class="muted">
Tesis AC grafiği ve günlük özetler tüm tesise aittir.
İnverter filtresi yalnızca MPPT ve P–Q grafiklerini etkiler.
Enerji hesapları 15 dakikalık zaman aralıklarına dayanır.
</p>

</main>

<script>
"use strict";

const $ = id => document.getElementById(id);

const palette = [
    "#49b9f2",
    "#ffb454",
    "#76d7a3",
    "#db99ee",
    "#f78c88",
    "#b5c7e0"
];

const fmt = (value, digits = 2) =>
    Number(value).toLocaleString(
        "tr-TR",
        { maximumFractionDigits: digits }
    );

async function getJSON(url) {
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error(
            "HTTP " + response.status +
            ": " + await response.text()
        );
    }

    return response.json();
}

function fillSelect(element, values, labelFunction) {
    element.replaceChildren();

    for (const item of values) {
        const option = document.createElement("option");
        option.value = String(item.value);
        option.textContent = labelFunction(item);
        element.appendChild(option);
    }
}

function svgEl(tag, attrs = {}, content) {
    const element = document.createElementNS(
        "http://www.w3.org/2000/svg",
        tag
    );

    for (const [key, value] of Object.entries(attrs)) {
        element.setAttribute(key, String(value));
    }

    if (content !== undefined) {
        element.textContent = content;
    }

    return element;
}

function draw(id, series, labels) {
    const svg = $(id);
    const legend = $(id + "legend");

    svg.replaceChildren();
    legend.replaceChildren();

    const W = 760;
    const H = 240;

    const L = 60;
    const R = 18;
    const T = 15;
    const B = 32;

    const width = W - L - R;
    const height = H - T - B;

    const allValues = series.flatMap(
        item => item.values.filter(Number.isFinite)
    );

    const minValue = Math.min(0, ...allValues);
    let maxValue = Math.max(1, ...allValues);

    if (maxValue === minValue) {
        maxValue = minValue + 1;
    }

    const y = value =>
        T + height -
        (value - minValue) /
        (maxValue - minValue) * height;

    for (let i = 0; i <= 4; i++) {
        const value = minValue +
            (maxValue - minValue) * i / 4;

        const yy = y(value);

        svg.appendChild(
            svgEl("line", {
                x1: L,
                y1: yy,
                x2: W - R,
                y2: yy,
                stroke: "#34445d",
                "stroke-width": 1
            })
        );

        svg.appendChild(
            svgEl("text", {
                x: 6,
                y: yy + 4,
                fill: "#9fb2cc",
                "font-size": 12
            }, fmt(value, 1))
        );
    }

    const count = labels.length;

    for (let j = 0; j < 5; j++) {
        if (!count) break;

        const index = Math.round(
            j * Math.max(0, count - 1) / 4
        );

        const x = L +
            index * width / Math.max(1, count - 1);

        svg.appendChild(
            svgEl("text", {
                x: x,
                y: H - 9,
                fill: "#9fb2cc",
                "font-size": 11,
                "text-anchor": "middle"
            }, labels[index].slice(11, 16))
        );
    }

    series.forEach((item, i) => {
        if (!item.values.length) return;

        const color =
            item.color || palette[i % palette.length];

        const points = item.values.map((value, index) => {
            const x = L +
                index * width /
                Math.max(1, item.values.length - 1);

            return `${x},${y(Number(value) || 0)}`;
        }).join(" ");

        svg.appendChild(
            svgEl("polyline", {
                points: points,
                fill: "none",
                stroke: color,
                "stroke-width": 2,
                "stroke-linecap": "round",
                "stroke-linejoin": "round"
            })
        );

        const span = document.createElement("span");
        span.style.setProperty("--c", color);
        span.textContent = item.name;

        legend.appendChild(span);
    });
}

function buildSeries(rows, labels, key, filter) {
    const ids = [
        ...new Set(
            rows.filter(filter).map(
                item => item.inverter_id +
                    " / MPPT " + item.channel
            )
        )
    ].sort();

    return ids.map((id, i) => {
        const valuesByTime = new Map(
            rows.filter(
                item =>
                    item.inverter_id +
                    " / MPPT " + item.channel === id
            ).map(
                item => [
                    item.start_utc,
                    Number(item[key])
                ]
            )
        );

        return {
            name: id,
            color: palette[i % palette.length],
            values: labels.map(
                time => valuesByTime.get(time) || 0
            )
        };
    });
}

async function refresh() {
    const run = $("run").value;
    const day = $("day").value;

    if (!run || !day) return;

    $("status").textContent = "Veriler yükleniyor...";

    try {
        const data = await getJSON(
            `/solar/analytics/runs/${encodeURIComponent(run)}` +
            `/days/${encodeURIComponent(day)}`
        );

        const plant = data.plant;
        const mppt = data.mppt;
        const pq = data.pq;

        const selectedInverter = $("inverter").value;

        const filter = item =>
            !selectedInverter ||
            item.inverter_id === selectedInverter;

        const labels = plant.map(
            item => item.start_utc
        );

        const acEnergy = plant.reduce(
            (total, item) =>
                total + item.interval_energy_kwh,
            0
        );

        const peakPower = Math.max(
            0,
            ...plant.map(
                item => item.dispatched_power_kw
            )
        );

        const dcEnergy = mppt.reduce(
            (total, item) =>
                total + item.dc_accepted_kw * 0.25,
            0
        );

        const curtailmentEnergy = plant.reduce(
            (total, item) =>
                total + item.curtailed_power_kw * 0.25,
            0
        );

        $("energy").textContent =
            fmt(acEnergy, 3) + " kWh";

        $("peak").textContent =
            fmt(peakPower, 3) + " kW";

        $("dc").textContent =
            fmt(dcEnergy, 3) + " kWh";

        $("curtail").textContent =
            fmt(curtailmentEnergy, 3) + " kWh";

        draw("ac", [
            {
                name: "AC kullanılabilir",
                color: palette[0],
                values: plant.map(
                    item => item.available_power_kw
                )
            },
            {
                name: "AC sevk",
                color: palette[1],
                values: plant.map(
                    item => item.dispatched_power_kw
                )
            }
        ], labels);

        draw(
            "mppt",
            buildSeries(
                mppt,
                labels,
                "dc_accepted_kw",
                filter
            ),
            labels
        );

        draw(
            "loss",
            buildSeries(
                mppt,
                labels,
                "dc_rejected_kw",
                filter
            ),
            labels
        );

        const inverterIds = [
            ...new Set(
                pq.filter(filter).map(
                    item => item.inverter_id
                )
            )
        ].sort();

        const pqSeries = [];

        inverterIds.forEach((id, i) => {
            const valuesByTime = new Map(
                pq.filter(
                    item => item.inverter_id === id
                ).map(
                    item => [item.start_utc, item]
                )
            );

            pqSeries.push({
                name: id + " P limiti (kW)",
                color: palette[(2 * i) % palette.length],
                values: labels.map(
                    time =>
                        valuesByTime.get(time)
                            ?.active_limit_kw || 0
                )
            });

            pqSeries.push({
                name: id + " Q talebi (kVAr)",
                color: palette[(2 * i + 1) % palette.length],
                values: labels.map(
                    time =>
                        valuesByTime.get(time)
                            ?.requested_reactive_kvar || 0
                )
            });
        });

        draw("pq", pqSeries, labels);

        $("status").textContent =
            `${day}: ${plant.length} tesis aralığı, ` +
            `${mppt.length} MPPT ve ` +
            `${pq.length} P–Q kaydı`;

    } catch (error) {
        $("status").textContent =
            "Hata: " + error.message;

        console.error(error);
    }
}

async function changeRun() {
    const run = $("run").value;

    if (!run) return;

    try {
        const days = await getJSON(
            `/solar/analytics/runs/${encodeURIComponent(run)}/days`
        );

        fillSelect(
            $("day"),
            days.map(
                item => ({
                    ...item,
                    value: item.day
                })
            ),
            item => item.day
        );

        await refresh();

    } catch (error) {
        $("status").textContent =
            "Hata: " + error.message;
    }
}

async function init() {
    try {
        const runs = await getJSON(
            "/solar/analytics/runs"
        );

        fillSelect(
            $("run"),
            runs.map(
                item => ({
                    ...item,
                    value: item.id
                })
            ),
            item => `#${item.id} – ${item.scenario}`
        );

        if (!runs.length) {
            $("status").textContent =
                "Kayıtlı simülasyon bulunamadı.";
            return;
        }

        await changeRun();

    } catch (error) {
        $("status").textContent =
            "Hata: " + error.message;
    }
}

$("run").addEventListener("change", changeRun);
$("day").addEventListener("change", refresh);
$("inverter").addEventListener("change", refresh);

init();
</script>
</body>
</html>"""


def create_solar_analytics_router(
    db_path: str | Path,
) -> APIRouter:
    """Create read-only routes for the existing GES Historian."""

    path = Path(db_path)

    router = APIRouter(
        prefix="/solar/analytics",
        tags=["Solar analytics (read-only)"],
    )

    def query(
        sql: str,
        params: tuple = (),
    ) -> list[dict]:

        if not path.is_file():
            raise HTTPException(
                404,
                "GES historian database not found",
            )

        try:
            with sqlite3.connect(
                path.resolve().as_uri() + "?mode=ro",
                uri=True,
            ) as db:

                db.row_factory = sqlite3.Row

                return [
                    dict(row)
                    for row in db.execute(
                        sql,
                        params,
                    ).fetchall()
                ]

        except sqlite3.Error as exc:
            raise HTTPException(
                409,
                "GES database query failed",
            ) from exc

    @router.get(
        "/runs",
        operation_id="ges_analytics_runs",
    )
    def runs():

        return query("""
            SELECT
                id,
                scenario,
                interval_count,
                total_energy_kwh
            FROM simulation_runs
            ORDER BY id DESC
            LIMIT 100
        """)

    @router.get(
        "/runs/{run_id}/days",
        operation_id="ges_analytics_days",
    )
    def days(run_id: int):

        if not query(
            "SELECT 1 FROM simulation_runs WHERE id = ?",
            (run_id,),
        ):
            raise HTTPException(
                404,
                "Simulation run not found",
            )

        return query("""
            SELECT
                substr(start_utc, 1, 10) AS day,
                COUNT(*) AS intervals
            FROM production_intervals
            WHERE run_id = ?
            GROUP BY substr(start_utc, 1, 10)
            ORDER BY day
        """, (run_id,))

    @router.get(
        "/runs/{run_id}/days/{day}",
        operation_id="ges_analytics_day",
    )
    def day_data(
        run_id: int,
        day: str,
    ):

        try:
            if date.fromisoformat(day).isoformat() != day:
                raise ValueError(
                    "Non-standard date format"
                )

        except ValueError as exc:
            raise HTTPException(
                422,
                "Date must be YYYY-MM-DD",
            ) from exc

        if not query(
            "SELECT 1 FROM simulation_runs WHERE id = ?",
            (run_id,),
        ):
            raise HTTPException(
                404,
                "Simulation run not found",
            )

        plant = query("""
            SELECT
                start_utc,
                available_power_kw,
                dispatched_power_kw,
                interval_energy_kwh,
                curtailed_power_kw
            FROM production_intervals
            WHERE
                run_id = ?
                AND substr(start_utc, 1, 10) = ?
            ORDER BY start_utc
        """, (run_id, day))

        mppt = query("""
            SELECT
                start_utc,
                inverter_id,
                channel,
                vmp_v,
                dc_accepted_kw,
                dc_rejected_kw
            FROM ges_mppt_intervals
            WHERE
                run_id = ?
                AND substr(start_utc, 1, 10) = ?
            ORDER BY
                start_utc,
                inverter_id,
                channel
        """, (run_id, day))

        pq = query("""
            SELECT
                start_utc,
                inverter_id,
                requested_reactive_kvar,
                active_limit_kw
            FROM ges_pq_intervals
            WHERE
                run_id = ?
                AND substr(start_utc, 1, 10) = ?
            ORDER BY
                start_utc,
                inverter_id
        """, (run_id, day))

        return {
            "run_id": run_id,
            "day": day,
            "plant": plant,
            "mppt": mppt,
            "pq": pq,
            "reactive_power_note": (
                "Requested Q only, "
                "not measured or delivered Q"
            ),
        }

    @router.get(
        "/dashboard",
        response_class=HTMLResponse,
        operation_id="ges_analytics_dashboard",
    )
    def dashboard():

        return HTMLResponse(PAGE)

    return router
