
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from pathlib import Path

from simulator.solar.solar_resource import IrradianceSample
from simulator.solar.solar_pipeline import SolarWeather


# CSV dosyasında zorunlu olacak alanlar.
REQUIRED_COLUMNS = {
    "start_utc",
    "end_utc",
    "ghi_w_m2",
    "dni_w_m2",
    "dhi_w_m2",
    "ambient_temperature_c",
    "wind_speed_m_s",
    "source_type",
    "quality_status",
}

ALLOWED_SOURCES = {
    "SYNTHETIC",
    "MEASURED",
    "SATELLITE",
    "REANALYSIS",
    "FORECAST",
}

INTERVAL = timedelta(minutes=15)


@dataclass(frozen=True)
class SolarWeatherInterval:
    start_utc: datetime
    end_utc: datetime
    weather: SolarWeather
    source_type: str
    quality_status: str


def _parse_utc(value: str, field: str, line: int) -> datetime:
    if not value or not value.strip():
        raise ValueError(
            f"Line {line}: missing {field}"
        )

    try:
        timestamp = datetime.fromisoformat(
            value.strip().replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError(
            f"Line {line}: invalid {field}"
        ) from exc

    if (
        timestamp.tzinfo is None
        or timestamp.utcoffset() != timedelta(0)
    ):
        raise ValueError(
            f"Line {line}: {field} must be UTC"
        )

    return timestamp.astimezone(timezone.utc)


def _number(
    row: dict,
    field: str,
    line: int,
    *,
    nonnegative: bool = False,
) -> float:

    raw = row.get(field)

    if raw is None or not raw.strip():
        raise ValueError(
            f"Line {line}: missing {field}"
        )

    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(
            f"Line {line}: invalid number in {field}"
        ) from exc

    if not isfinite(value):
        raise ValueError(
            f"Line {line}: {field} must be finite"
        )

    if nonnegative and value < 0:
        raise ValueError(
            f"Line {line}: {field} cannot be negative"
        )

    return value


def load_weather_intervals_csv(
    filename: str | Path,
) -> list[SolarWeatherInterval]:
    """
    15 dakikalik GES meteorolojik veri dosyasini okur.

    Girdi:
        Her satir 15 dakikalik aralik ortalamasidir.

    Zaman:
        start_utc / end_utc UTC olmalidir.

    Dondurulen kayitlar:
        SolarTimeSeriesSimulator ile kullanilabilir.

    Guvenlik:
        Bilinmeyen, eksik veya kalitesiz veri
        sessizce doldurulmaz.
    """

    records: list[SolarWeatherInterval] = []

    with Path(filename).open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:

        reader = csv.DictReader(file)

        if reader.fieldnames is None:
            raise ValueError(
                "CSV has no header"
            )

        missing = (
            REQUIRED_COLUMNS
            - set(reader.fieldnames)
        )

        if missing:
            raise ValueError(
                f"Missing CSV columns: {sorted(missing)}"
            )

        for line_number, row in enumerate(
            reader,
            start=2,
        ):

            if None in row:
                raise ValueError(
                    f"Line {line_number}: extra CSV fields"
                )

            start = _parse_utc(
                row.get("start_utc"),
                "start_utc",
                line_number,
            )

            end = _parse_utc(
                row.get("end_utc"),
                "end_utc",
                line_number,
            )

            # Every interval must be 15 minutes.
            if end - start != INTERVAL:
                raise ValueError(
                    f"Line {line_number}: "
                    "interval must be 15 minutes"
                )

            if (
                start.minute % 15 != 0
                or start.second != 0
                or start.microsecond != 0
            ):
                raise ValueError(
                    f"Line {line_number}: "
                    "invalid interval boundary"
                )

            # Do not silently fill missing time.
            if records and start != records[-1].end_utc:
                raise ValueError(
                    f"Line {line_number}: "
                    "time gap, overlap or duplicate"
                )

            source = (
                row["source_type"]
                or ""
            ).strip().upper()

            if source not in ALLOWED_SOURCES:
                raise ValueError(
                    f"Line {line_number}: "
                    "unknown source_type"
                )

            quality = (
                row["quality_status"]
                or ""
            ).strip().upper()

            if quality != "VALID":
                raise ValueError(
                    f"Line {line_number}: "
                    "weather data quality is not VALID"
                )

            ghi = _number(
                row, "ghi_w_m2", line_number,
                nonnegative=True,
            )

            dni = _number(
                row, "dni_w_m2", line_number,
                nonnegative=True,
            )

            dhi = _number(
                row, "dhi_w_m2", line_number,
                nonnegative=True,
            )

            ambient = _number(
                row,
                "ambient_temperature_c",
                line_number,
            )

            if ambient <= -273.15:
                raise ValueError(
                    f"Line {line_number}: "
                    "temperature below absolute zero"
                )

            wind = _number(
                row,
                "wind_speed_m_s",
                line_number,
                nonnegative=True,
            )

            weather = SolarWeather(
                irradiance=IrradianceSample(
                    # Timestamp represents interval end.
                    timestamp=end,
                    ghi_w_m2=ghi,
                    dni_w_m2=dni,
                    dhi_w_m2=dhi,
                    source_type=source,
                ),
                ambient_temperature_c=ambient,
                wind_speed_m_s=wind,
            )

            records.append(
                SolarWeatherInterval(
                    start_utc=start,
                    end_utc=end,
                    weather=weather,
                    source_type=source,
                    quality_status=quality,
                )
            )

    if not records:
        raise ValueError(
            "CSV contains no weather records"
        )

    return records
