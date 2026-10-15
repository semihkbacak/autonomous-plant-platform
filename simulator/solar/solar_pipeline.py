
from __future__ import annotations
from typing import Mapping

from simulator.solar.pq_dispatch import (
    PQCapability,
    dispatch_with_pq,
)
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import Sequence

from simulator.solar.solar_resource import (
    IrradianceSample,
    PVSurface,
    SolarSite,
    POAResult,
    calculate_poa,
)

from simulator.solar.pv_array import (
    PVArrayConfiguration,
    PVArrayDCResult,
    calculate_pv_array_from_poa,
)

from simulator.solar.inverter import InverterConfig

from simulator.solar.solar_plant import (
    SolarInverterInput,
    SolarPlantReport,
    SolarPlantSimulator,
)


# ============================================================
# WEATHER INPUT
# ============================================================

@dataclass(frozen=True)
class SolarWeather:
    irradiance: IrradianceSample
    ambient_temperature_c: float
    wind_speed_m_s: float


# ============================================================
# PV ARRAY + INVERTER CONNECTION
# ============================================================

@dataclass(frozen=True)
class SolarAsset:
    inverter: InverterConfig
    array: PVArrayConfiguration
    surface: PVSurface


# ============================================================
# SINGLE ARRAY CALCULATION
# ============================================================

@dataclass(frozen=True)
class SolarArrayReport:
    inverter_id: str
    poa: POAResult
    dc: PVArrayDCResult


# ============================================================
# COMPLETE PLANT SNAPSHOT
# ============================================================

@dataclass(frozen=True)
class SolarPipelineReport:
    timestamp_utc: datetime
    array_reports: tuple[SolarArrayReport, ...]
    plant: SolarPlantReport


# ============================================================
# SOLAR PHYSICS PIPELINE
# ============================================================

class SolarPhysicsPipeline:
    """
    GES fizik modellerini uçtan uca birleştirir.

    GHI / DNI / DHI
         -> POA
         -> PV sıcaklık
         -> DC MPP
         -> inverter AC
         -> plant dispatch

    Sadece simülasyon ve analiz amaçlıdır.
    Gerçek PLC/SCADA komutu göndermez.
    """

    def __init__(
        self,
        site: SolarSite,
        assets: Sequence[SolarAsset],
    ) -> None:

        self.site = site
        self.assets = tuple(assets)

        # Çoklu inverter işletim hesaplayıcısı.
        # Boş veya tekrarlanan inverter kimlikleri
        # SolarPlantSimulator tarafından reddedilir.
        self.plant = SolarPlantSimulator(
            [
                asset.inverter
                for asset in self.assets
            ]
        )

        self.inverter_ids = {
            asset.inverter.inverter_id
            for asset in self.assets
        }

    # ========================================================
    # SIMULATION
    # ========================================================

    def simulate(
        self,
        weather: SolarWeather,
        requested_target_kw: float | None = None,
        *,
        grid_available: bool = True,
        emergency_stop: bool = False,
        fault_inverter_ids: frozenset[str] = frozenset(),
        maintenance_inverter_ids: frozenset[str] = frozenset(),
        pq_capabilities: Mapping[str, PQCapability] | None = None,
        reactive_requests_kvar: Mapping[str, float] | None = None,
    ) -> SolarPipelineReport:

        # ----------------------------------------
        # WEATHER VALIDATION
        # ----------------------------------------

        if (
            not isfinite(weather.ambient_temperature_c)
            or weather.ambient_temperature_c <= -273.15
        ):
            raise ValueError(
                "Invalid ambient temperature"
            )

        if (
            not isfinite(weather.wind_speed_m_s)
            or weather.wind_speed_m_s < 0
        ):
            raise ValueError(
                "Invalid wind speed"
            )

        # ----------------------------------------
        # INVERTER ID VALIDATION
        # ----------------------------------------

        unknown_faults = (
            set(fault_inverter_ids)
            - self.inverter_ids
        )

        unknown_locks = (
            set(maintenance_inverter_ids)
            - self.inverter_ids
        )

        if unknown_faults or unknown_locks:
            raise ValueError(
                "Unknown inverter ID in fault/lock inputs"
            )

        # ----------------------------------------
        # ARRAY PHYSICS
        # ----------------------------------------

        array_reports = []
        inverter_inputs = []
                # Cache only for the current simulation instant.
        # The next interval starts with empty caches.
        poa_cache = {}
        dc_cache = {}

        for asset in self.assets:

                        # 1. Reuse POA for identical surfaces.
            surface_key = asset.surface

            if surface_key not in poa_cache:
                poa_cache[surface_key] = calculate_poa(
                    site=self.site,
                    surface=asset.surface,
                    sample=weather.irradiance,
                )

            poa = poa_cache[surface_key]

            # 2. Reuse DC physics for identical arrays.
            temperature_params = getattr(
                asset,
                "temperature_params",
                None,
            )

            dc_key = (
                asset.surface,
                asset.array,
                temperature_params,
            )

            if dc_key not in dc_cache:
                dc_cache[dc_key] = (
                    calculate_pv_array_from_poa(
                        poa_result=poa,
                        ambient_temperature_c=(
                            weather.ambient_temperature_c
                        ),
                        wind_speed_m_s=(
                            weather.wind_speed_m_s
                        ),
                        config=asset.array,
                        temperature_params=temperature_params,
                    )
                )

            dc = dc_cache[dc_key]

            inverter_id = (
                asset.inverter.inverter_id
            )

            array_reports.append(
                SolarArrayReport(
                    inverter_id=inverter_id,
                    poa=poa,
                    dc=dc,
                )
            )

            # 3. Use calculated DC MPP values.
            # No hard-coded DC voltage or power.
            inverter_inputs.append(
                SolarInverterInput(
                    inverter_id=inverter_id,
                    dc_power_kw=dc.array_pmp_kw,
                    dc_voltage_v=dc.array_vmp_v,
                    fault_active=(
                        inverter_id
                        in fault_inverter_ids
                    ),
                    maintenance_lock=(
                        inverter_id
                        in maintenance_inverter_ids
                    ),
                )
            )

        # ----------------------------------------
        # MULTI-INVERTER PLANT DISPATCH
        # ----------------------------------------

        if (
            pq_capabilities is None
            and reactive_requests_kvar is None
        ):
            # Legacy behavior remains unchanged.
            plant_report = self.plant.simulate(
                inputs=inverter_inputs,
                requested_target_kw=requested_target_kw,
                grid_available=grid_available,
                emergency_stop=emergency_stop,
            )

        else:
            if (
                pq_capabilities is None
                or reactive_requests_kvar is None
            ):
                raise ValueError(
                    "Both P-Q capability and Q requests required"
                )

            pq_result = dispatch_with_pq(
                plant=self.plant,
                inputs=inverter_inputs,

                capabilities=pq_capabilities,

                reactive_requests_kvar=(
                    reactive_requests_kvar
                ),

                requested_target_kw=(
                    requested_target_kw
                ),

                grid_available=grid_available,

                emergency_stop=emergency_stop,
            )

            plant_report = pq_result.plant

        return SolarPipelineReport(
            timestamp_utc=(
                array_reports[0].poa.timestamp_utc
            ),
            array_reports=tuple(array_reports),
            plant=plant_report,
        )
