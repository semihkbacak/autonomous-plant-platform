"""End-to-end synthetic GHI/DNI/DHI -> POA -> PV module DC MPP demo.

This is NOT the final HES/GES/RES app, an AC model, a real data connector,
or an industrial controller. Parameter values are synthetic.
"""
from datetime import datetime, timezone
from math import cos, radians

import pandas as pd
import pvlib

from simulator.solar.solar_resource import (
    IrradianceSample,
    PVSurface,
    SolarSite,
    calculate_poa,
)
from simulator.solar.pv_array import (
    PVArrayConfiguration,
    calculate_pv_array_from_poa,
    synthetic_demo_module,
)


def main():
    site = SolarSite(latitude_deg=39.93, longitude_deg=32.86)
    surface = PVSurface(tilt_deg=30.0, azimuth_deg=180.0)
    now = datetime(2026, 6, 21, 10, 0, tzinfo=timezone.utc)
    # Construct a consistent synthetic horizontal irradiance triplet.
    sun = pvlib.solarposition.get_solarposition(pd.DatetimeIndex([now]), 39.93, 32.86)
    zenith = float(sun["apparent_zenith"].iloc[0])
    dni, dhi = 700.0, 150.0
    ghi = dhi + dni * max(0.0, cos(radians(zenith)))
    poa = calculate_poa(site, surface, IrradianceSample(now, ghi, dni, dhi))

    config = PVArrayConfiguration(
        modules_per_string=10,
        parallel_strings=2,
        module=synthetic_demo_module(),
    )
    dc = calculate_pv_array_from_poa(
        poa_result=poa,
        ambient_temperature_c=25.0,
        wind_speed_m_s=3.0,
        config=config,
    )
    print("GES DC DEMO - SYNTHETIC VALUES ONLY")
    print("Timestamp UTC:", poa.timestamp_utc.isoformat())
    print(f"POA irradiance: {poa.poa_global_w_m2:.2f} W/m²")
    print(f"PV module temperature: {dc.temperature.module_temperature_c:.2f} °C")
    print(f"PV cell temperature: {dc.temperature.cell_temperature_c:.2f} °C")
    print(f"Module MPP: {dc.module_pmp_w:.2f} W")
    print(f"Array DC MPP: {dc.array_pmp_kw:.3f} kW")
    print("Data quality flags:", dc.source_quality_flags)
    print("NOTICE: This is available DC MPP only; no inverter AC power is computed.")


if __name__ == "__main__":
    main()
