
from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite, sqrt


# ============================================================
# AC POWER CAPABILITY - SIMULATION SCREENING ONLY
# ============================================================


@dataclass(frozen=True)
class ACOperatingRequest:
    nameplate_kva: float
    requested_active_kw: float
    requested_reactive_kvar: float

    # Optional externally established operating limit.
    # This is NOT calculated from temperature automatically.
    temperature_limit_kva: float | None = None
    temperature_limit_source: str | None = None


@dataclass(frozen=True)
class ACPowerScreeningResult:
    applied_kva_limit: float

    requested_apparent_kva: float
    requested_reactive_kvar: float

    max_active_kw: float | None
    candidate_active_kw: float | None
    active_shortfall_kw: float | None

    candidate_power_factor: float | None

    status: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def request_is_feasible(self) -> bool:
        return self.status == "WITHIN_CAPABILITY"


def _validate_number(
    name: str,
    value: float,
    allow_zero: bool = True,
) -> float:

    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
    ):
        raise ValueError(f"{name} must be finite")

    if allow_zero:
        valid = value >= 0
    else:
        valid = value > 0

    if not valid:
        raise ValueError(f"{name} outside valid range")

    return float(value)


def evaluate_ac_power(
    request: ACOperatingRequest,
) -> ACPowerScreeningResult:
    """
    Evaluate a simplified P-Q apparent-power envelope.

    Does not model:
    - OEM-specific capability curves
    - Grid voltage/frequency restrictions
    - DC availability
    - Grid protection
    - Autonomous equipment commands

    Unknown thermal capability is explicitly reported.
    """

    # 1. Validate operating request.

    nameplate = _validate_number(
        "nameplate_kva",
        request.nameplate_kva,
        allow_zero=False,
    )

    requested_p = _validate_number(
        "requested_active_kw",
        request.requested_active_kw,
    )

    requested_q = request.requested_reactive_kvar

    if (
        isinstance(requested_q, bool)
        or not isinstance(requested_q, (int, float))
        or not isfinite(requested_q)
    ):
        raise ValueError(
            "requested_reactive_kvar must be finite"
        )

    requested_q = float(requested_q)

    # 2. Determine capacity available for screening.

    warnings = []

    if request.temperature_limit_kva is None:

        if request.temperature_limit_source is not None:
            raise ValueError(
                "Temperature limit source without a limit"
            )

        applied_limit = nameplate

        warnings.append(
            "THERMAL_CAPABILITY_NOT_VERIFIED"
        )

    else:

        thermal_limit = _validate_number(
            "temperature_limit_kva",
            request.temperature_limit_kva,
            allow_zero=False,
        )

        if thermal_limit > nameplate:
            raise ValueError(
                "Temperature limit exceeds nameplate"
            )

        source = request.temperature_limit_source

        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                "Temperature limit requires a source"
            )

        applied_limit = thermal_limit

        if thermal_limit < nameplate:
            warnings.append(
                "THERMAL_KVA_LIMIT_APPLIED"
            )

    # 3. Calculate requested apparent power.

    requested_s = hypot(requested_p, requested_q)

    # 4. Check reactive power feasibility first.

    if abs(requested_q) > applied_limit:

        return ACPowerScreeningResult(
            applied_kva_limit=applied_limit,
            requested_apparent_kva=requested_s,
            requested_reactive_kvar=requested_q,
            max_active_kw=None,
            candidate_active_kw=None,
            active_shortfall_kw=None,
            candidate_power_factor=None,
            status="REACTIVE_REQUEST_INFEASIBLE",
            reasons=(
                "REACTIVE_REQUEST_EXCEEDS_KVA_LIMIT",
            ),
            warnings=tuple(warnings),
        )

    # 5. Active power boundary for this Q request.

    max_active = sqrt(
        max(
            0.0,
            applied_limit**2 - requested_q**2,
        )
    )

    candidate_active = min(requested_p, max_active)

    shortfall = max(
        0.0,
        requested_p - candidate_active,
    )

    # 6. Power factor at the candidate operating point.

    candidate_s = hypot(
        candidate_active,
        requested_q,
    )

    power_factor = (
        candidate_active / candidate_s
        if candidate_s > 0
        else None
    )

    # 7. Determine screening result.

    if shortfall > 1e-9:
        status = "ACTIVE_POWER_LIMITED"
        reasons = (
            "ACTIVE_POWER_EXCEEDS_KVA_ENVELOPE",
        )
    else:
        status = "WITHIN_CAPABILITY"
        reasons = ()

    return ACPowerScreeningResult(
        applied_kva_limit=applied_limit,
        requested_apparent_kva=requested_s,
        requested_reactive_kvar=requested_q,
        max_active_kw=max_active,
        candidate_active_kw=candidate_active,
        active_shortfall_kw=shortfall,
        candidate_power_factor=power_factor,
        status=status,
        reasons=reasons,
        warnings=tuple(warnings),
    )
