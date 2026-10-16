
"""GES v0.5 — OEM teknik sınırlarının senaryo denetimi.

Mevcut SQLite Historian salt okunur açılır.

Bu program:
- Batın'ın öneri kataloğunu ZIP içinden okur.
- Yalnızca kaynaklı OEM sınırlarını kabul eder.
- Sentetik MPPT sonuçlarını SMA/Sungrow sınırlarıyla tarar.
- Eksik MPPT kayıtlarını denetler.
- Senaryo bazında CSV ve JSON raporları üretir.

Gerçek OEM üretim simülasyonu veya kurulum onayı değildir.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import sqlite3
import zipfile

from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


CATALOG_SUFFIX = (
    "01_oem_parameter_catalog/"
    "ges_component_parameters_proposed.csv"
)

MODELS = (
    "SMA_STP50_40",
    "SUNGROW_SG110CX_V152",
)

REQUIRED_LIMITS = (
    "mppt_count",
    "mppt_min_v",
    "mppt_max_v",
    "max_dc_v",
    "max_operating_current_per_mppt_a",
    "max_short_circuit_current_per_mppt_a",
)

PHYSICS_MISSING = {
    "TRINA_TSM445_NEG9R28": (
        "a_ref_v",
        "i_l_ref_a",
        "i_o_ref_a",
        "r_sh_ref_ohm",
        "r_s_ohm",
    ),
    "JINKO_JKM585N72HL4V": (
        "a_ref_v",
        "i_l_ref_a",
        "i_o_ref_a",
        "r_sh_ref_ohm",
        "r_s_ohm",
    ),
    "SMA_STP50_40": (
        "eta_nominal_curve_parameter",
    ),
    "SUNGROW_SG110CX_V152": (
        "eta_nominal_curve_parameter",
        "rated_ac_w",
    ),
}


def write_csv(path, fields, rows):
    with path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def load_catalog(zip_path):
    with zipfile.ZipFile(zip_path) as archive:
        matching = [
            name
            for name in archive.namelist()
            if name.endswith(CATALOG_SUFFIX)
        ]

        if len(matching) != 1:
            raise ValueError(
                "OEM ZIP içinde tek bir parametre kataloğu olmalı"
            )

        content = archive.read(
            matching[0]
        ).decode("utf-8-sig")

    records = list(
        csv.DictReader(io.StringIO(content))
    )

    required = {
        "component_id",
        "parameter",
        "value",
        "value_type",
        "verification_status",
        "source_document",
        "document_revision",
        "page_number",
        "source_url",
    }

    if not records or not required.issubset(records[0]):
        raise ValueError(
            "OEM katalog kolonları eksik"
        )

    lookup = {}

    for row in records:
        key = (
            row["component_id"].strip(),
            row["parameter"].strip(),
        )

        if key in lookup:
            raise ValueError(
                f"Yinelenen OEM parametresi: {key}"
            )

        lookup[key] = row

    return records, lookup


def published_number(catalog, model, name):
    row = catalog.get((model, name))

    if row is None:
        return None

    if row["value_type"].strip() != "oem_published":
        return None

    if (
        row["verification_status"].strip()
        != "verified_selected_document"
    ):
        return None

    if not (
        row["source_url"].startswith("https://")
        and row["source_document"].strip()
        and row["document_revision"].strip()
        and row["page_number"].strip()
    ):
        return None

    try:
        number = float(row["value"])
    except (ValueError, TypeError):
        return None

    if not (-float("inf") < number < float("inf")):
        return None

    return number


def load_limits(catalog):
    result = {}

    for model in MODELS:
        limits = {
            name: published_number(
                catalog,
                model,
                name,
            )
            for name in REQUIRED_LIMITS
        }

        limits["max_dc_current_a"] = (
            published_number(
                catalog,
                model,
                "max_dc_current_a",
            )
        )

        missing = [
            name
            for name in REQUIRED_LIMITS
            if limits[name] is None
        ]

        if missing:
            raise ValueError(
                f"{model}: OEM sınırları eksik: {missing}"
            )

        if limits["mppt_min_v"] >= limits["mppt_max_v"]:
            raise ValueError(
                f"{model}: MPPT gerilim aralığı geçersiz"
            )

        result[model] = limits

    return result


def screen_channel(row, limits):
    """MPP noktası için ön teknik sınır taraması."""

    if float(row["dc_offered_kw"]) <= 1e-9:
        return []

    reasons = []

    if float(row["vmp_v"]) < limits["mppt_min_v"] - 1e-8:
        reasons.append(
            "VMP_BELOW_OEM_MPPT_MIN"
        )

    if float(row["vmp_v"]) > limits["mppt_max_v"] + 1e-8:
        reasons.append(
            "VMP_ABOVE_OEM_MPPT_MAX"
        )

    if float(row["voc_v"]) > limits["max_dc_v"] + 1e-8:
        reasons.append(
            "VOC_ABOVE_OEM_ABSOLUTE_MAX"
        )

    if (
        float(row["imp_a"])
        > limits["max_operating_current_per_mppt_a"] + 1e-8
    ):
        reasons.append(
            "MPP_CURRENT_ABOVE_OEM_PORT_LIMIT"
        )

    if (
        float(row["isc_a"])
        > limits["max_short_circuit_current_per_mppt_a"] + 1e-8
    ):
        reasons.append(
            "ISC_ABOVE_OEM_PORT_LIMIT"
        )

    if int(row["channel"]) > int(limits["mppt_count"]):
        reasons.append(
            "MPPT_CHANNEL_NUMBER_OUT_OF_RANGE"
        )

    return reasons


def audit(research_zip, db_file, output):
    if not research_zip.is_file():
        raise FileNotFoundError(
            f"OEM araştırma ZIP bulunamadı: {research_zip}"
        )

    if not db_file.is_file():
        raise FileNotFoundError(
            f"Senaryo veritabanı bulunamadı: {db_file}"
        )

    rows, catalog = load_catalog(research_zip)
    limits = load_limits(catalog)

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    # SQLite bağlantısı yalnızca okuma yapabilir.
    db_uri = db_file.resolve().as_uri() + "?mode=ro"

    with sqlite3.connect(
        db_uri,
        uri=True,
    ) as db:

        db.row_factory = sqlite3.Row

        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table'"
            )
        }

        required_tables = {
            "simulation_runs",
            "production_intervals",
            "ges_mppt_intervals",
        }

        if not required_tables.issubset(tables):
            raise ValueError(
                "Eksik Historian tabloları: "
                f"{required_tables - tables}"
            )

        foreign_key_errors = list(
            db.execute("PRAGMA foreign_key_check")
        )

        if foreign_key_errors:
            raise ValueError(
                "SQLite foreign key hataları bulundu"
            )

        runs = [
            dict(row)
            for row in db.execute("""
                SELECT
                    id,
                    scenario,
                    interval_count,
                    total_energy_kwh
                FROM simulation_runs
                ORDER BY id
            """)
        ]

        data = list(db.execute("""
            SELECT
                run_id,
                start_utc,
                inverter_id,
                channel,
                vmp_v,
                imp_a,
                voc_v,
                isc_a,
                dc_offered_kw,
                dc_accepted_kw,
                dc_rejected_kw
            FROM ges_mppt_intervals
            ORDER BY
                run_id,
                start_utc,
                inverter_id,
                channel
        """))

        plant_counts = {
            int(row[0]): int(row[1])
            for row in db.execute("""
                SELECT run_id, COUNT(*)
                FROM production_intervals
                GROUP BY run_id
            """)
        }

        inverter_keys = set()

        if "ges_inverter_intervals" in tables:
            inverter_keys = {
                tuple(row)
                for row in db.execute("""
                    SELECT
                        run_id,
                        start_utc,
                        inverter_id
                    FROM ges_inverter_intervals
                """)
            }

    if not runs or not data:
        raise ValueError(
            "Simülasyon veya MPPT geçmişi boş"
        )

    scenarios = {
        int(run["id"]): run
        for run in runs
    }

    for run in runs:
        run_id = int(run["id"])

        if plant_counts.get(run_id) != int(
            run["interval_count"]
        ):
            raise ValueError(
                f"Run {run_id}: eksik tesis kayıtları"
            )

    actual_inverter_keys = {
        (
            int(row["run_id"]),
            row["start_utc"],
            row["inverter_id"],
        )
        for row in data
    }

    if inverter_keys:
        missing = inverter_keys - actual_inverter_keys
        unexpected = actual_inverter_keys - inverter_keys

        if missing or unexpected:
            raise ValueError(
                "Inverter/MPPT kayıt kapsamı uyumsuz: "
                f"missing={list(missing)[:3]}, "
                f"unexpected={list(unexpected)[:3]}"
            )

    # Bir senaryonun her inverterinde MPPT kanal
    # kümesi zaman boyunca eksiksiz kalmalı.
    configured = defaultdict(set)
    observed = defaultdict(set)

    for row in data:
        run_id = int(row["run_id"])
        iid = row["inverter_id"]
        channel = int(row["channel"])

        configured[(run_id, iid)].add(channel)

        observed[
            (run_id, row["start_utc"], iid)
        ].add(channel)

    for (run_id, stamp, iid), channels in observed.items():
        if channels != configured[(run_id, iid)]:
            raise ValueError(
                "Eksik MPPT kanal kaydı: "
                f"run={run_id}, inverter={iid}, time={stamp}"
            )

    metrics = defaultdict(Counter)
    detail = []
    currents = defaultdict(float)

    for row in data:
        run_id = int(row["run_id"])

        if run_id not in scenarios:
            raise ValueError(
                "Bilinmeyen run_id"
            )

        for model in MODELS:
            key = (run_id, model)
            reasons = screen_channel(
                row,
                limits[model],
            )

            metrics[key]["all_rows"] += 1

            if float(row["dc_offered_kw"]) <= 1e-9:
                metrics[key]["idle_rows"] += 1
                continue

            metrics[key]["active_rows"] += 1

            if reasons:
                metrics[key]["flagged_rows"] += 1
            else:
                metrics[key]["passing_rows"] += 1

            for reason in reasons:
                metrics[key][reason] += 1

            current_key = (
                run_id,
                model,
                row["inverter_id"],
                row["start_utc"],
            )

            currents[current_key] += float(
                row["imp_a"]
            )

            if reasons:
                detail.append({
                    "run_id": run_id,
                    "scenario": scenarios[run_id]["scenario"],
                    "candidate_oem_inverter": model,
                    "sim_inverter": row["inverter_id"],
                    "start_utc": row["start_utc"],
                    "channel": row["channel"],
                    "vmp_v": row["vmp_v"],
                    "voc_v": row["voc_v"],
                    "imp_a": row["imp_a"],
                    "isc_a": row["isc_a"],
                    "dc_offered_kw_synthetic": (
                        row["dc_offered_kw"]
                    ),
                    "flags": ";".join(reasons),
                })

    # OEM toplam DC akım sınırı mevcutsa ayrıca kontrol et.
    for (run_id, model, iid, stamp), amps in currents.items():
        max_current = limits[model]["max_dc_current_a"]

        if (
            max_current is not None
            and amps > max_current + 1e-8
        ):
            metrics[
                (run_id, model)
            ]["total_input_current_flags"] += 1

    summary = []

    for run in runs:
        run_id = int(run["id"])

        for model in MODELS:
            stat = metrics[(run_id, model)]

            active = stat["active_rows"]
            flagged = stat["flagged_rows"]

            flag_types = sorted(
                name
                for name, count in stat.items()
                if count > 0
                and name.startswith((
                    "VMP_",
                    "VOC_",
                    "MPP_",
                    "ISC_",
                    "MPPT_",
                ))
            )

            summary.append({
                "run_id": run_id,
                "scenario": run["scenario"],
                "candidate_oem_inverter": model,
                "synthetic_plant_energy_kwh": (
                    run["total_energy_kwh"]
                ),
                "plant_intervals": plant_counts.get(
                    run_id,
                    0,
                ),
                "active_mppt_rows": active,
                "passing_mppt_rows": (
                    stat["passing_rows"]
                ),
                "flagged_mppt_rows": flagged,
                "flagged_pct": (
                    round(100 * flagged / active, 3)
                    if active
                    else 0.0
                ),
                "total_input_current_flags": (
                    stat["total_input_current_flags"]
                ),
                "flag_types": ";".join(flag_types),
                "interpretation": (
                    "OEM_LIMIT_SHADOW_ONLY_NOT_OEM_PRODUCTION"
                ),
            })

    write_csv(
        output / "oem_shadow_summary.csv",
        list(summary[0]),
        summary,
    )

    detail_fields = [
        "run_id",
        "scenario",
        "candidate_oem_inverter",
        "sim_inverter",
        "start_utc",
        "channel",
        "vmp_v",
        "voc_v",
        "imp_a",
        "isc_a",
        "dc_offered_kw_synthetic",
        "flags",
    ]

    write_csv(
        output / "oem_shadow_flag_details.csv",
        detail_fields,
        detail,
    )

    write_csv(
        output / "oem_parameter_evidence.csv",
        list(rows[0]),
        rows,
    )

    missing_physics = {}

    for model, required_fields in PHYSICS_MISSING.items():
        missing_physics[model] = [
            name
            for name in required_fields
            if published_number(
                catalog,
                model,
                name,
            ) is None
        ]

    report = {
        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "research_zip_sha256": hashlib.sha256(
            research_zip.read_bytes()
        ).hexdigest(),
        "scenario_database": str(db_file),
        "scenario_runs": len(runs),
        "mppt_rows": len(data),
        "oem_catalog_rows": len(rows),
        "evidence_types": dict(
            Counter(
                row["value_type"]
                for row in rows
            )
        ),
        "verification_statuses": dict(
            Counter(
                row["verification_status"]
                for row in rows
            )
        ),
        "missing_for_full_physics": missing_physics,
        "model_screening": limits,
        "flags_total": len(detail),
        "limitations": [
            "OEM source classifications originate from "
            "the supplied research package.",
            "Original manufacturer PDFs are not "
            "included in the ZIP.",
            "The scenario powers are synthetic.",
            "No new OEM energy simulation was run.",
            "This is an electrical envelope screening, "
            "not an installation approval.",
            "De Soto and full inverter efficiency "
            "calibration remain incomplete.",
            "Requested Q is not measured delivered Q.",
        ],
    }

    report_path = output / "oem_shadow_audit.json"

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== GES OEM SHADOW AUDIT ===")
    print("Scenario runs:", len(runs))
    print("MPPT records:", len(data))
    print("OEM catalog records:", len(rows))

    for model in MODELS:
        affected = sum(
            row["flagged_mppt_rows"]
            for row in summary
            if row["candidate_oem_inverter"] == model
        )

        print(
            f"{model}: {affected} MPPT "
            "kaydı teknik sınır taramasında işaretlendi"
        )

    print("\nGES OEM SHADOW AUDIT OK")
    print("Report directory:", output.resolve())
    print(
        "NOT: Bu bir OEM üretim simülasyonu değildir."
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--research-zip",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--db",
        type=Path,
        default=Path(
            "outputs/ges_v05_matrix_full/historian.sqlite3"
        ),
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=Path(
            "outputs/ges_oem_shadow_v05"
        ),
    )

    args = parser.parse_args()

    audit(
        args.research_zip,
        args.db,
        args.out,
    )


if __name__ == "__main__":
    main()
