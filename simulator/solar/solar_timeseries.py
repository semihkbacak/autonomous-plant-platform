
from __future__ import annotations
from typing import Mapping

from simulator.solar.pq_dispatch import (
    PQCapability,
)
import csv
from simulator.solar.inverter import InverterResult
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

from simulator.solar.solar_pipeline import (
    SolarPhysicsPipeline,
    SolarWeather,
)


INTERVAL = timedelta(minutes=15)


@dataclass(frozen=True)
class SolarIntervalInput:
    start_utc: datetime
    end_utc: datetime
    weather: SolarWeather

    requested_target_kw: float | None = None
    grid_available: bool = True
    emergency_stop: bool = False

    fault_inverter_ids: frozenset[str] = frozenset()
    maintenance_inverter_ids: frozenset[str] = frozenset()
    pq_capabilities: Mapping[str, PQCapability] | None = None

    reactive_requests_kvar: Mapping[str, float] | None = None


@dataclass(frozen=True)
class SolarAlarmTransition:
    timestamp_utc: datetime
    code: str
    inverter_id: str | None
    transition: str


@dataclass(frozen=True)
class SolarIntervalResult:
    start_utc: datetime
    end_utc: datetime

    available_power_kw: float
    dispatched_power_kw: float

    interval_energy_kwh: float
    cumulative_energy_kwh: float

    curtailed_power_kw: float
    unserved_target_kw: float

    reasons: tuple[str, ...]
    quality_flags: tuple[str, ...]
    source_types: tuple[str, ...]
    active_alarms: tuple[str, ...]
    inverter_results: tuple[InverterResult, ...] = ()
    mppt_reports: tuple = ()  # per-channel MPPT results
    pq_reports: tuple = ()  # Q requests, not measured output


class SolarTimeSeriesSimulator:
    """
    15 dakikalik GES zaman serisi simulatoru.

    Meteorolojik veriler ilgili zaman
    araliginin ortalamasini temsil eder.

    Gercek PLC/SCADA baglantisi yoktur.
    """

    def __init__(
        self,
        pipeline: SolarPhysicsPipeline,
    ) -> None:

        self.pipeline = pipeline

        self.records: list[
            SolarIntervalResult
        ] = []

        self.alarm_history: list[
            SolarAlarmTransition
        ] = []

        self._active: set[
            tuple[str, str | None]
        ] = set()

    @staticmethod
    def _utc(
        value: datetime,
        name: str,
    ) -> datetime:

        if (
            value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(
                f"{name} must be timezone-aware UTC"
            )

        if value.utcoffset() != timedelta(0):
            raise ValueError(
                f"{name} must use UTC offset +00:00"
            )

        return value.astimezone(timezone.utc)

    @staticmethod
    def _detect_alarms(
        plant,
    ) -> set[tuple[str, str | None]]:

        active: set[
            tuple[str, str | None]
        ] = set()

        if not plant.grid_available:
            active.add(
                ("GRID_UNAVAILABLE", None)
            )

        if plant.emergency_stop:
            active.add(
                ("PLANT_EMERGENCY_STOP", None)
            )

        for inverter in plant.inverter_results:

            for code in inverter.reasons:

                if code in {
                    "INVERTER_FAULT",
                    "DC_OVERVOLTAGE",
                    "INVALID_DC_VOLTAGE",
                }:
                    active.add(
                        (code, inverter.inverter_id)
                    )

        return active

    @staticmethod
    def _alarm_label(
        alarm: tuple[str, str | None],
    ) -> str:

        code, inverter_id = alarm

        if inverter_id is None:
            return code

        return f"{code}:{inverter_id}"

    def step(
        self,
        item: SolarIntervalInput,
    ) -> SolarIntervalResult:

        # 1. TIME VALIDATION

        start = self._utc(
            item.start_utc,
            "start_utc",
        )

        end = self._utc(
            item.end_utc,
            "end_utc",
        )

        timestamp = self._utc(
            item.weather.irradiance.timestamp,
            "weather.timestamp",
        )

        if end - start != INTERVAL:
            raise ValueError(
                "Each interval must be exactly 15 minutes"
            )

        if (
            start.minute % 15 != 0
            or start.second != 0
            or start.microsecond != 0
        ):
            raise ValueError(
                "Interval must start on a "
                "15-minute UTC boundary"
            )

        if timestamp != end:
            raise ValueError(
                "Weather timestamp must equal interval end"
            )

        if self.records:

            previous_end = self.records[-1].end_utc

            if start != previous_end:
                raise ValueError(
                    "Intervals must be consecutive "
                    "and non-overlapping"
                )

        # 2. IRRADIANCE VALIDATION

        for name in (
            "ghi_w_m2",
            "dni_w_m2",
            "dhi_w_m2",
        ):

            value = getattr(
                item.weather.irradiance,
                name,
            )

            if (
                not isfinite(value)
                or value < 0
            ):
                raise ValueError(
                    f"Invalid irradiance: {name}"
                )

        # 3. SOLAR POSITION AT MIDPOINT

        midpoint = start + INTERVAL / 2

        weather_at_midpoint = replace(
            item.weather,
            irradiance=replace(
                item.weather.irradiance,
                timestamp=midpoint,
            ),
        )

        # 4. RUN COMPLETE SOLAR PHYSICS
        pq_kwargs = {}

        if (
            item.pq_capabilities is not None
            or item.reactive_requests_kvar is not None
        ):
            pq_kwargs = {
                "pq_capabilities": item.pq_capabilities,
                "reactive_requests_kvar": (
                    item.reactive_requests_kvar
                ),
            }
        response = self.pipeline.simulate(
            weather=weather_at_midpoint,

            requested_target_kw=(
                item.requested_target_kw
            ),

            grid_available=item.grid_available,

            emergency_stop=item.emergency_stop,

            fault_inverter_ids=(
                item.fault_inverter_ids
            ),

            maintenance_inverter_ids=(
                item.maintenance_inverter_ids
            ),
            **pq_kwargs,
        )

        plant = response.plant

        power_kw = plant.dispatched_power_kw

        if (
            not isfinite(power_kw)
            or power_kw < 0
        ):
            raise ValueError(
                "Pipeline returned invalid power"
            )

        # 5. ENERGY CALCULATION

        interval_energy_kwh = power_kw * 0.25

        previous_energy = (
            self.records[-1].cumulative_energy_kwh
            if self.records
            else 0.0
        )

        cumulative_energy_kwh = (
            previous_energy + interval_energy_kwh
        )

        # 6. ALARM STATE CHANGES

        active = self._detect_alarms(
            plant
        )

        raised = active - self._active
        cleared = self._active - active

        changes = []

        for code, inverter_id in sorted(raised):

            changes.append(
                SolarAlarmTransition(
                    timestamp_utc=end,
                    code=code,
                    inverter_id=inverter_id,
                    transition="RAISED",
                )
            )

        for code, inverter_id in sorted(cleared):

            changes.append(
                SolarAlarmTransition(
                    timestamp_utc=end,
                    code=code,
                    inverter_id=inverter_id,
                    transition="CLEARED",
                )
            )

        # 7. DATA QUALITY

        quality_flags = tuple(
            sorted({
                flag
                for array in response.array_reports
                for flag in array.poa.quality_flags
            })
        )

        source_types = tuple(
            sorted({
                array.poa.source_type
                for array in response.array_reports
            })
        )

        active_alarms = tuple(
            sorted(
                self._alarm_label(alarm)
                for alarm in active
            )
        )

        # 8. CREATE INTERVAL RESULT

        result = SolarIntervalResult(
            start_utc=start,
            end_utc=end,

            available_power_kw=(
                plant.available_power_kw
            ),

            dispatched_power_kw=power_kw,

            interval_energy_kwh=interval_energy_kwh,

            cumulative_energy_kwh=cumulative_energy_kwh,

            curtailed_power_kw=(
                plant.curtailed_power_kw
            ),

            unserved_target_kw=(
                plant.unserved_target_kw
            ),

            reasons=tuple(plant.reasons),

            quality_flags=quality_flags,
            source_types=source_types,
            active_alarms=active_alarms,
            inverter_results=tuple(
                plant.inverter_results
            ),
            mppt_reports=tuple(getattr(response, 'mppt_reports', ())),
            pq_reports=tuple(getattr(response, 'pq_reports', ())),
        )

        # Only commit internal state after success.

        self.records.append(result)

        self.alarm_history.extend(
            changes
        )

        self._active = active

        return result

    def export_15m_csv(
        self,
        destination: str | Path,
    ) -> None:

        fields = (
            "start_utc",
            "end_utc",
            "available_power_kw",
            "dispatched_power_kw",
            "interval_energy_kwh",
            "cumulative_energy_kwh",
            "curtailed_power_kw",
            "unserved_target_kw",
            "reasons",
            "quality_flags",
            "source_types",
            "active_alarms",
        )

        with Path(destination).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=fields,
            )

            writer.writeheader()

            for record in self.records:

                writer.writerow({
                    "start_utc": (
                        record.start_utc.isoformat()
                    ),

                    "end_utc": (
                        record.end_utc.isoformat()
                    ),

                    "available_power_kw": (
                        record.available_power_kw
                    ),

                    "dispatched_power_kw": (
                        record.dispatched_power_kw
                    ),

                    "interval_energy_kwh": (
                        record.interval_energy_kwh
                    ),

                    "cumulative_energy_kwh": (
                        record.cumulative_energy_kwh
                    ),

                    "curtailed_power_kw": (
                        record.curtailed_power_kw
                    ),

                    "unserved_target_kw": (
                        record.unserved_target_kw
                    ),

                    "reasons": ";".join(
                        record.reasons
                    ),

                    "quality_flags": ";".join(
                        record.quality_flags
                    ),

                    "source_types": ";".join(
                        record.source_types
                    ),

                    "active_alarms": ";".join(
                        record.active_alarms
                    ),
                })

    def export_hourly_csv(
        self,
        destination: str | Path,
    ) -> None:

        hours: dict[
            datetime,
            list[SolarIntervalResult],
        ] = {}

        for record in self.records:

            hour = record.start_utc.replace(
                minute=0,
                second=0,
                microsecond=0,
            )

            hours.setdefault(
                hour, []
            ).append(record)

        with Path(destination).open(
            "w",
            encoding="utf-8",
            newline="",
        ) as file:

            writer = csv.writer(file)

            writer.writerow((
                "hour_start_utc",
                "interval_count",
                "coverage_minutes",
                "energy_kwh",
                "mean_power_kw",
            ))

            for hour, records in sorted(
                hours.items()
            ):

                energy_kwh = sum(
                    record.interval_energy_kwh
                    for record in records
                )

                count = len(records)

                mean_power_kw = (
                    energy_kwh / (0.25 * count)
                )

                writer.writerow((
                    hour.isoformat(),
                    count,
                    15 * count,
                    energy_kwh,
                    mean_power_kw,
                ))
