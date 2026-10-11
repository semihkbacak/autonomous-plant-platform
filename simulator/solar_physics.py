from __future__ import annotations

from math import isfinite


# ============================================================
# SOLAR / PV DEMO CONSTANTS
# ============================================================

STANDARD_IRRADIANCE_W_M2 = 1000.0
STANDARD_CELL_TEMPERATURE_C = 25.0

# Sentetik/demo NOCT değeri.
DEFAULT_NOCT_C = 45.0

# Yaklaşık PV güç sıcaklık katsayısı.
# Her +1 °C hücre sıcaklığında yaklaşık -%0.4 güç.
DEFAULT_POWER_TEMP_COEFF_PER_C = -0.004

# Demo inverter verimi.
DEFAULT_INVERTER_EFFICIENCY = 0.98


# ============================================================
# VALIDATION
# ============================================================

def _require_finite(value: float, name: str) -> None:
    if not isfinite(value):
        raise ValueError(f"{name} must be finite")


# ============================================================
# PV CELL TEMPERATURE
# ============================================================

def calculate_cell_temperature_c(
    ambient_temperature_c: float,
    irradiance_w_m2: float,
    noct_c: float = DEFAULT_NOCT_C,
) -> float:
    """
    Basitleştirilmiş PV hücre sıcaklığı modeli.

    T_cell =
        T_ambient
        + ((NOCT - 20) / 800) * irradiance

    Tüm değerler simülasyon/demo amaçlıdır.
    """

    _require_finite(
        ambient_temperature_c,
        "ambient_temperature_c",
    )
    _require_finite(
        irradiance_w_m2,
        "irradiance_w_m2",
    )
    _require_finite(
        noct_c,
        "noct_c",
    )

    if irradiance_w_m2 < 0.0:
        raise ValueError(
            "irradiance_w_m2 cannot be negative"
        )

    if noct_c <= 0.0:
        raise ValueError(
            "noct_c must be positive"
        )

    return (
        ambient_temperature_c
        + (
            (noct_c - 20.0)
            / 800.0
        )
        * irradiance_w_m2
    )


# ============================================================
# TEMPERATURE DERATING
# ============================================================

def calculate_temperature_factor(
    cell_temperature_c: float,
    power_temp_coeff_per_c: float = (
        DEFAULT_POWER_TEMP_COEFF_PER_C
    ),
) -> float:
    """
    Hücre sıcaklığının PV DC gücüne etkisini hesaplar.

    25 °C referans sıcaklığı kullanılır.

    Örnek:
    sıcaklık yükselirse güç faktörü azalır.
    """

    _require_finite(
        cell_temperature_c,
        "cell_temperature_c",
    )
    _require_finite(
        power_temp_coeff_per_c,
        "power_temp_coeff_per_c",
    )

    factor = (
        1.0
        + power_temp_coeff_per_c
        * (
            cell_temperature_c
            - STANDARD_CELL_TEMPERATURE_C
        )
    )

    return max(
        0.0,
        factor,
    )


# ============================================================
# AVAILABLE PV DC POWER
# ============================================================

def calculate_available_dc_power_kw(
    array_rated_power_kw: float,
    irradiance_w_m2: float,
    cell_temperature_c: float,
    power_temp_coeff_per_c: float = (
        DEFAULT_POWER_TEMP_COEFF_PER_C
    ),
) -> float:
    """
    PV dizisinin mevcut çevre koşullarında
    üretebileceği yaklaşık DC gücü hesaplar.

    Bu değer inverter setpoint'i değildir.

    Bu, o anda fiziksel olarak kullanılabilir
    sentetik PV gücüdür.
    """

    _require_finite(
        array_rated_power_kw,
        "array_rated_power_kw",
    )
    _require_finite(
        irradiance_w_m2,
        "irradiance_w_m2",
    )
    _require_finite(
        cell_temperature_c,
        "cell_temperature_c",
    )

    if array_rated_power_kw <= 0.0:
        raise ValueError(
            "array_rated_power_kw must be positive"
        )

    if irradiance_w_m2 < 0.0:
        raise ValueError(
            "irradiance_w_m2 cannot be negative"
        )

    irradiance_ratio = (
        irradiance_w_m2
        / STANDARD_IRRADIANCE_W_M2
    )

    temperature_factor = (
        calculate_temperature_factor(
            cell_temperature_c=(
                cell_temperature_c
            ),
            power_temp_coeff_per_c=(
                power_temp_coeff_per_c
            ),
        )
    )

    power_kw = (
        array_rated_power_kw
        * irradiance_ratio
        * temperature_factor
    )

    return max(
        0.0,
        power_kw,
    )


# ============================================================
# INVERTER AC POWER
# ============================================================

def calculate_available_ac_power_kw(
    available_dc_power_kw: float,
    inverter_rated_power_kw: float,
    inverter_efficiency: float = (
        DEFAULT_INVERTER_EFFICIENCY
    ),
) -> float:
    """
    DC taraftaki kullanılabilir PV gücünden,
    inverter çıkışında kullanılabilecek AC gücü
    hesaplar.

    Inverter nominal gücünün üzerinde çıkış
    üretilmesine izin verilmez (clipping).
    """

    _require_finite(
        available_dc_power_kw,
        "available_dc_power_kw",
    )
    _require_finite(
        inverter_rated_power_kw,
        "inverter_rated_power_kw",
    )
    _require_finite(
        inverter_efficiency,
        "inverter_efficiency",
    )

    if available_dc_power_kw < 0.0:
        raise ValueError(
            "available_dc_power_kw cannot be negative"
        )

    if inverter_rated_power_kw <= 0.0:
        raise ValueError(
            "inverter_rated_power_kw must be positive"
        )

    if not (
        0.0
        < inverter_efficiency
        <= 1.0
    ):
        raise ValueError(
            "inverter_efficiency must be between 0 and 1"
        )

    converted_power_kw = (
        available_dc_power_kw
        * inverter_efficiency
    )

    return min(
        converted_power_kw,
        inverter_rated_power_kw,
    )


# ============================================================
# CURTAILMENT / TARGET
# ============================================================

def calculate_deliverable_power_kw(
    requested_target_kw: float,
    available_power_kw: float,
) -> float:
    """
    Operatör/scheduler hedefi ile mevcut güneş
    kaynağını karşılaştırır.

    Örnek:

    target = 800 kW
    available = 530 kW

    deliverable = 530 kW
    """

    _require_finite(
        requested_target_kw,
        "requested_target_kw",
    )
    _require_finite(
        available_power_kw,
        "available_power_kw",
    )

    if requested_target_kw < 0.0:
        raise ValueError(
            "requested_target_kw cannot be negative"
        )

    if available_power_kw < 0.0:
        raise ValueError(
            "available_power_kw cannot be negative"
        )

    return min(
        requested_target_kw,
        available_power_kw,
    )


def calculate_unserved_target_kw(
    requested_target_kw: float,
    deliverable_power_kw: float,
) -> float:
    """
    Güneş kaynağı veya ekipman kapasitesi nedeniyle
    karşılanamayan üretim hedefini hesaplar.
    """

    _require_finite(
        requested_target_kw,
        "requested_target_kw",
    )
    _require_finite(
        deliverable_power_kw,
        "deliverable_power_kw",
    )

    if requested_target_kw < 0.0:
        raise ValueError(
            "requested_target_kw cannot be negative"
        )

    if deliverable_power_kw < 0.0:
        raise ValueError(
            "deliverable_power_kw cannot be negative"
        )

    return max(
        0.0,
        requested_target_kw
        - deliverable_power_kw,
    )


# ============================================================
# ENERGY
# ============================================================

def calculate_interval_energy_kwh(
    power_kw: float,
    interval_minutes: float,
) -> float:
    """
    Sabit ortalama güç kabulüyle zaman aralığındaki
    enerjiyi hesaplar.
    """

    _require_finite(
        power_kw,
        "power_kw",
    )
    _require_finite(
        interval_minutes,
        "interval_minutes",
    )

    if power_kw < 0.0:
        raise ValueError(
            "power_kw cannot be negative"
        )

    if interval_minutes <= 0.0:
        raise ValueError(
            "interval_minutes must be positive"
        )

    return (
        power_kw
        * interval_minutes
        / 60.0
    )