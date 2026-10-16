
"""GES v0.5: OEM electrical envelope constrained scenario comparison.

NOT an OEM-calibrated energy model.
PV parameters, PVWatts AC conversion and Q requests remain synthetic.
Existing simulation databases and physical models are not modified.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sqlite3

from dataclasses import replace
from pathlib import Path

from demo_ges_integrated_v04 import (
    build_integrated_snapshots,
)

from demo_ges_v05_scenarios import (
    CASES,
    CASE_BY_NAME,
    _case_interval,
    _case_pipeline,
    _check_interval,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
    InverterMPPTConfig,
)

from simulator.solar.historian import SolarHistorian
from simulator.solar.solar_stress import make_stress_intervals
from simulator.solar.solar_timeseries import SolarTimeSeriesSimulator


MODEL_IDS = (
    "SMA_STP50_40",
    "SUNGROW_SG110CX_V152",
)

REQUIRED = (
    "mppt_count",
    "mppt_min_v",
    "mppt_max_v",
    "max_dc_v",
    "max_operating_current_per_mppt_a",
    "max_short_circuit_current_per_mppt_a",
)


def load_envelopes(audit_path: Path) -> tuple[dict, dict]:
    raw = audit_path.read_bytes()
    audit = json.loads(raw)
    candidates = audit.get("model_screening", {})
    result = {}

    for model in MODEL_IDS:
        supplied = candidates.get(model)

        if not isinstance(supplied, dict):
            raise ValueError(
                f"OEM denetiminde {model} bulunamadı"
            )

        values = {}

        for key in REQUIRED:
            val = supplied.get(key)

            if (
                isinstance(val, bool)
                or not isinstance(val, (int, float))
                or not math.isfinite(val)
                or val <= 0
            ):
                raise ValueError(
                    f"OEM sınırı eksik/geçersiz: {model}/{key}"
                )

            values[key] = float(val)

        count = values["mppt_count"]

        if int(count) != count:
            raise ValueError(
                f"MPPT sayısı tam sayı olmalı: {model}"
            )

        if not (
            values["mppt_min_v"]
            < values["mppt_max_v"]
            <= values["max_dc_v"]
        ):
            raise ValueError(
                f"OEM gerilim aralığı hatalı: {model}"
            )

        result[model] = values

    return result, {
        "audit_sha256": hashlib.sha256(raw).hexdigest(),
        "research_zip_sha256": audit.get("research_zip_sha256"),
        "original_oem_limitations": audit.get(
            "limitations",
            [],
        ),
    }


def guarded_pipeline(
    name: str,
    model: str,
    envelope: dict,
) -> IntegratedSolarPhysicsPipeline:
    """Apply intersection of synthetic and reported OEM limits."""

    base = _case_pipeline(name)
    assets = []
    configs = {}

    for asset in base.assets:
        iid = asset.inverter.inverter_id
        existing = base.mppt_configs[iid]
        old = existing.limits

        if len(existing.channels) > int(envelope["mppt_count"]):
            raise ValueError(
                f"{iid}: OEM MPPT giriş sayısı yetersiz"
            )

        new_min = max(
            old.min_v,
            envelope["mppt_min_v"],
        )

        new_max = min(
            old.max_v,
            envelope["mppt_max_v"],
        )

        new_absolute = min(
            old.max_dc_v,
            envelope["max_dc_v"],
        )

        if not (0 < new_min < new_max <= new_absolute):
            raise ValueError(
                f"{name}/{model}: ortak MPPT gerilim aralığı yok"
            )

        limits = replace(
            old,
            mppt_count=int(envelope["mppt_count"]),
            min_v=new_min,
            max_v=new_max,
            max_dc_v=new_absolute,
            max_operating_a=min(
                old.max_operating_a,
                envelope["max_operating_current_per_mppt_a"],
            ),
            max_short_circuit_a=min(
                old.max_short_circuit_a,
                envelope["max_short_circuit_current_per_mppt_a"],
            ),
        )

        configs[iid] = InverterMPPTConfig(
            existing.channels,
            limits,
        )

        inv = asset.inverter

        # Original 10 kW AC and synthetic efficiency remain.
        # This does NOT create a true SMA/Sungrow OEM inverter.
        inv = replace(
            inv,
            mppt_min_v=min(
                inv.mppt_min_v,
                limits.min_v,
            ),
            mppt_max_v=max(
                inv.mppt_max_v,
                limits.max_v,
            ),
            max_dc_voltage_v=max(
                inv.max_dc_voltage_v,
                limits.max_dc_v,
            ),
        )

        assets.append(
            replace(asset, inverter=inv)
        )

    return IntegratedSolarPhysicsPipeline(
        base.site,
        tuple(assets),
        configs,
    )


def read_baselines(
    source: Path,
    days: int,
) -> dict[str, float]:

    if not source.is_file():
        raise FileNotFoundError(source)

    with sqlite3.connect(
        source.resolve().as_uri() + "?mode=ro",
        uri=True,
    ) as db:

        rows = db.execute("""
            SELECT scenario, interval_count, total_energy_kwh
            FROM simulation_runs
        """).fetchall()

        problems = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    if problems:
        raise ValueError(
            f"Kaynak veritabanı anahtar hatası: {problems[:3]}"
        )

    result = {}

    for name, n, energy in rows:

        if name in result:
            raise ValueError(
                f"Kaynakta çift senaryo: {name}"
            )

        if int(n) != days * 96:
            raise ValueError(
                f"Kaynak senaryo süre uyuşmazlığı: {name}"
            )

        result[name] = float(energy)

    return result


def run(args) -> None:

    if not (1 <= args.days <= 30):
        raise ValueError(
            "Gün aralığı 1..30"
        )

    envelopes, provenance = load_envelopes(
        args.audit
    )

    baseline = read_baselines(
        args.source_db,
        args.days,
    )

    names = (
        [
            x.strip()
            for x in args.only.split(",")
            if x.strip()
        ]
        if args.only
        else [x.name for x in CASES]
    )

    if (
        not names
        or len(names) != len(set(names))
        or any(x not in CASE_BY_NAME for x in names)
    ):
        raise ValueError(
            "Senaryo listesi boş, yinelenmiş veya bilinmiyor"
        )

    if any(name not in baseline for name in names):
        raise ValueError(
            "Kaynak veritabanında seçili senaryo bulunamıyor"
        )

    output_db = (
        args.output / "historian.sqlite3"
    )

    if output_db.exists():
        raise FileExistsError(
            f"Çıktı veritabanı zaten var, korundu: {output_db}"
        )

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    intervals = tuple(
        make_stress_intervals(args.days)
    )

    if len(intervals) != args.days * 96:
        raise ValueError(
            "Stres zaman aralığı sayısı farklı"
        )

    historian = SolarHistorian(
        output_db
    )

    results = []

    for model in MODEL_IDS:
        for name in names:

            pipeline = guarded_pipeline(
                name,
                model,
                envelopes[model],
            )

            sim = SolarTimeSeriesSimulator(
                pipeline
            )

            for index, source_item in enumerate(intervals):

                record = sim.step(
                    _case_interval(
                        name,
                        source_item,
                        index,
                        pipeline,
                    )
                )

                _check_interval(record)

            energy = math.fsum(
                r.interval_energy_kwh
                for r in sim.records
            )

            reference = baseline[name]

            if energy > reference + 0.001:
                raise AssertionError(
                    "Daraltılmış limit üretimi artırdı: "
                    f"{model}/{name}"
                )

            snapshots = build_integrated_snapshots(
                pipeline
            )

            for payload in snapshots.values():

                payload["model_id"] = (
                    "APP_V05_SYNTHETIC_WITH_OEM_ENVELOPE_INTERSECTION"
                )

                payload["values"]["oem_screened_inverter_model"] = {
                    "value": model,
                    "source_id": "GES_V05_OEM_SHADOW_AUDIT",
                    "source_url": (
                        "project://outputs/ges_oem_shadow_v05/"
                        "oem_shadow_audit.json"
                    ),
                    "evidence": (
                        "Reported OEM electrical bounds; original "
                        "PDFs not independently checked; "
                        "AC and PV model synthetic"
                    ),
                }

            run_id = historian.save_simulation(
                sim,
                scenario=f"BOUND_{model}_{name}",
                inverter_snapshot_payloads=snapshots,
            )

            active_channels = sum(
                ch.offered_kw > 1e-8
                for row in sim.records
                for mppt in row.mppt_reports
                for ch in mppt.dc.channels
            )

            rejected_channels = sum(
                ch.offered_kw > 1e-8
                and ch.accepted_kw < 1e-8
                for row in sim.records
                for mppt in row.mppt_reports
                for ch in mppt.dc.channels
            )

            results.append({
                "run_id": run_id,
                "scenario": name,
                "candidate_model": model,
                "original_synthetic_kwh": round(reference, 6),
                "bounded_synthetic_kwh": round(energy, 6),
                "difference_kwh": round(
                    reference - energy,
                    6,
                ),
                "active_mppt_intervals": active_channels,
                "zero_accepted_mppt_intervals": rejected_channels,
                "interpretation": (
                    "SYNTHETIC_AC_AND_PQ_WITH_REPORTED_OEM_"
                    "MPPT_LIMIT_INTERSECTION_NOT_OEM_PRODUCTION"
                ),
            })

            print(
                f"{model:<23} {name:<25} "
                f"ref={reference:.3f} kWh | "
                f"limited={energy:.3f} kWh",
                flush=True,
            )

    with sqlite3.connect(output_db) as db:

        fk = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

        runs = db.execute(
            "SELECT COUNT(*) FROM simulation_runs"
        ).fetchone()[0]

    if fk or runs != len(results):
        raise RuntimeError(
            "OEM karşılaştırma veri bütünlüğü hatası: "
            f"{fk}, runs={runs}"
        )

    csv_path = (
        args.output / "oem_constrained_summary.csv"
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0]),
        )

        writer.writeheader()
        writer.writerows(results)

    manifest = {
        "data_kind": (
            "SIMULATED_OEM_ELECTRICAL_ENVELOPE_INTERSECTION_"
            "NOT_OEM_CALIBRATED"
        ),
        "cases": names,
        "candidate_models": MODEL_IDS,
        "days_per_case": args.days,
        "runs": runs,
        "audit_provenance": provenance,
        "limitations": [
            "Manufacturer PDFs not independently available",
            "Synthetic PV parameters, PVWatts AC and Q requests",
            "Synthetic and reported OEM MPPT limits intersected",
            "OEM nameplate power NOT modeled",
            "No full cold Voc or real grid/P-Q validation",
        ],
    }

    (
        args.output / "oem_constrained_manifest.json"
    ).write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        f"\nOEM ELECTRICAL ENVELOPE COMPARISON OK: {runs} runs"
    )

    print("CSV:", csv_path)
    print("Dashboard DB:", output_db)


def main():

    parser = argparse.ArgumentParser(
        description=__doc__
    )

    parser.add_argument(
        "--audit",
        type=Path,
        default=Path(
            "outputs/ges_oem_shadow_v05/"
            "oem_shadow_audit.json"
        ),
    )

    parser.add_argument(
        "--source-db",
        type=Path,
        default=Path(
            "outputs/ges_v05_matrix_full/"
            "historian.sqlite3"
        ),
    )

    parser.add_argument(
        "--days",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated scenarios; empty means all",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "outputs/ges_v05_oem_bound"
        ),
    )

    run(parser.parse_args())


if __name__ == "__main__":
    main()
