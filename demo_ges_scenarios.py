
"""Autonomous Plant Platform - GES Scenario Laboratory.

150 anlik senaryo + 13 zaman serisi kampanyasi.
Sadece sentetik simulasyon. PLC/SCADA/OT komutu yoktur.
Mevcut GES v0.4 fizik motorunu degistirmez.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3

from dataclasses import dataclass, replace
from pathlib import Path

from demo_ges_integrated_v04 import (
    build_integrated_demo_pipeline,
    build_integrated_snapshots,
)

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
    InverterMPPTConfig,
)

from simulator.solar.historian import SolarHistorian
from simulator.solar.pq_dispatch import PQCapability

from simulator.solar.solar_stress import (
    make_stress_intervals,
)

from simulator.solar.solar_timeseries import (
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


@dataclass(frozen=True)
class Case:
    name: str
    family: str

    irradiance: float = 1.0
    ambient_c: float | None = None
    wind_m_s: float | None = None

    transmission: float | None = None
    channel: tuple[str, int] | None = None

    tilt_deg: float | None = None
    azimuth_deg: float | None = None
    modules_per_string: int | None = None

    operating_a: float | None = None
    isc_limit_a: float | None = None

    voltage_min_v: float | None = None
    voltage_max_v: float | None = None
    absolute_max_v: float | None = None

    grid: bool = True
    stop: bool = False

    faults: tuple[str, ...] = ()
    locks: tuple[str, ...] = ()

    target_kw: float | None = None

    q_kvar: float | None = 0.0
    kva: float = 10.0
    thermal_kva: float | None = None

    bad: str = ""
    expect_error: bool = False


# ============================================================
# 150 SCENARIOS
# ============================================================

def catalog() -> list[Case]:

    cases = [
        Case("reference", "normal"),
    ]

    # Sunlight variations
    for x in (
        0, .01, .05, .1, .25, .4,
        .6, .8, 1.1, 1.3, 1.5,
    ):
        cases.append(
            Case(
                f"irradiance_{x:g}",
                "weather",
                irradiance=x,
            )
        )

    # Ambient temperature
    for x in (-25, -10, 0, 10, 25, 40, 55, 70):
        cases.append(
            Case(
                f"ambient_{x}",
                "thermal",
                ambient_c=x,
            )
        )

    # Wind cooling
    for x in (0, .2, 1, 2, 4, 8, 15, 25):
        cases.append(
            Case(
                f"wind_{x:g}",
                "thermal",
                wind_m_s=x,
            )
        )

    # Optical losses - approximate soiling/occlusion proxy
    for x in (0, .05, .2, .4, .65, .8, .95):

        cases.append(
            Case(
                f"optical_all_{x:g}",
                "soiling_proxy",
                transmission=x,
            )
        )

        cases.append(
            Case(
                f"optical_one_{x:g}",
                "channel_proxy",
                transmission=x,
                channel=("INV_1", 1),
            )
        )

    # PV array tilt
    for x in (0, 15, 45, 60, 85):
        cases.append(
            Case(
                f"tilt_{x}",
                "geometry",
                tilt_deg=x,
                channel=("INV_2", 2),
            )
        )

    # Array azimuth
    for x in (0, 90, 135, 225, 270):
        cases.append(
            Case(
                f"azimuth_{x}",
                "geometry",
                azimuth_deg=x,
                channel=("INV_1", 2),
            )
        )

    # Series-connected modules
    for x in (5, 7, 8, 9, 11, 12, 14, 16, 20):
        cases.append(
            Case(
                f"series_modules_{x}",
                "electrical",
                modules_per_string=x,
                channel=("INV_1", 2),
            )
        )

    # MPPT operating-current limits
    for x in (.5, 1, 3, 5, 10, 15, 20, 30):
        cases.append(
            Case(
                f"mppt_current_{x:g}",
                "electrical",
                operating_a=x,
            )
        )

    # Short-circuit-current limits
    for x in (1, 5, 10, 20, 40):
        cases.append(
            Case(
                f"mppt_isc_{x:g}",
                "electrical",
                isc_limit_a=x,
            )
        )

    cases.extend([
        Case(
            "narrow_mppt_window",
            "electrical",
            voltage_min_v=450,
        ),
        Case(
            "dc_voc_rejection",
            "electrical",
            voltage_max_v=400,
            absolute_max_v=420,
        ),
    ])

    # Availability, alarms and operational interlocks
    cases.extend([
        Case("grid_loss", "availability", grid=False),
        Case("emergency_stop", "availability", stop=True),

        Case(
            "fault_inv1",
            "availability",
            faults=("INV_1",),
        ),
        Case(
            "fault_inv2",
            "availability",
            faults=("INV_2",),
        ),
        Case(
            "fault_both",
            "availability",
            faults=("INV_1", "INV_2"),
        ),
        Case(
            "maintenance_inv1",
            "availability",
            locks=("INV_1",),
        ),
        Case(
            "maintenance_inv2",
            "availability",
            locks=("INV_2",),
        ),
        Case(
            "fault_maintenance",
            "availability",
            faults=("INV_1",),
            locks=("INV_2",),
        ),
        Case(
            "grid_and_fault",
            "availability",
            grid=False,
            faults=("INV_1",),
        ),
        Case(
            "stop_and_grid",
            "availability",
            grid=False,
            stop=True,
        ),
    ])

    # Reactive power screening
    for x in (0, .5, 2, 4, 6, 8, 9.5, 10):
        cases.append(
            Case(
                f"reactive_q_{x:g}",
                "pq",
                q_kvar=x,
            )
        )

    # External synthetic thermal-capability restrictions
    for x in (5, 6, 8, 9, 10):
        cases.append(
            Case(
                f"thermal_kva_{x:g}",
                "pq",
                thermal_kva=x,
            )
        )

    # Active-power scheduling / curtailment
    for x in (0, .1, 1, 2, 4, 6, 8, 12, 20, 50):
        cases.append(
            Case(
                f"plant_target_{x:g}",
                "dispatch",
                target_kw=x,
            )
        )

    # Deterministic combined conditions
    for i in range(24):
        cases.append(
            Case(
                f"combined_{i:02d}",
                "combined",
                irradiance=(
                    .15, .35, .6, 1.0, 1.3
                )[i % 5],
                ambient_c=(
                    -8, 15, 33, 53
                )[i % 4],
                wind_m_s=(
                    .5, 3, 11
                )[i % 3],
                transmission=(
                    .45, .75, .95
                )[i % 3],
                channel=(
                    ("INV_1", 1)
                    if i % 2
                    else ("INV_2", 2)
                ),
                q_kvar=(0, 3, 6, 8)[i % 4],
                target_kw=(
                    None, 4, 8, 15
                )[i % 4],
                grid=i % 11 != 0,
                faults=(
                    ("INV_1",)
                    if i % 13 == 0
                    else ()
                ),
            )
        )

    # Inputs that MUST be rejected.
    invalid_cases = (
        ("bad_negative_irradiance", {
            "irradiance": -1,
        }),
        ("bad_nan_irradiance", {
            "irradiance": float("nan"),
        }),
        ("bad_wind", {
            "wind_m_s": -2,
        }),
        ("bad_ambient", {
            "ambient_c": -300,
        }),
        ("bad_target", {
            "target_kw": -1,
        }),
        ("bad_unknown_fault", {
            "faults": ("NOT_PRESENT",),
        }),
        ("bad_unknown_lock", {
            "locks": ("NOT_PRESENT",),
        }),
        ("bad_q_too_large", {
            "q_kvar": 11,
        }),
        ("bad_q_nan", {
            "q_kvar": float("nan"),
        }),
        ("bad_transmission", {
            "transmission": 1.1,
        }),
        ("bad_negative_transmission", {
            "transmission": -.1,
        }),
        ("bad_modules", {
            "modules_per_string": 0,
        }),
        ("bad_current_limit", {
            "operating_a": 0,
        }),
        ("bad_tilt", {
            "tilt_deg": 100,
        }),
        ("bad_duplicate_channels", {
            "bad": "duplicate_mppt",
        }),
        ("bad_too_many_strings", {
            "bad": "strings_exceeded",
        }),
        ("bad_missing_q_mapping", {
            "bad": "missing_q",
        }),
    )

    for name, changes in invalid_cases:
        cases.append(
            Case(
                name,
                "invalid_input",
                expect_error=True,
                **changes,
            )
        )

    assert len(cases) == 150
    assert len({c.name for c in cases}) == 150

    return cases


# ============================================================
# BUILD INDEPENDENT MPPT CONFIGURATION
# ============================================================

def pipeline_for(case: Case) -> IntegratedSolarPhysicsPipeline:

    baseline = build_integrated_demo_pipeline()

    config_map = dict(baseline.mppt_configs)

    for iid, config in config_map.items():

        channels = []

        for item in config.channels:

            applies = (
                case.channel is None
                or case.channel == (iid, item.channel)
            )

            array = item.array
            surface = item.surface

            if applies:

                if case.transmission is not None:
                    array = replace(
                        array,
                        optical_transmission_factor=(
                            case.transmission
                        ),
                    )

                if case.modules_per_string is not None:
                    array = replace(
                        array,
                        modules_per_string=(
                            case.modules_per_string
                        ),
                    )

                if case.bad == "strings_exceeded":
                    array = replace(
                        array,
                        parallel_strings=2,
                    )

                if case.tilt_deg is not None:
                    surface = replace(
                        surface,
                        tilt_deg=case.tilt_deg,
                    )

                if case.azimuth_deg is not None:
                    surface = replace(
                        surface,
                        azimuth_deg=case.azimuth_deg,
                    )

            channels.append(
                replace(
                    item,
                    array=array,
                    surface=surface,
                )
            )

        if (
            case.bad == "duplicate_mppt"
            and iid == "INV_1"
        ):
            channels[1] = replace(channels[0])

        limits = config.limits

        if case.operating_a is not None:
            limits = replace(
                limits,
                max_operating_a=case.operating_a,
            )

        if case.isc_limit_a is not None:
            limits = replace(
                limits,
                max_short_circuit_a=case.isc_limit_a,
            )

        if case.voltage_min_v is not None:
            limits = replace(
                limits,
                min_v=case.voltage_min_v,
            )

        if case.voltage_max_v is not None:
            limits = replace(
                limits,
                max_v=case.voltage_max_v,
            )

        if case.absolute_max_v is not None:
            limits = replace(
                limits,
                max_dc_v=case.absolute_max_v,
            )

        config_map[iid] = InverterMPPTConfig(
            tuple(channels),
            limits,
        )

    return IntegratedSolarPhysicsPipeline(
        baseline.site,
        baseline.assets,
        config_map,
    )


# ============================================================
# PHYSICAL AND MATHEMATICAL INVARIANTS
# ============================================================

def validate_report(report) -> None:

    plant = report.plant

    assert math.isclose(
        plant.available_power_kw,
        sum(
            r.ac_available_kw
            for r in plant.inverter_results
        ),
        abs_tol=1e-5,
    )

    assert math.isclose(
        plant.dispatched_power_kw,
        sum(
            r.ac_dispatched_kw
            for r in plant.inverter_results
        ),
        abs_tol=1e-5,
    )

    assert math.isclose(
        plant.curtailed_power_kw,
        sum(
            r.curtailment_kw
            for r in plant.inverter_results
        ),
        abs_tol=1e-5,
    )

    assert (
        0
        <= plant.dispatched_power_kw
        <= plant.available_power_kw + 1e-5
    )

    ids = {
        item.inverter_id
        for item in report.mppt_reports
    }

    assert ids == {
        item.inverter_id
        for item in plant.inverter_results
    }

    for mppt_report in report.mppt_reports:

        dc = mppt_report.dc

        inverter = next(
            item
            for item in plant.inverter_results
            if item.inverter_id == mppt_report.inverter_id
        )

        assert math.isclose(
            dc.dc_offered_kw,
            inverter.dc_offered_kw,
            abs_tol=1e-5,
        )

        assert math.isclose(
            dc.dc_offered_kw,
            sum(
                channel.offered_kw
                for channel in dc.channels
            ),
            abs_tol=1e-5,
        )

        assert math.isclose(
            dc.dc_accepted_kw,
            sum(
                channel.accepted_kw
                for channel in dc.channels
            ),
            abs_tol=1e-5,
        )

        if inverter.status != "BLOCKED":
            assert math.isclose(
                dc.dc_accepted_kw,
                inverter.dc_accepted_kw,
                abs_tol=1e-5,
            )

        for channel in dc.channels:

            assert channel.offered_kw >= 0
            assert channel.accepted_kw >= 0

            assert (
                channel.accepted_kw
                <= channel.offered_kw + 1e-6
            )

            assert math.isclose(
                channel.rejected_kw,
                channel.offered_kw - channel.accepted_kw,
                abs_tol=1e-5,
            )

    if (
        not plant.grid_available
        or plant.emergency_stop
    ):
        assert plant.dispatched_power_kw == 0


# ============================================================
# SINGLE-INSTANT SCENARIO
# ============================================================

def simulate_case(case: Case, weather):

    pipeline = pipeline_for(case)

    sample = weather.irradiance

    altered_weather = replace(
        weather,
        irradiance=replace(
            sample,
            ghi_w_m2=(
                sample.ghi_w_m2 * case.irradiance
            ),
            dni_w_m2=(
                sample.dni_w_m2 * case.irradiance
            ),
            dhi_w_m2=(
                sample.dhi_w_m2 * case.irradiance
            ),
        ),
        ambient_temperature_c=(
            case.ambient_c
            if case.ambient_c is not None
            else weather.ambient_temperature_c
        ),
        wind_speed_m_s=(
            case.wind_m_s
            if case.wind_m_s is not None
            else weather.wind_speed_m_s
        ),
    )

    pq_kwargs = {}

    if case.q_kvar is not None:

        pq_kwargs = {
            "pq_capabilities": {
                iid: PQCapability(
                    nameplate_kva=case.kva,
                    rated_active_kw=10.0,
                    temperature_limit_kva=(
                        case.thermal_kva
                    ),
                    temperature_limit_source=(
                        "SYNTHETIC_SCENARIO"
                        if case.thermal_kva is not None
                        else None
                    ),
                )
                for iid in pipeline.inverter_ids
            },
            "reactive_requests_kvar": {
                iid: case.q_kvar
                for iid in pipeline.inverter_ids
            },
        }

    if case.bad == "missing_q":
        pq_kwargs.pop(
            "reactive_requests_kvar",
            None,
        )

    report = pipeline.simulate(
        altered_weather,
        requested_target_kw=case.target_kw,
        grid_available=case.grid,
        emergency_stop=case.stop,
        fault_inverter_ids=frozenset(case.faults),
        maintenance_inverter_ids=frozenset(case.locks),
        **pq_kwargs,
    )

    validate_report(report)

    return report


def write_csv(path: Path, records: list[dict]):

    if not records:
        return

    with path.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=records[0].keys(),
        )

        writer.writeheader()
        writer.writerows(records)


# ============================================================
# RUN ALL 150 SNAPSHOT SCENARIOS
# ============================================================

def run_matrix(weather, output: Path) -> tuple[int, int]:

    rows = []
    failures = 0

    cases = catalog()

    for case in cases:

        try:
            report = simulate_case(case, weather)

            if case.expect_error:
                raise AssertionError(
                    "INVALID INPUT WAS ACCEPTED"
                )

            plant = report.plant

            rows.append({
                "name": case.name,
                "category": case.family,
                "verdict": "PASS",
                "available_kw": round(
                    plant.available_power_kw, 6
                ),
                "dispatched_kw": round(
                    plant.dispatched_power_kw, 6
                ),
                "curtailed_kw": round(
                    plant.curtailed_power_kw, 6
                ),
                "mppt_dc_kw": round(
                    sum(
                        r.dc.dc_accepted_kw
                        for r in report.mppt_reports
                    ),
                    6,
                ),
                "details": ";".join(
                    plant.reasons
                ),
            })

        except (ValueError, TypeError) as exc:

            expected = case.expect_error

            if not expected:
                failures += 1

            rows.append({
                "name": case.name,
                "category": case.family,
                "verdict": (
                    "EXPECTED_REJECTION"
                    if expected
                    else "FAIL"
                ),
                "available_kw": "",
                "dispatched_kw": "",
                "curtailed_kw": "",
                "mppt_dc_kw": "",
                "details": str(exc),
            })

        except Exception as exc:

            failures += 1

            rows.append({
                "name": case.name,
                "category": case.family,
                "verdict": "FAIL",
                "available_kw": "",
                "dispatched_kw": "",
                "curtailed_kw": "",
                "mppt_dc_kw": "",
                "details": (
                    f"{type(exc).__name__}: {exc}"
                ),
            })

    write_csv(
        output / "scenario_matrix.csv",
        rows,
    )

    catalog_data = []

    for case in cases:
        catalog_data.append({
            key: (
                "NaN"
                if isinstance(value, float)
                and math.isnan(value)
                else value
            )
            for key, value in case.__dict__.items()
        })

    (output / "scenario_catalog.json").write_text(
        json.dumps(
            catalog_data,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    print(
        f"SCENARIO MATRIX: {len(cases)} checked, "
        f"{failures} failures"
    )

    return len(cases), failures


# ============================================================
# MULTI-INTERVAL CAMPAIGNS
# ============================================================

CAMPAIGNS = (
    "normal",
    "clouds",
    "heatwave",
    "cold_wind",
    "low_light",
    "grid_trip",
    "fault_recovery",
    "maintenance",
    "zero_target",
    "reactive_dispatch",
    "combined_events",
    "one_channel_soiling",
    "east_west_mppts",
)


def campaign_setup(name: str):

    if name == "one_channel_soiling":
        return pipeline_for(
            Case(
                name,
                "campaign",
                transmission=.35,
                channel=("INV_1", 1),
            )
        )

    if name == "east_west_mppts":

        pipeline = pipeline_for(
            Case(
                name,
                "campaign",
                azimuth_deg=90,
                channel=("INV_1", 1),
            )
        )

        config = pipeline.mppt_configs["INV_2"]

        pipeline.mppt_configs["INV_2"] = replace(
            config,
            channels=tuple(
                replace(
                    channel,
                    surface=replace(
                        channel.surface,
                        azimuth_deg=270,
                    ),
                )
                if channel.channel == 2
                else channel
                for channel in config.channels
            ),
        )

        return pipeline

    return build_integrated_demo_pipeline()


def interval_variant(name: str, idx: int, original):

    hour = idx / 4.0

    scale = 1.0
    ambient_delta = 0.0
    wind_delta = 0.0

    target = None
    q = 0.0

    grid = True
    stop = False

    faults = frozenset()
    locks = frozenset()

    if name == "clouds":

        scale = (
            .2 if 8 <= hour < 12
            else .65 if 12 <= hour < 15
            else 1.0
        )

    elif name == "heatwave":

        ambient_delta = 20
        wind_delta = -1.0

    elif name == "cold_wind":

        ambient_delta = -22
        wind_delta = 10

    elif name == "low_light":

        scale = .15

    elif name == "grid_trip":

        grid = not 9 <= hour < 10.5

    elif name == "fault_recovery":

        faults = (
            frozenset({"INV_1"})
            if 8 <= hour < 11
            else frozenset()
        )

    elif name == "maintenance":

        locks = (
            frozenset({"INV_2"})
            if 8 <= hour < 13
            else frozenset()
        )

    elif name == "zero_target":

        target = (
            0.0 if 10 <= hour < 12
            else 5.0
        )

    elif name == "reactive_dispatch":

        q = (
            8.0 if 8 <= hour < 15
            else 0.0
        )

    elif name == "combined_events":

        scale = (
            .3 if 8 <= hour < 9
            else .8
        )

        q = 8.0

        target = (
            5.0
            if hour >= 12
            else None
        )

        grid = not 9 <= hour < 9.5

        faults = (
            frozenset({"INV_1"})
            if 11 <= hour < 12
            else frozenset()
        )

        locks = (
            frozenset({"INV_2"})
            if 13 <= hour < 14
            else frozenset()
        )

        stop = 15 <= hour < 15.25

    sample = original.weather.irradiance

    new_weather = replace(
        original.weather,
        irradiance=replace(
            sample,
            ghi_w_m2=sample.ghi_w_m2 * scale,
            dni_w_m2=sample.dni_w_m2 * scale,
            dhi_w_m2=sample.dhi_w_m2 * scale,
        ),
        ambient_temperature_c=(
            original.weather.ambient_temperature_c
            + ambient_delta
        ),
        wind_speed_m_s=max(
            0.0,
            original.weather.wind_speed_m_s
            + wind_delta,
        ),
    )

    return replace(
        original,
        weather=new_weather,
        requested_target_kw=target,
        grid_available=grid,
        emergency_stop=stop,
        fault_inverter_ids=faults,
        maintenance_inverter_ids=locks,
    ), q


# ============================================================
# SAVE MULTIPLE CAMPAIGNS TO A SEPARATE SQLITE DATABASE
# ============================================================

def run_campaigns(
    output: Path,
    names: tuple[str, ...],
) -> int:

    db_file = output / "historian.sqlite3"

    historian = SolarHistorian(db_file)

    report_rows = []
    failed = 0

    for name in names:

        print(
            "  campaign:",
            name,
            flush=True,
        )

        try:

            pipeline = campaign_setup(name)

            simulator = SolarTimeSeriesSimulator(
                pipeline
            )

            ids = pipeline.inverter_ids

            capabilities = {
                iid: PQCapability(10.0, 10.0)
                for iid in ids
            }

            for index, interval in enumerate(
                make_stress_intervals(1)
            ):

                variant, q = interval_variant(
                    name,
                    index,
                    interval,
                )

                variant = replace(
                    variant,
                    pq_capabilities=capabilities,
                    reactive_requests_kvar={
                        iid: q
                        for iid in ids
                    },
                )

                result = simulator.step(variant)

                assert (
                    0
                    <= result.dispatched_power_kw
                    <= result.available_power_kw + 1e-5
                )

                assert math.isclose(
                    result.interval_energy_kwh,
                    result.dispatched_power_kw * .25,
                    abs_tol=1e-5,
                )

            assert len(simulator.records) == 96

            snapshots = build_integrated_snapshots(
                pipeline
            )

            run_id = historian.save_simulation(
                simulator,
                scenario=(
                    "GES_SCENARIO_"
                    + name.upper()
                ),
                inverter_snapshot_payloads=snapshots,
            )

            with sqlite3.connect(db_file) as db:

                interval_count = db.execute(
                    """
                    SELECT COUNT(*)
                    FROM production_intervals
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()[0]

                mppt_count = db.execute(
                    """
                    SELECT COUNT(*)
                    FROM ges_mppt_intervals
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()[0]

                pq_count = db.execute(
                    """
                    SELECT COUNT(*)
                    FROM ges_pq_intervals
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()[0]

                fk_issues = db.execute(
                    "PRAGMA foreign_key_check"
                ).fetchall()

            assert interval_count == 96
            assert mppt_count == 384
            assert pq_count == 192
            assert not fk_issues

            report_rows.append({
                "campaign": name,
                "status": "PASS",
                "run_id": run_id,
                "intervals": interval_count,
                "mppt_rows": mppt_count,
                "pq_rows": pq_count,
                "energy_kwh": round(
                    simulator.records[
                        -1
                    ].cumulative_energy_kwh,
                    6,
                ),
                "alarm_transitions": len(
                    simulator.alarm_history
                ),
                "details": "",
            })

        except Exception as exc:

            failed += 1

            report_rows.append({
                "campaign": name,
                "status": "FAIL",
                "run_id": "",
                "intervals": "",
                "mppt_rows": "",
                "pq_rows": "",
                "energy_kwh": "",
                "alarm_transitions": "",
                "details": (
                    f"{type(exc).__name__}: {exc}"
                ),
            })

    write_csv(
        output / "campaign_summary.csv",
        report_rows,
    )

    print(
        f"CAMPAIGNS: {len(names)} tested, "
        f"{failed} failures"
    )

    return failed


# ============================================================
# COMMAND LINE
# ============================================================

def main() -> None:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "outputs/ges_scenarios_v05"
        ),
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="2 campaigns instead of 13",
    )

    parser.add_argument(
        "--matrix-only",
        action="store_true",
    )

    args = parser.parse_args()

    args.output.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = load_weather_intervals_csv(
        "data/solar/demo_weather_15m.csv"
    )

    assert len(rows) >= 2

    weather = max(
        rows,
        key=lambda row: (
            row.weather.irradiance.ghi_w_m2
        ),
    ).weather

    assert weather.irradiance.ghi_w_m2 > 0

    case_count, failed_matrix = run_matrix(
        weather,
        args.output,
    )

    failed_campaigns = 0

    if not args.matrix_only:

        names = (
            CAMPAIGNS[:2]
            if args.quick
            else CAMPAIGNS
        )

        failed_campaigns = run_campaigns(
            args.output,
            names,
        )

    limitations = (
        "SIMULATION ONLY. NO OT COMMANDS.\n"
        "Optical transmission is an aggregate "
        "soiling/occlusion proxy.\n"
        "No physical partial-shadow I-V curves.\n"
        "P-Q reports requested Q, not measured Q.\n"
        "No OEM inverter efficiency or thermal "
        "derating calibration.\n"
        "No real protection relay or grid code model.\n"
        "Not covered: arc faults, ground faults, "
        "insulation faults, lightning,\n"
        "bypass diode hotspots, battery systems, "
        "cybersecurity or field certification.\n"
        "All test parameters are synthetic.\n"
    )

    (
        args.output / "model_limitations.txt"
    ).write_text(
        limitations,
        encoding="utf-8",
    )

    print()
    print("OUTPUT:", args.output.resolve())
    print("SCENARIOS:", case_count)

    if failed_matrix or failed_campaigns:
        raise SystemExit(
            "SCENARIO SUITE FAILED: "
            f"{failed_matrix} snapshot + "
            f"{failed_campaigns} campaigns"
        )

    print("GES SCENARIO SUITE OK")


if __name__ == "__main__":
    main()

