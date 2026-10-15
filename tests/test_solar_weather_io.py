
import pytest

from simulator.solar.weather_io import (
    load_weather_intervals_csv,
)


HEADER = (
    "start_utc,end_utc,"
    "ghi_w_m2,dni_w_m2,dhi_w_m2,"
    "ambient_temperature_c,wind_speed_m_s,"
    "source_type,quality_status"
)

ROW_1 = (
    "2026-06-21T10:00:00Z,"
    "2026-06-21T10:15:00Z,"
    "800,700,150,25,2,SYNTHETIC,VALID"
)

ROW_2 = (
    "2026-06-21T10:15:00Z,"
    "2026-06-21T10:30:00Z,"
    "850,740,160,26,2.5,SYNTHETIC,VALID"
)


def write_csv(tmp_path, *rows, header=HEADER):
    path = tmp_path / "weather.csv"
    path.write_text(
        header + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_valid_weather_csv(tmp_path):
    path = write_csv(tmp_path, ROW_1, ROW_2)
    data = load_weather_intervals_csv(path)

    assert len(data) == 2
    assert data[0].weather.irradiance.ghi_w_m2 == 800
    assert data[0].source_type == "SYNTHETIC"


def test_timestamp_is_interval_end(tmp_path):
    data = load_weather_intervals_csv(
        write_csv(tmp_path, ROW_1)
    )

    assert (
        data[0].weather.irradiance.timestamp
        == data[0].end_utc
    )


def test_time_gap_rejected(tmp_path):
    late_row = ROW_2.replace(
        "10:15:00Z,2026-06-21T10:30:00Z",
        "10:30:00Z,2026-06-21T10:45:00Z",
    )

    path = write_csv(
        tmp_path, ROW_1, late_row
    )

    with pytest.raises(ValueError):
        load_weather_intervals_csv(path)


def test_duplicate_interval_rejected(tmp_path):
    path = write_csv(
        tmp_path, ROW_1, ROW_1
    )

    with pytest.raises(ValueError):
        load_weather_intervals_csv(path)


def test_negative_irradiance_rejected(tmp_path):
    invalid = ROW_1.replace(
        "800,700,150",
        "-5,700,150",
    )

    with pytest.raises(ValueError):
        load_weather_intervals_csv(
            write_csv(tmp_path, invalid)
        )


def test_nan_irradiance_rejected(tmp_path):
    invalid = ROW_1.replace(
        "800,700,150",
        "nan,700,150",
    )

    with pytest.raises(ValueError):
        load_weather_intervals_csv(
            write_csv(tmp_path, invalid)
        )


def test_suspect_quality_rejected(tmp_path):
    invalid = ROW_1.replace(
        "SYNTHETIC,VALID",
        "SYNTHETIC,SUSPECT",
    )

    with pytest.raises(ValueError):
        load_weather_intervals_csv(
            write_csv(tmp_path, invalid)
        )


def test_non_utc_timestamp_rejected(tmp_path):
    invalid = ROW_1.replace(
        "2026-06-21T10:00:00Z",
        "2026-06-21T10:00:00+03:00",
    )

    with pytest.raises(ValueError):
        load_weather_intervals_csv(
            write_csv(tmp_path, invalid)
        )


def test_missing_column_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_weather_intervals_csv(
            write_csv(
                tmp_path,
                ROW_1,
                header="start_utc,end_utc",
            )
        )


def test_empty_data_rejected(tmp_path):
    with pytest.raises(ValueError):
        load_weather_intervals_csv(
            write_csv(tmp_path)
        )


def test_source_type_preserved(tmp_path):
    satellite_row = ROW_1.replace(
        "SYNTHETIC",
        "SATELLITE",
    )

    data = load_weather_intervals_csv(
        write_csv(tmp_path, satellite_row)
    )

    assert data[0].source_type == "SATELLITE"
    assert (
        data[0].weather.irradiance.source_type
        == "SATELLITE"
    )
