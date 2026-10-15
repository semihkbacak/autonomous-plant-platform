
"""GES v0.4 integrated MPPT/AC/P-Q/SQLite demo."""
from __future__ import annotations

import sqlite3

from dataclasses import asdict
from pathlib import Path

from demo_ges_timeseries import build_demo_pipeline

from simulator.solar.ges_integrated import (
    IntegratedSolarPhysicsPipeline,
    InverterMPPTConfig,
)

from simulator.solar.historian import SolarHistorian

from simulator.solar.inverter_snapshot_payloads import (
    build_demo_inverter_snapshot_payloads,
)

from simulator.solar.multi_mppt_physics import (
    MPPTArray,
    MPPTLimits,
)

from simulator.solar.pq_dispatch import PQCapability

from simulator.solar.pv_array import (
    PVArrayConfiguration,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


def build_integrated_demo_pipeline() -> IntegratedSolarPhysicsPipeline:

    baseline = build_demo_pipeline()

    configs = {}

    for asset in baseline.assets:

        # Original 2 parallel strings are now represented
        # as 1 string on each of 2 independent MPPT channels.
        one_string = PVArrayConfiguration(
            modules_per_string=(
                asset.array.modules_per_string
            ),
            parallel_strings=1,
            module=asset.array.module,
            optical_transmission_factor=(
                asset.array.optical_transmission_factor
            ),
        )

        configs[asset.inverter.inverter_id] = (
            InverterMPPTConfig(
                channels=(
                    MPPTArray(
                        1,
                        one_string,
                        asset.surface,
                    ),
                    MPPTArray(
                        2,
                        one_string,
                        asset.surface,
                    ),
                ),
                limits=MPPTLimits(
                    mppt_count=2,
                    min_v=200,
                    max_v=800,
                    max_dc_v=1000,
                    max_operating_a=30,
                    max_short_circuit_a=40,
                    max_strings=1,
                ),
            )
        )

    return IntegratedSolarPhysicsPipeline(
        baseline.site,
        baseline.assets,
        configs,
    )


def build_integrated_snapshots(pipeline):

    snapshots = build_demo_inverter_snapshot_payloads(
        pipeline
    )

    for iid, mppt_config in pipeline.mppt_configs.items():

        payload = snapshots[iid]

        payload["model_id"] = (
            "APP_SYNTHETIC_GES_V04_MULTI_MPPT"
        )

        values = payload["values"]

        for channel in mppt_config.channels:

            fields = {
                "array": asdict(channel.array),
                "surface": asdict(channel.surface),
                "temperature": asdict(
                    channel.temperature_params
                ),
            }

            for name, value in fields.items():

                values[
                    f"mppt.{channel.channel}.{name}"
                ] = {
                    "value": value,
                    "source_id": "APP_SYNTHETIC_GES_V04",
                    "source_url": (
                        "project://demo_ges_integrated_v04.py"
                    ),
                    "evidence": (
                        "Synthetic MPPT assignment; "
                        "not OEM-verified"
                    ),
                }

        values["mppt_limits"] = {
            "value": asdict(mppt_config.limits),
            "source_id": "APP_SYNTHETIC_GES_V04",
            "source_url": (
                "project://demo_ges_integrated_v04.py"
            ),
            "evidence": (
                "Synthetic channel limits; "
                "not OEM-verified"
            ),
        }

    return snapshots


def main() -> None:

    root = Path(__file__).resolve().parent

    weather_rows = load_weather_intervals_csv(
        root / "data/solar/demo_weather_15m.csv"
    )

    pipeline = build_integrated_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    # Synthetic P-Q capacity inputs.
    pq = {
        iid: PQCapability(10.0, 10.0)
        for iid in pipeline.inverter_ids
    }

    q = {
        iid: 8.0
        for iid in pipeline.inverter_ids
    }

    for index, row in enumerate(weather_rows):

        result = simulator.step(
            SolarIntervalInput(
                start_utc=row.start_utc,
                end_utc=row.end_utc,
                weather=row.weather,

                # Third interval is simulated grid loss.
                grid_available=(index != 2),

                pq_capabilities=pq,
                reactive_requests_kvar=q,
            )
        )

        channel_count = sum(
            len(report.dc.channels)
            for report in result.mppt_reports
        )

        print(
            row.start_utc.isoformat(),
            "AC dispatched kW:",
            round(
                result.dispatched_power_kw,
                4,
            ),
            "MPPT channels:",
            channel_count,
        )

    output = (
        root / "outputs/ges_v04_integrated_demo"
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_path = output / "historian.sqlite3"

    historian = SolarHistorian(db_path)

    run_id = historian.save_simulation(
        simulator,
        scenario="GES_V04_SYNTHETIC_PQ_GRIDLOSS",
        inverter_snapshot_payloads=(
            build_integrated_snapshots(pipeline)
        ),
    )

    with sqlite3.connect(db_path) as db:

        count = db.execute(
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

        foreign_key_errors = db.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()

    expected = len(simulator.records) * 4

    assert count == expected, (count, expected)

    assert pq_count == len(simulator.records) * 2

    assert not foreign_key_errors, foreign_key_errors

    print(
        "GES V0.4 MPPT HISTORIAN OK",
        "run_id:",
        run_id,
        "channels:",
        count,
        "P-Q screens:",
        pq_count,
        "DB:",
        db_path,
    )


if __name__ == "__main__":
    main()
