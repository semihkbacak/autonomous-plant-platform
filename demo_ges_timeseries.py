from __future__ import annotations
from simulator.solar.historian import SolarHistorian
import argparse
import csv
from pathlib import Path
from simulator.solar.inverter_snapshot_payloads import (
    build_demo_inverter_snapshot_payloads,
)

from simulator.solar.solar_resource import (
    PVSurface,
    SolarSite,
)

from simulator.solar.pv_array import (
    PVArrayConfiguration,
    synthetic_demo_module,
)

from simulator.solar.inverter import InverterConfig

from simulator.solar.solar_pipeline import (
    SolarAsset,
    SolarPhysicsPipeline,
)

from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


# ============================================================
# DEMO GES CONFIGURATION
# ============================================================

def build_demo_pipeline() -> SolarPhysicsPipeline:
    """
    Creates a synthetic two-inverter solar plant.
    No real equipment is connected.
    """

    module = synthetic_demo_module()

    assets = []

    for inverter_id in ("INV_1", "INV_2"):

        inverter = InverterConfig(
            inverter_id=inverter_id,
            rated_ac_kw=10.0,
            nominal_efficiency=0.96,
            mppt_min_v=200.0,
            mppt_max_v=800.0,
            max_dc_voltage_v=1000.0,
            max_dc_current_a=30.0,
        )

        array = PVArrayConfiguration(
            modules_per_string=10,
            parallel_strings=2,
            module=module,
        )

        assets.append(
            SolarAsset(
                inverter=inverter,
                array=array,
                surface=PVSurface(
                    tilt_deg=30.0,
                    azimuth_deg=180.0,
                ),
            )
        )

    site = SolarSite(
        latitude_deg=39.93,
        longitude_deg=32.86,
    )

    return SolarPhysicsPipeline(
        site=site,
        assets=assets,
    )


# ============================================================
# RUN COMPLETE SOLAR SIMULATION
# ============================================================

def run_demo(
    weather_file: str | Path,
    output_directory: str | Path,
    grid_loss_interval_index: int | None = None,
) -> SolarTimeSeriesSimulator:

    weather_rows = load_weather_intervals_csv(
        weather_file
    )


    if grid_loss_interval_index is not None:
        if not (
            0 <= grid_loss_interval_index < len(weather_rows)
        ):
            raise ValueError(
                "Grid loss interval index is out of range"
            )

    # Build the pipeline for EVERY scenario.
    pipeline = build_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )


    print()
    print("AUTONOMOUS PLANT PLATFORM - GES DEMO")
    print("SYNTHETIC DATA ONLY")
    print("-" * 62)

    for index, row in enumerate(weather_rows):

        # Normal operation except the selected
        # simulated grid-loss interval.
        grid_available = (
            index != grid_loss_interval_index
        )

        interval = SolarIntervalInput(
            start_utc=row.start_utc,
            end_utc=row.end_utc,
            weather=row.weather,
            requested_target_kw=None,
            grid_available=grid_available,
            emergency_stop=False,
        )

        result = simulator.step(interval)

        print(
            f"{result.start_utc.strftime('%H:%M')}"
            " - "
            f"{result.end_utc.strftime('%H:%M')}"
            " UTC"
        )

        print(
            "  Available AC : "
            f"{result.available_power_kw:.3f} kW"
        )

        print(
            "  Dispatched AC: "
            f"{result.dispatched_power_kw:.3f} kW"
        )

        print(
            "  Interval     : "
            f"{result.interval_energy_kwh:.3f} kWh"
        )

        print(
            "  Cumulative   : "
            f"{result.cumulative_energy_kwh:.3f} kWh"
        )

        print(
            "  Active alarms: "
            f"{result.active_alarms}"
        )

        print("-" * 62)

    # ========================================================
    # EXPORT REPORTS
    # ========================================================

    output_directory = Path(output_directory)

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    file_15m = (
        output_directory / "production_15m.csv"
    )

    file_hourly = (
        output_directory / "production_hourly.csv"
    )

    file_alarms = (
        output_directory / "alarm_history.csv"
    )

    simulator.export_15m_csv(file_15m)

    simulator.export_hourly_csv(file_hourly)

    with file_alarms.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as file:

        writer = csv.writer(file)

        writer.writerow((
            "detected_at_utc",
            "code",
            "inverter_id",
            "transition",
        ))

        for event in simulator.alarm_history:
            writer.writerow((
                event.timestamp_utc.isoformat(),
                event.code,
                event.inverter_id or "",
                event.transition,
            ))

    print()

    print("SIMULATION COMPLETE")


    # Save completed GES simulation to SQLite.
    historian = SolarHistorian(
        output_directory / "historian.sqlite3"
    )

    scenario = (
        "GRID_LOSS"
        if grid_loss_interval_index is not None
        else "NORMAL"
    )

    run_id = historian.save_simulation(
        simulator,
        scenario=scenario,
        inverter_snapshot_payloads=(
            build_demo_inverter_snapshot_payloads(
                pipeline
            )
        ),
    )

    print(f"Historian run ID: {run_id}")


    if simulator.records:
        total_energy = (
            simulator.records[-1].cumulative_energy_kwh
        )
    else:
        total_energy = 0.0

    print(
        f"Total simulated energy: "
        f"{total_energy:.3f} kWh"
    )

    print(
        f"Alarm transitions: "
        f"{len(simulator.alarm_history)}"
    )

    print(f"Reports: {output_directory.resolve()}")

    print(
        "NOTICE: No real PLC, SCADA or OT "
        "equipment was contacted."
    )

    return simulator
    # Save the completed simulation to SQLite.
    historian = SolarHistorian(
        output_directory / "historian.sqlite3"
    )

    scenario = (
        "GRID_LOSS"
        if grid_loss_interval_index is not None
        else "NORMAL"
    )

    run_id = historian.save_simulation(
        simulator,
        scenario=scenario,
    )

    print(f"Historian run ID: {run_id}")

    # Persist simulation results in SQLite.
    historian = SolarHistorian(
        output_directory / "historian.sqlite3"
    )

    scenario = (
        "GRID_LOSS"
        if grid_loss_interval_index is not None
        else "NORMAL"
    )

    run_id = historian.save_simulation(
        simulator,
        scenario=scenario,
    )

    print(f"Historian run ID: {run_id}")
# ============================================================
# COMMAND LINE
# ============================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Synthetic GES time-series demo"
    )

    parser.add_argument(
        "--weather",
        default="data/solar/demo_weather_15m.csv",
    )

    parser.add_argument(
        "--out",
        default="outputs/ges_normal",
    )

    parser.add_argument(
        "--grid-loss-interval",
        type=int,
        default=None,
        help="Zero-based interval index",
    )

    args = parser.parse_args()

    run_demo(
        weather_file=args.weather,
        output_directory=args.out,
        grid_loss_interval_index=args.grid_loss_interval,
    )
