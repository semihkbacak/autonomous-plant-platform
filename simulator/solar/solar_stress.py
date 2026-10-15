
from __future__ import annotations

import argparse
import json

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from math import cos, radians, sin
from pathlib import Path

import pandas as pd
import pvlib

from simulator.solar.solar_pipeline import SolarWeather
from simulator.solar.solar_resource import IrradianceSample
from simulator.solar.solar_timeseries import (
    SolarIntervalInput,
    SolarTimeSeriesSimulator,
)


START = datetime(
    2026, 6, 21,
    tzinfo=timezone.utc,
)

STEP = timedelta(minutes=15)


def make_stress_intervals(
    days: int,
    *,
    start_utc: datetime = START,
    latitude_deg: float = 39.93,
    longitude_deg: float = 32.86,
) -> list[SolarIntervalInput]:
    """
    Generate deterministic synthetic GES weather and
    disturbance inputs.

    These are NOT observed meteorological measurements.
    """

    if type(days) is not int or not (1 <= days <= 365):
        raise ValueError(
            "days must be an integer from 1 to 365"
        )

    if (
        not isinstance(start_utc, datetime)
        or start_utc.tzinfo is None
        or start_utc.utcoffset() != timedelta(0)
        or any((
            start_utc.hour,
            start_utc.minute,
            start_utc.second,
            start_utc.microsecond,
        ))
    ):
        raise ValueError(
            "start_utc must be midnight UTC"
        )

    count = 96 * days

    times = pd.date_range(
        start=start_utc,
        periods=count,
        freq="15min",
    )

    midpoint = times + pd.Timedelta(
        minutes=7,
        seconds=30,
    )

    positions = pvlib.solarposition.get_solarposition(
        midpoint,
        latitude=latitude_deg,
        longitude=longitude_deg,
    )

    intervals = []

    for index, stamp in enumerate(times):

        start = stamp.to_pydatetime()
        end = start + STEP

        zenith = float(
            positions["apparent_zenith"].iloc[index]
        )

        sun_height = max(
            0.0,
            cos(radians(zenith)),
        )

        # Deterministic synthetic cloud variation.
        cloud = (
            0.75
            + 0.18 * sin(index * 0.19)
            + 0.05 * cos(index * 0.043)
        )

        if sun_height < 0.02:
            dni = 0.0
            dhi = 0.0
            ghi = 0.0
        else:
            dni = 800.0 * sun_height * cloud

            dhi = (
                110.0
                * sun_height
                * (1.25 - cloud)
            )

            # Consistent horizontal irradiance.
            ghi = dni * sun_height + dhi

        day, slot = divmod(index, 96)

        # Day 1 contains controlled disturbances.
        grid_available = not (
            day == 0
            and slot in (40, 41)
        )

        fault_ids = (
            frozenset({"INV_2"})
            if day == 0 and slot in (48, 49)
            else frozenset()
        )

        emergency_stop = (
            day == 0 and slot == 56
        )

        maintenance_ids = (
            frozenset({"INV_1"})
            if day == 0 and slot in (64, 65)
            else frozenset()
        )

        target = (
            5.0
            if day == 0 and slot in (44, 45)
            else None
        )

        intervals.append(
            SolarIntervalInput(
                start_utc=start,
                end_utc=end,

                weather=SolarWeather(
                    irradiance=IrradianceSample(
                        timestamp=end,
                        ghi_w_m2=ghi,
                        dni_w_m2=dni,
                        dhi_w_m2=dhi,
                        source_type="SYNTHETIC",
                    ),

                    ambient_temperature_c=(
                        19.0 + 12.0 * sun_height
                    ),

                    wind_speed_m_s=(
                        1.7
                        + 0.6
                        * (1 + sin(index * 0.05))
                    ),
                ),

                grid_available=grid_available,
                fault_inverter_ids=fault_ids,
                emergency_stop=emergency_stop,
                maintenance_inverter_ids=maintenance_ids,
                requested_target_kw=target,
            )
        )

    return intervals


def main() -> None:

    parser = argparse.ArgumentParser(
        description="Synthetic GES stress test"
    )

    parser.add_argument(
        "--days",
        type=int,
        default=7,
    )

    parser.add_argument(
        "--output",
        default="outputs/ges_stress_7d",
        help="Directory for a new test database",
    )

    args = parser.parse_args()

    from demo_ges_timeseries import (
        build_demo_pipeline,
    )

    from simulator.solar.historian import (
        SolarHistorian,
    )

    from simulator.solar.inverter_snapshot_payloads import (
        build_demo_inverter_snapshot_payloads,
    )

    from simulator.solar.solar_historian_audit import (
        audit_solar_run,
    )

    output = Path(args.output)
    db_file = output / "historian.sqlite3"

    # Do not overwrite an existing database.
    if db_file.exists():
        parser.error(
            f"Database already exists: {db_file}. "
            "Choose a new --output directory."
        )

    pipeline = build_demo_pipeline()

    simulator = SolarTimeSeriesSimulator(
        pipeline
    )

    inputs = make_stress_intervals(
        args.days,
        latitude_deg=pipeline.site.latitude_deg,
        longitude_deg=pipeline.site.longitude_deg,
    )

    print(
        f"Starting {args.days}-day synthetic GES test"
    )

    for index, item in enumerate(inputs, start=1):

        simulator.step(item)

        if index % 96 == 0:
            print(
                f"Completed day {index // 96}"
            )

    historian = SolarHistorian(
        db_file
    )

    run_id = historian.save_simulation(
        simulator,

        scenario=(
            f"SYNTHETIC_STRESS_{args.days}D"
        ),

        inverter_snapshot_payloads=(
            build_demo_inverter_snapshot_payloads(
                pipeline
            )
        ),
    )

    result = audit_solar_run(
        db_file,
        run_id,
        expected_inverter_ids=(
            "INV_1",
            "INV_2",
        ),
    )

    print(
        json.dumps(
            asdict(result),
            indent=2,
            ensure_ascii=False,
        )
    )

    if not result.ok:
        raise SystemExit(
            "STRESS AUDIT FAILED"
        )

    print(
        f"STRESS AUDIT OK | DB: {db_file}"
    )


if __name__ == "__main__":
    main()
