"""v0.6: fit an explicit De Soto model to a user-supplied I-V point dataset.

Curve-fitting is NOT proof of OEM approval or independent field validation.
Calibration inputs must carry source metadata; fitting cannot invent data.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from pathlib import Path

import numpy as np
import pvlib
from scipy.optimize import least_squares

from simulator.solar.pv_array import DeSotoModuleParameters


@dataclass(frozen=True)
class IVSample:
    curve_id: str
    irradiance_w_m2: float
    cell_temp_c: float
    voltage_v: float
    current_a: float


@dataclass(frozen=True)
class FitResult:
    parameters: DeSotoModuleParameters
    training_rmse_a: float
    holdout_rmse_a: float
    training_count: int
    holdout_count: int
    optimizer_success: bool
    provenance: str
    oem_verified: bool = False

    def report(self) -> dict:
        result = asdict(self)
        result["status"] = "PROVISIONAL_CURVE_FIT_NOT_OEM_VERIFIED"
        return result


def load_iv_csv(path: str | Path) -> list[IVSample]:
    """CSV: curve_id,irradiance_w_m2,cell_temp_c,voltage_v,current_a."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = set(IVSample.__dataclass_fields__)
        if not required <= set(reader.fieldnames or ()):
            raise ValueError("Missing I-V dataset columns")
        samples = [
            IVSample(
                curve_id=row["curve_id"].strip(),
                irradiance_w_m2=float(row["irradiance_w_m2"]),
                cell_temp_c=float(row["cell_temp_c"]),
                voltage_v=float(row["voltage_v"]),
                current_a=float(row["current_a"]),
            )
            for row in reader
        ]
    validate_iv_samples(samples)
    return samples


def validate_iv_samples(
    samples: list[IVSample] | tuple[IVSample, ...],
) -> None:
    if len(samples) < 24:
        raise ValueError("Need at least 24 measured I-V points")

    per_curve: dict[str, list[IVSample]] = {}

    for item in samples:
        if not item.curve_id:
            raise ValueError("Empty curve identifier")

        values = (
            item.irradiance_w_m2,
            item.cell_temp_c,
            item.voltage_v,
            item.current_a,
        )

        if any(
            isinstance(x, bool) or not isfinite(x)
            for x in values
        ):
            raise ValueError("Nonfinite I-V observation")

        if not (
            50 <= item.irradiance_w_m2 <= 1500
            and -60 < item.cell_temp_c < 110
        ):
            raise ValueError("I-V conditions outside supported range")

        if item.voltage_v < 0 or item.current_a < 0:
            raise ValueError("Negative I-V point")

        per_curve.setdefault(item.curve_id, []).append(item)

    if len(per_curve) < 3:
        raise ValueError(
            "Need at least three separate I-V curves for holdout"
        )

    if any(
        len(set(p.voltage_v for p in curve)) < 6
        for curve in per_curve.values()
    ):
        raise ValueError(
            "Each curve needs six unique voltage points"
        )

    for curve in per_curve.values():
        if len({
            (p.irradiance_w_m2, p.cell_temp_c)
            for p in curve
        }) != 1:
            raise ValueError(
                "Irradiance/temperature must be constant per curve"
            )

    if (
        len({p.irradiance_w_m2 for p in samples}) < 2
        or len({p.cell_temp_c for p in samples}) < 2
    ):
        raise ValueError(
            "Fit needs irradiance and temperature diversity"
        )


def _predict(
    samples: list[IVSample],
    values: np.ndarray,
) -> np.ndarray:
    alpha, a_ref, il_ref, log_io, log_rsh, rs = values

    irradiance = np.array([
        p.irradiance_w_m2 for p in samples
    ])
    temperature = np.array([
        p.cell_temp_c for p in samples
    ])
    voltage = np.array([
        p.voltage_v for p in samples
    ])

    il, io, r_s, r_sh, nnsvth = (
        pvlib.pvsystem.calcparams_desoto(
            effective_irradiance=irradiance,
            temp_cell=temperature,
            alpha_sc=alpha,
            a_ref=a_ref,
            I_L_ref=il_ref,
            I_o_ref=10.0**log_io,
            R_sh_ref=10.0**log_rsh,
            R_s=rs,
        )
    )

    return np.maximum(
        0.0,
        np.asarray(
            pvlib.pvsystem.i_from_v(
                voltage,
                il, io, r_s, r_sh, nnsvth,
                method="lambertw",
            ),
            dtype=float,
        ),
    )


def fit_desoto_from_iv(
    samples: list[IVSample],
    *,
    initial: DeSotoModuleParameters,
    provenance: str,
    holdout_curve_id: str | None = None,
    max_nfev: int = 180,
) -> FitResult:
    """Fit on training curves; hold out an entire curve for validation."""

    validate_iv_samples(samples)

    if not provenance.strip() or len(provenance.strip()) < 8:
        raise ValueError(
            "Explicit dataset provenance is required"
        )

    curve_ids = sorted({p.curve_id for p in samples})
    holdout = holdout_curve_id or curve_ids[-1]

    if holdout not in curve_ids:
        raise ValueError("Unknown holdout curve")

    train = [
        p for p in samples if p.curve_id != holdout
    ]
    test = [
        p for p in samples if p.curve_id == holdout
    ]

    if (
        len({p.irradiance_w_m2 for p in train}) < 2
        or len({p.cell_temp_c for p in train}) < 2
    ):
        raise ValueError(
            "Training set lacks irradiation/temperature diversity"
        )

    if initial.i_o_ref_a <= 0 or initial.r_sh_ref_ohm <= 0:
        raise ValueError("Invalid initial parameters")

    x0 = np.array([
        initial.alpha_sc_a_per_c,
        initial.a_ref_v,
        initial.i_l_ref_a,
        np.log10(initial.i_o_ref_a),
        np.log10(initial.r_sh_ref_ohm),
        initial.r_s_ohm,
    ])

    lower = [-0.05, 0.2, 0.01, -16, 0.5, 0]
    upper = [0.05, 12, 45, -4, 6, 5]

    if (
        not np.all(np.isfinite(x0))
        or np.any(x0 < lower)
        or np.any(x0 > upper)
    ):
        raise ValueError(
            "Initial parameters outside supported fit bounds"
        )

    observed = np.array([
        p.current_a for p in train
    ])

    def residual(x):
        predicted = _predict(train, x)

        if not np.all(np.isfinite(predicted)):
            return np.full(len(train), 1e4)

        return predicted - observed

    fit = least_squares(
        residual,
        x0,
        bounds=(lower, upper),
        max_nfev=max_nfev,
        x_scale="jac",
        method="trf",
    )

    x = fit.x

    fitted = DeSotoModuleParameters(
        alpha_sc_a_per_c=float(x[0]),
        a_ref_v=float(x[1]),
        i_l_ref_a=float(x[2]),
        i_o_ref_a=float(10.0**x[3]),
        r_sh_ref_ohm=float(10.0**x[4]),
        r_s_ohm=float(x[5]),
    )

    training_rmse = sqrt(
        float(np.mean(np.square(residual(x))))
    )

    holdout_diff = (
        _predict(test, x)
        - np.array([p.current_a for p in test])
    )

    holdout_rmse = sqrt(
        float(np.mean(np.square(holdout_diff)))
    )

    if not (
        isfinite(training_rmse)
        and isfinite(holdout_rmse)
    ):
        raise ValueError(
            "Nonfinite De Soto calibration result"
        )

    return FitResult(
        parameters=fitted,
        training_rmse_a=training_rmse,
        holdout_rmse_a=holdout_rmse,
        training_count=len(train),
        holdout_count=len(test),
        optimizer_success=bool(fit.success),
        provenance=provenance.strip(),
    )