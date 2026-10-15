
from dataclasses import dataclass
from math import isfinite

from pvlib.inverter import pvwatts


@dataclass(frozen=True)
class InverterConfig:
    inverter_id: str
    rated_ac_kw: float
    nominal_efficiency: float

    mppt_min_v: float
    mppt_max_v: float
    max_dc_voltage_v: float
    max_dc_current_a: float

    def __post_init__(self):
        if not self.inverter_id.strip():
            raise ValueError("Inverter ID cannot be empty")

        values = (
            self.rated_ac_kw,
            self.nominal_efficiency,
            self.mppt_min_v,
            self.mppt_max_v,
            self.max_dc_voltage_v,
            self.max_dc_current_a,
        )

        if not all(isfinite(value) for value in values):
            raise ValueError("Inverter parameters must be finite")

        if self.rated_ac_kw <= 0:
            raise ValueError("Rated AC power must be positive")

        if not 0 < self.nominal_efficiency <= 1:
            raise ValueError("Invalid inverter efficiency")

        if not (
            0 < self.mppt_min_v
            < self.mppt_max_v
            <= self.max_dc_voltage_v
        ):
            raise ValueError("Invalid DC voltage limits")

        if self.max_dc_current_a <= 0:
            raise ValueError("Max DC current must be positive")


@dataclass(frozen=True)
class InverterResult:
    inverter_id: str
    status: str

    dc_offered_kw: float
    dc_accepted_kw: float

    ac_unclipped_kw: float
    ac_available_kw: float
    ac_dispatched_kw: float

    dc_rejected_kw: float
    conversion_loss_kw: float
    clipping_loss_kw: float
    curtailment_kw: float

    reasons: tuple[str, ...]


def _zero_result(
    config: InverterConfig,
    dc_offered_kw: float,
    status: str,
    reasons: list[str],
) -> InverterResult:
    return InverterResult(
        inverter_id=config.inverter_id,
        status=status,
        dc_offered_kw=dc_offered_kw,
        dc_accepted_kw=0.0,
        ac_unclipped_kw=0.0,
        ac_available_kw=0.0,
        ac_dispatched_kw=0.0,
        dc_rejected_kw=0.0,
        conversion_loss_kw=0.0,
        clipping_loss_kw=0.0,
        curtailment_kw=0.0,
        reasons=tuple(reasons),
    )


def simulate_inverter(
    config: InverterConfig,
    dc_power_kw: float,
    dc_voltage_v: float,
    *,
    grid_available: bool = True,
    fault_active: bool = False,
    maintenance_lock: bool = False,
    active_power_limit_kw: float | None = None,
) -> InverterResult:

    if not isfinite(dc_power_kw) or dc_power_kw < 0:
        raise ValueError("Invalid DC power")

    if not isfinite(dc_voltage_v) or dc_voltage_v < 0:
        raise ValueError("Invalid DC voltage")

    if active_power_limit_kw is not None:
        if (
            not isfinite(active_power_limit_kw)
            or active_power_limit_kw < 0
        ):
            raise ValueError("Invalid active power limit")

    reasons = []

    if not grid_available:
        reasons.append("GRID_UNAVAILABLE")

    if fault_active:
        reasons.append("INVERTER_FAULT")

    if maintenance_lock:
        reasons.append("MAINTENANCE_LOCK")

    if dc_power_kw > 0:
        if dc_voltage_v <= 0:
            reasons.append("INVALID_DC_VOLTAGE")

        elif dc_voltage_v > config.max_dc_voltage_v:
            reasons.append("DC_OVERVOLTAGE")

        elif not (
            config.mppt_min_v
            <= dc_voltage_v
            <= config.mppt_max_v
        ):
            reasons.append("OUTSIDE_MPPT_WINDOW")

    if reasons:
        return _zero_result(
            config,
            dc_power_kw,
            "BLOCKED",
            reasons,
        )

    if dc_power_kw == 0:
        return _zero_result(
            config,
            dc_power_kw,
            "IDLE",
            ["NO_DC_POWER"],
        )

    # DC current limitation.
    max_dc_power_by_current_kw = (
        dc_voltage_v
        * config.max_dc_current_a
        / 1000.0
    )

    dc_accepted_kw = min(
        dc_power_kw,
        max_dc_power_by_current_kw,
    )

    dc_rejected_kw = max(
        0.0,
        dc_power_kw - dc_accepted_kw,
    )

    if dc_rejected_kw > 1e-9:
        reasons.append("DC_CURRENT_LIMIT")

    # PVWatts DC input reference.
    # This is NOT the PV array STC rating.
    pdc0_kw = (
        config.rated_ac_kw
        / config.nominal_efficiency
    )

    ac_available_kw = float(
        pvwatts(
            pdc=dc_accepted_kw,
            pdc0=pdc0_kw,
            eta_inv_nom=config.nominal_efficiency,
        )
    )

    ac_available_kw = max(0.0, ac_available_kw)

    # PVWatts efficiency formula before AC clipping.
    zeta = dc_accepted_kw / pdc0_kw

    efficiency = (
        config.nominal_efficiency / 0.9637
    ) * (
        -0.0162 * zeta
        - 0.0059 / zeta
        + 0.9858
    )

    ac_unclipped_kw = max(
        0.0,
        dc_accepted_kw * efficiency,
    )

    clipping_loss_kw = max(
        0.0,
        ac_unclipped_kw - ac_available_kw,
    )

    conversion_loss_kw = max(
        0.0,
        dc_accepted_kw - ac_unclipped_kw,
    )

    if clipping_loss_kw > 1e-9:
        reasons.append("AC_CLIPPING")

    # Operator / scheduler curtailment.
    if active_power_limit_kw is None:
        ac_dispatched_kw = ac_available_kw
    else:
        ac_dispatched_kw = min(
            ac_available_kw,
            active_power_limit_kw,
        )

    curtailment_kw = max(
        0.0,
        ac_available_kw - ac_dispatched_kw,
    )

    if curtailment_kw > 1e-9:
        reasons.append("ACTIVE_POWER_LIMIT")

    status = (
        "RUNNING"
        if ac_dispatched_kw > 0
        else "CURTAILED"
    )

    return InverterResult(
        inverter_id=config.inverter_id,
        status=status,
        dc_offered_kw=dc_power_kw,
        dc_accepted_kw=dc_accepted_kw,
        ac_unclipped_kw=ac_unclipped_kw,
        ac_available_kw=ac_available_kw,
        ac_dispatched_kw=ac_dispatched_kw,
        dc_rejected_kw=dc_rejected_kw,
        conversion_loss_kw=conversion_loss_kw,
        clipping_loss_kw=clipping_loss_kw,
        curtailment_kw=curtailment_kw,
        reasons=tuple(reasons),
    )
