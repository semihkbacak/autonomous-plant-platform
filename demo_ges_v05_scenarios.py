
"""GES v0.5 synthetic scenario matrix; NO PLC/SCADA/OT access.

This module never modifies the v0.4 physics engine or existing SQLite files.
All new runs are saved to a separately selected historian database.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from dataclasses import dataclass, replace
from math import fsum, isclose
from pathlib import Path

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
    build_integrated_snapshots,
)
from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
)
from simulator.solar.historian import SolarHistorian
from simulator.solar.pq_dispatch import PQCapability
from simulator.solar.solar_stress import make_stress_intervals
from simulator.solar.solar_timeseries import SolarTimeSeriesSimulator


@dataclass(frozen=True)
class Case:
    name: str
    group: str
    description: str
    limitation: str = (
        "Sentetik girişler; gerçek tesis ölçümü değildir."
    )


CASES = (
    Case("BASELINE_PQ8", "referans",
         "İki inverter, dört MPPT; inverter başına Q talebi +8 kVAr."),
    Case("BASELINE_NO_Q", "referans",
         "P-Q sınırlaması kapalı referans modeli."),

    Case("SUNNY_110", "meteoroloji",
         "Işınımın %110'a ölçeklenmesi; gerçek açık gökyüzü modeli değil."),
    Case("OVERCAST_30", "meteoroloji",
         "Sürekli kapalı hava: ışınımın %30'u."),
    Case("DENSE_CLOUD_08", "meteoroloji",
         "Çok düşük ışınım: %8."),
    Case("MORNING_FOG", "meteoroloji",
         "Sabah erken saatlerde ışınım azaltımı."),
    Case("AFTERNOON_STORM", "meteoroloji",
         "Öğle sonrası bulut + rüzgâr + sıcaklık düşüşü."),
    Case("PASSING_CLOUDS", "meteoroloji",
         "15 dakikalık geçiş bulutları: değişken ışınım."),
    Case("LOW_LIGHT_ALL_DAY", "meteoroloji",
         "Bütün gün %3 ışınım."),
    Case("NO_SUN_ALL_DAY", "meteoroloji",
         "Işınım tamamen sıfır: DC/AC sıfır sınaması."),
    Case("DUST_AIR_PROXY", "meteoroloji",
         "Atmosferik toz için ışınım %70 vekil modeli."),
    Case("HEATWAVE", "meteoroloji",
         "Ortam sıcaklığı +18 °C; inverter termal derating değildir."),
    Case("COLD_SNAP", "meteoroloji",
         "Ortam sıcaklığı -20 °C; düşük sıcaklık duyarlılığı."),
    Case("STILL_AIR", "meteoroloji",
         "Rüzgâr sıfır, panel daha az soğur."),
    Case("WIND_COOLING", "meteoroloji",
         "Rüzgâr 10 m/s, Faiman ısı transferi duyarlılığı."),
    Case("RAIN_PROXY", "meteoroloji",
         "Yağışın yalnız ışınım/sıcaklık/rüzgâr vekil etkisi.",
         "Yağış, nem ve izolasyon arızası modelleri bulunmuyor."),

    Case("SOILING_ALL", "pv_mppt",
         "Tüm modüllerde %25 optik geçirgenlik kaybı."),
    Case("SOILING_ONE_MPPT", "pv_mppt",
         "Tek MPPT kanalında %60 optik kayıp; homojen vekil.",
         "Kısmi gölge bypass diyodu ve çoklu P-V tepeleri modellenmiyor."),
    Case("MPPT_DISCONNECT_PROXY", "pv_mppt",
         "INV_1/MPPT-1 optik girdi sıfır; açık devre vekili.",
         "Gerçek kablo kopukluğu, izolasyon ölçümü veya alarm çıkışı yok."),
    Case("STRINGS_UNBALANCED", "pv_mppt",
         "INV_1/MPPT-2 üzerinde sekiz modüllü bağımsız string."),
    Case("EAST_WEST_ARRAYS", "pv_mppt",
         "Birinci ve ikinci MPPT kanalları doğu/batı yönlü."),
    Case("SNOW_ALBEDO_PROXY", "pv_mppt",
         "Albedo 0.75; kar yüzeyi yansıması vekili.",
         "Panel üstündeki kar örtüsü ve mekanik yük modellenmiyor."),
    Case("SHORT_STRING", "pv_mppt",
         "INV_1 MPPT-1 üzerinde üç modüllük düşük Vmp string."),
    Case("LONG_STRING_VOC", "pv_mppt",
         "INV_1 MPPT-1 üzerinde 26 modüllük yüksek Voc string."),
    Case("CURRENT_LIMIT_2A", "pv_mppt",
         "INV_1 için MPPT akım limiti 2 A.",
         "Akım sınırlaması Vmp üzerinden yaklaşık hesaplanıyor."),
    Case("ISC_SCREEN_3A", "pv_mppt",
         "INV_1 için MPPT kısa devre akım sınırı 3 A."),
    Case("MPPT_WINDOW_400V", "pv_mppt",
         "INV_1 MPPT minimum çalışma gerilimi 400 V."),

    Case("INVERTER_AC_DERATE", "inverter",
         "INV_1 AC nominal gücü sentetik olarak 4 kW."),
    Case("INVERTER_EFFICIENCY_88", "inverter",
         "INV_1 PVWatts nominal verim varsayımı %88.",
         "Yaşlanma/degradasyonun kalibre edilmiş modeli değildir."),

    Case("GRID_LOSS_ALL", "isletme",
         "Bütün gün şebeke yok: AC sevk sıfır."),
    Case("GRID_LOSS_NOON", "isletme",
         "09:00–11:00 UTC şebeke kesintisi."),
    Case("GRID_CYCLING", "isletme",
         "Periyodik şebeke kaybı ve geri gelme."),
    Case("ESTOP_NOON", "isletme",
         "10:00–11:00 UTC simüle acil durdurma."),
    Case("ESTOP_REPEATED", "isletme",
         "Tekrarlanan acil durdurma olayları."),
    Case("ESTOP_ALL_DAY", "isletme",
         "Tüm gün simüle acil durdurma."),
    Case("INVERTER_TRIP_CYCLE", "isletme",
         "INV_1 tekrarlayan trip ve toparlanma."),
    Case("COMPOUND_STORM_GRID_FAULT", "isletme",
         "Öğleden sonra fırtına, şebeke ve inverter arızası kombinasyonu."),
    Case("INV1_FAULT_NOON", "isletme",
         "INV_1 öğle arıza ve toparlanma."),
    Case("INV2_FAULT_NOON", "isletme",
         "INV_2 öğle arıza ve toparlanma."),
    Case("BOTH_FAULT", "isletme",
         "İki inverter aynı anda arızalı."),
    Case("MAINT_INV1_ALL", "isletme",
         "INV_1 bütün gün bakım kilidinde."),
    Case("MAINT_INV2_NOON", "isletme",
         "INV_2 öğle bakım kilidi."),

    Case("TARGET_0", "dispatch",
         "Tesis aktif güç hedefi 0 kW."),
    Case("TARGET_4", "dispatch",
         "Tesis aktif güç hedefi 4 kW."),
    Case("TARGET_RAMP", "dispatch",
         "Aktif güç hedefi 2→10→3 kW basamaklı."),
    Case("TARGET_UNREACHABLE", "dispatch",
         "100 kW istenen hedef; karşılanamayan güç raporu."),

    Case("Q_ZERO", "pq",
         "Reaktif güç talebi 0 kVAr."),
    Case("Q_POS_6", "pq",
         "Her inverter için +6 kVAr talebi."),
    Case("Q_NEG_6", "pq",
         "Her inverter için -6 kVAr talebi."),
    Case("Q_POS_9_5", "pq",
         "Her inverter için +9.5 kVAr, P limiti düşer."),
    Case("Q_ASYMMETRIC", "pq",
         "INV_1 +8 ve INV_2 -3 kVAr talebi."),
    Case("Q_REVERSAL", "pq",
         "Öğlen +8 kVAr talepten -8 kVAr talebe geçiş; gerçek Q dinamiği değil."),
    Case("Q_THERMAL_6KVA", "pq",
         "Görünür gücü 6 kVA'ya sınırlandıran sentetik tarama.",
         "OEM sıcaklık eğrisi veya gerçek ısıl durum modellenmiyor."),
    Case("Q_THERMAL_RECOVERY", "pq",
         "Öğlen 6 kVA varsayımsal sınırlama, sonra kaldırma.",
         "Bu yalnızca haricî verilen kVA limiti senaryosudur."),
)

CASE_BY_NAME = {case.name: case for case in CASES}
assert len(CASE_BY_NAME) == len(CASES), "Duplicate case name"


def _case_pipeline(case_name: str) -> IntegratedSolarPhysicsPipeline:
    base = build_integrated_demo_pipeline()
    assets = list(base.assets)
    configurations = dict(base.mppt_configs)

    def channel_update(inverter_id: str, channel_number: int, **changes):
        old = configurations[inverter_id]
        channels = list(old.channels)

        for index, channel in enumerate(channels):
            if channel.channel == channel_number:
                channels[index] = replace(channel, **changes)

                configurations[inverter_id] = replace(
                    old,
                    channels=tuple(channels),
                )
                return

        raise ValueError(f"Missing MPPT {inverter_id}/{channel_number}")

    if case_name == "SOILING_ALL":
        for inverter_id, config in list(configurations.items()):
            for channel in config.channels:
                channel_update(
                    inverter_id,
                    channel.channel,
                    array=replace(
                        channel.array,
                        optical_transmission_factor=0.75,
                    ),
                )

    elif case_name in {"SOILING_ONE_MPPT", "MPPT_DISCONNECT_PROXY"}:
        ch = configurations["INV_1"].channels[0]

        channel_update(
            "INV_1",
            1,
            array=replace(
                ch.array,
                optical_transmission_factor=(
                    0.40 if case_name == "SOILING_ONE_MPPT" else 0.0
                ),
            ),
        )

    elif case_name == "EAST_WEST_ARRAYS":
        for inverter_id, config in list(configurations.items()):
            for ch in config.channels:
                channel_update(
                    inverter_id,
                    ch.channel,
                    surface=replace(
                        ch.surface,
                        azimuth_deg=90.0 if ch.channel == 1 else 270.0,
                        tilt_deg=35.0,
                    ),
                )

    elif case_name == "SNOW_ALBEDO_PROXY":
        for inverter_id, config in list(configurations.items()):
            for ch in config.channels:
                channel_update(
                    inverter_id,
                    ch.channel,
                    surface=replace(ch.surface, albedo=0.75),
                )

    elif case_name in {
        "SHORT_STRING",
        "LONG_STRING_VOC",
        "STRINGS_UNBALANCED",
    }:
        channel_number = 2 if case_name == "STRINGS_UNBALANCED" else 1

        ch = next(
            c for c in configurations["INV_1"].channels
            if c.channel == channel_number
        )

        module_count = {
            "SHORT_STRING": 3,
            "LONG_STRING_VOC": 26,
            "STRINGS_UNBALANCED": 8,
        }[case_name]

        channel_update(
            "INV_1",
            channel_number,
            array=replace(
                ch.array,
                modules_per_string=module_count,
            ),
        )

    elif case_name in {
        "CURRENT_LIMIT_2A",
        "ISC_SCREEN_3A",
        "MPPT_WINDOW_400V",
    }:
        old = configurations["INV_1"]

        if case_name == "CURRENT_LIMIT_2A":
            limits = replace(
                old.limits,
                max_operating_a=2.0,
            )
        elif case_name == "ISC_SCREEN_3A":
            limits = replace(
                old.limits,
                max_short_circuit_a=3.0,
            )
        else:
            limits = replace(
                old.limits,
                min_v=400.0,
            )

        configurations["INV_1"] = replace(
            old,
            limits=limits,
        )

    elif case_name in {
        "INVERTER_AC_DERATE",
        "INVERTER_EFFICIENCY_88",
    }:
        old = assets[0]

        new_inverter = replace(
            old.inverter,
            **(
                {"rated_ac_kw": 4.0}
                if case_name == "INVERTER_AC_DERATE"
                else {"nominal_efficiency": 0.88}
            ),
        )

        assets[0] = replace(
            old,
            inverter=new_inverter,
        )

    return IntegratedSolarPhysicsPipeline(
        base.site,
        tuple(assets),
        configurations,
    )


def _case_interval(case_name: str, item, index: int, pipeline):
    """Transform one synthetic 15-minute input without mutating source data."""

    slot = index % 96
    hour = item.start_utc.hour + item.start_utc.minute / 60.0

    weather = item.weather
    radiation_factor = 1.0
    temp_delta = 0.0
    wind = weather.wind_speed_m_s

    if case_name == "SUNNY_110":
        radiation_factor = 1.10

    elif case_name == "OVERCAST_30":
        radiation_factor = 0.30

    elif case_name == "DENSE_CLOUD_08":
        radiation_factor = 0.08

    elif case_name == "MORNING_FOG" and 3 <= hour < 9:
        radiation_factor = 0.20

    elif (
        case_name in {"AFTERNOON_STORM", "COMPOUND_STORM_GRID_FAULT"}
        and 10 <= hour < 15
    ):
        radiation_factor = 0.15
        temp_delta = -6.0
        wind = 9.0

    elif case_name == "PASSING_CLOUDS":
        radiation_factor = (0.18, 0.75, 0.42, 1.0)[slot % 4]

    elif case_name == "LOW_LIGHT_ALL_DAY":
        radiation_factor = 0.03

    elif case_name == "NO_SUN_ALL_DAY":
        radiation_factor = 0.0

    elif case_name == "DUST_AIR_PROXY":
        radiation_factor = 0.70

    elif case_name == "HEATWAVE":
        temp_delta = 18.0
        wind = 0.6

    elif case_name == "COLD_SNAP":
        temp_delta = -20.0

    elif case_name == "STILL_AIR":
        wind = 0.0

    elif case_name == "WIND_COOLING":
        wind = 10.0

    elif case_name == "RAIN_PROXY" and 8 <= hour < 15:
        radiation_factor = 0.35
        temp_delta = -5.0
        wind = 8.0

    if radiation_factor != 1.0:
        sample = weather.irradiance

        sample = replace(
            sample,
            ghi_w_m2=sample.ghi_w_m2 * radiation_factor,
            dni_w_m2=sample.dni_w_m2 * radiation_factor,
            dhi_w_m2=sample.dhi_w_m2 * radiation_factor,
            # Recognized SYNTHETIC source_type is retained.
        )

        weather = replace(
            weather,
            irradiance=sample,
        )

    if temp_delta or wind != weather.wind_speed_m_s:
        weather = replace(
            weather,
            ambient_temperature_c=(
                weather.ambient_temperature_c + temp_delta
            ),
            wind_speed_m_s=wind,
        )

    # Reset generic stress events; apply only named scenario events.
    grid = True
    estop = False
    faults: frozenset[str] = frozenset()
    locks: frozenset[str] = frozenset()
    target = None

    if case_name == "GRID_LOSS_ALL":
        grid = False

    elif case_name == "GRID_LOSS_NOON":
        grid = not (36 <= slot < 44)

    elif case_name == "GRID_CYCLING":
        grid = slot % 16 not in {8, 9, 10, 11}

    elif case_name == "ESTOP_NOON":
        estop = 40 <= slot < 44

    elif case_name == "ESTOP_REPEATED":
        estop = slot in {35, 36, 48, 49, 60, 61}

    elif case_name == "ESTOP_ALL_DAY":
        estop = True

    elif (
        case_name == "INVERTER_TRIP_CYCLE"
        and 32 <= slot < 60
        and slot % 8 < 3
    ):
        faults = frozenset({"INV_1"})

    elif case_name == "COMPOUND_STORM_GRID_FAULT":
        grid = not (40 <= slot < 44)

        if 48 <= slot < 54:
            faults = frozenset({"INV_1"})

    elif case_name == "INV1_FAULT_NOON" and 36 <= slot < 52:
        faults = frozenset({"INV_1"})

    elif case_name == "INV2_FAULT_NOON" and 36 <= slot < 52:
        faults = frozenset({"INV_2"})

    elif case_name == "BOTH_FAULT" and 36 <= slot < 52:
        faults = frozenset({"INV_1", "INV_2"})

    elif case_name == "MAINT_INV1_ALL":
        locks = frozenset({"INV_1"})

    elif case_name == "MAINT_INV2_NOON" and 36 <= slot < 52:
        locks = frozenset({"INV_2"})

    elif case_name == "TARGET_0":
        target = 0.0

    elif case_name == "TARGET_4":
        target = 4.0

    elif case_name == "TARGET_RAMP":
        target = 2.0 if hour < 8 else (
            10.0 if hour < 13 else 3.0
        )

    elif case_name == "TARGET_UNREACHABLE":
        target = 100.0

    capability = {}
    q_values = {}

    for asset in pipeline.assets:
        iid = asset.inverter.inverter_id
        q = 8.0
        thermal = None
        thermal_source = None

        if case_name == "Q_ZERO":
            q = 0.0

        elif case_name == "Q_POS_6":
            q = 6.0

        elif case_name == "Q_NEG_6":
            q = -6.0

        elif case_name == "Q_POS_9_5":
            q = 9.5

        elif case_name == "Q_ASYMMETRIC":
            q = 8.0 if iid == "INV_1" else -3.0

        elif case_name == "Q_REVERSAL":
            q = 8.0 if slot < 48 else -8.0

        elif case_name == "COMPOUND_STORM_GRID_FAULT":
            q = 9.5

        elif case_name in {
            "Q_THERMAL_6KVA",
            "Q_THERMAL_RECOVERY",
        }:
            q = 4.0

            if (
                case_name == "Q_THERMAL_6KVA"
                or 36 <= slot < 52
            ):
                thermal = 6.0
                thermal_source = (
                    "SYNTHETIC_DERATING_ASSUMPTION_NOT_OEM"
                )

        capability[iid] = PQCapability(
            nameplate_kva=10.0,
            rated_active_kw=min(
                10.0,
                asset.inverter.rated_ac_kw,
            ),
            temperature_limit_kva=thermal,
            temperature_limit_source=thermal_source,
        )

        q_values[iid] = q

    return replace(
        item,
        weather=weather,
        grid_available=grid,
        emergency_stop=estop,
        fault_inverter_ids=faults,
        maintenance_inverter_ids=locks,
        requested_target_kw=target,
        pq_capabilities=(
            None if case_name == "BASELINE_NO_Q"
            else capability
        ),
        reactive_requests_kvar=(
            None if case_name == "BASELINE_NO_Q"
            else q_values
        ),
    )


def _check_interval(record):
    """Independent numerical invariants for each simulated interval."""

    tol = 1e-5

    if not isclose(
        record.dispatched_power_kw * 0.25,
        record.interval_energy_kwh,
        abs_tol=tol,
        rel_tol=0,
    ):
        raise AssertionError(
            "15-minute energy balance failed"
        )

    if not isclose(
        fsum(
            x.ac_dispatched_kw
            for x in record.inverter_results
        ),
        record.dispatched_power_kw,
        abs_tol=tol,
        rel_tol=0,
    ):
        raise AssertionError(
            "Inverter -> plant dispatch balance failed"
        )

    if not isclose(
        fsum(
            x.ac_available_kw
            for x in record.inverter_results
        ),
        record.available_power_kw,
        abs_tol=tol,
        rel_tol=0,
    ):
        raise AssertionError(
            "Inverter -> plant available balance failed"
        )

    if (
        record.dispatched_power_kw < -tol
        or record.dispatched_power_kw
        > record.available_power_kw + tol
    ):
        raise AssertionError(
            "Dispatched AC exceeds available AC"
        )

    for report in record.mppt_reports:
        dc = report.dc

        if not isclose(
            fsum(c.offered_kw for c in dc.channels),
            dc.dc_offered_kw,
            abs_tol=tol,
            rel_tol=0,
        ):
            raise AssertionError(
                "MPPT DC offer total mismatch"
            )

        if not isclose(
            fsum(c.accepted_kw for c in dc.channels),
            dc.dc_accepted_kw,
            abs_tol=tol,
            rel_tol=0,
        ):
            raise AssertionError(
                "MPPT DC accepted total mismatch"
            )

        for ch in dc.channels:
            if (
                ch.accepted_kw < -tol
                or ch.accepted_kw > ch.offered_kw + tol
            ):
                raise AssertionError(
                    "Invalid accepted MPPT DC power"
                )


def run_case(
    case: Case,
    intervals,
    historian: SolarHistorian | None,
):
    pipeline = _case_pipeline(case.name)
    simulator = SolarTimeSeriesSimulator(pipeline)

    for index, item in enumerate(intervals):
        record = simulator.step(
            _case_interval(
                case.name,
                item,
                index,
                pipeline,
            )
        )

        _check_interval(record)

    run_id = None

    if historian is not None:
        run_id = historian.save_simulation(
            simulator,
            scenario=case.name,
            inverter_snapshot_payloads=(
                build_integrated_snapshots(pipeline)
            ),
        )

    records = simulator.records

    return {
        "name": case.name,
        "group": case.group,
        "description": case.description,
        "limitation": case.limitation,
        "run_id": run_id,
        "intervals": len(records),
        "energy_kwh": round(
            fsum(x.interval_energy_kwh for x in records),
            6,
        ),
        "peak_ac_kw": round(
            max(x.dispatched_power_kw for x in records),
            6,
        ),
        "dc_offered_kwh": round(
            fsum(
                r.dc.dc_offered_kw * 0.25
                for x in records
                for r in x.mppt_reports
            ),
            6,
        ),
        "dc_accepted_kwh": round(
            fsum(
                r.dc.dc_accepted_kw * 0.25
                for x in records
                for r in x.mppt_reports
            ),
            6,
        ),
        "dc_rejected_kwh": round(
            fsum(
                r.dc.dc_rejected_kw * 0.25
                for x in records
                for r in x.mppt_reports
            ),
            6,
        ),
        "ac_curtailment_kwh": round(
            fsum(
                x.curtailed_power_kw * 0.25
                for x in records
            ),
            6,
        ),
        "unserved_target_kwh": round(
            fsum(
                x.unserved_target_kw * 0.25
                for x in records
            ),
            6,
        ),
        "alarm_transitions": len(
            simulator.alarm_history
        ),
    }


def run_matrix(
    days: int,
    names: list[str],
    output: Path,
    *,
    save_database: bool = True,
):
    if type(days) is not int or not (1 <= days <= 30):
        raise ValueError(
            "Use 1..30 days; larger stress tests should run separately"
        )

    unknown = set(names) - set(CASE_BY_NAME)

    if unknown:
        raise ValueError(
            f"Unknown scenarios: {sorted(unknown)}"
        )

    if not names or len(names) != len(set(names)):
        raise ValueError(
            "Select distinct nonempty scenarios"
        )

    intervals = tuple(
        make_stress_intervals(days)
    )

    if len(intervals) != days * 96:
        raise ValueError(
            f"Stress generator yielded {len(intervals)} "
            f"intervals; expected {days * 96}"
        )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_file = output / "historian.sqlite3"

    historian = (
        SolarHistorian(db_file)
        if save_database
        else None
    )

    results = []

    for index, name in enumerate(names, start=1):
        case = CASE_BY_NAME[name]

        print(
            f"[{index}/{len(names)}] {name} ...",
            flush=True,
        )

        result = run_case(
            case,
            intervals,
            historian,
        )

        results.append(result)

        print(
            "    AC energy:",
            result["energy_kwh"],
            "kWh | peak:",
            result["peak_ac_kw"],
            "kW | run:",
            result["run_id"],
            flush=True,
        )

    csv_file = output / "scenario_results.csv"

    with csv_file.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(results[0]),
        )

        writer.writeheader()
        writer.writerows(results)

    metadata = {
        "model": (
            "GES v0.4 physics + "
            "v0.5 synthetic scenario inputs"
        ),
        "data_kind": "SYNTHETIC_SIMULATION_ONLY",
        "days_per_case": days,
        "scenario_count": len(results),
        "not_modelled": [
            "Real inverter or transformer thermal dynamics",
            "Dynamic grid voltage/frequency and protective relay response",
            "Partial-shading multi-peak IV / bypass-diode physics",
            "Reactive power physical delivery or power quality",
            "OEM-calibrated inverter and module behavior",
            "Sub-15-minute cloud flicker and control transients",
            "Measurement latency, packet loss or cybersecurity intrusion",
        ],
        "results": results,
    }

    (output / "scenario_manifest.json").write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    if historian is not None:
        with sqlite3.connect(db_file) as db:
            issues = db.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()

            n_runs = db.execute(
                "SELECT count(*) FROM simulation_runs"
            ).fetchone()[0]

        if issues:
            raise RuntimeError(
                f"SQLite foreign key problems: {issues[:5]}"
            )

        if n_runs < len(results):
            raise RuntimeError(
                "Missing saved runs"
            )

    print("\nGES V0.5 SCENARIO MATRIX OK")
    print("Scenarios:", len(results), "| Days each:", days)
    print("CSV:", csv_file)
    print("Manifest:", output / "scenario_manifest.json")

    if historian is not None:
        print("Dashboard DB:", db_file)

    return results


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List all scenarios",
    )

    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Synthetic days per case, 1..30",
    )

    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated exact scenario names",
    )

    parser.add_argument(
        "--group",
        default="",
        help="Only one group, e.g. pv_mppt or pq",
    )

    parser.add_argument(
        "--no-db",
        action="store_true",
        help="CSV/JSON only, no SQLite",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/ges_v05_scenarios"),
    )

    args = parser.parse_args()

    if args.list:
        for case in CASES:
            print(
                f"{case.name:24s} "
                f"[{case.group}] "
                f"{case.description}"
            )

        print("Total:", len(CASES))
        return

    if args.only:
        names = [
            x.strip()
            for x in args.only.split(",")
            if x.strip()
        ]
    else:
        names = [
            x.name
            for x in CASES
            if not args.group or x.group == args.group
        ]

    if not names:
        parser.error(
            "No scenarios selected; check --group"
        )

    run_matrix(
        args.days,
        names,
        args.output,
        save_database=not args.no_db,
    )


if __name__ == "__main__":
    main()
