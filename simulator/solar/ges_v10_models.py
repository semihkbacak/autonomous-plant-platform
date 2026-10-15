
"""Optional, explicitly supplied inverter screening curves. NO OEM claims.

Not wired to the existing simulation by default. Never substitute unknown
manufacturer curves with estimated or synthetic values in an OEM-ready run.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


def _number(value: float, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Curve values must be finite numbers")
    if (positive and value <= 0) or (not positive and value < 0):
        raise ValueError("Curve value outside allowed range")
    return float(value)


@dataclass(frozen=True)
class InverterScreeningCurve:
    """Measured or assumed external points; provenance is declaration only.

    curve: (DC input in kW, conversion efficiency [0..1]), strictly ordered.
    thermal: (ambient Celsius, available rated AC fraction [0..1]).
    Both curves must cover the evaluated operating point; no extrapolation.
    """
    inverter_id: str
    ac_rating_kw: float
    efficiency_points: tuple[tuple[float, float], ...]
    thermal_points: tuple[tuple[float, float], ...]
    source_note: str

    def __post_init__(self) -> None:
        if not self.inverter_id.strip() or not self.source_note.strip():
            raise ValueError("Inverter ID and source note are required")
        _number(self.ac_rating_kw, positive=True)
        for points in (self.efficiency_points, self.thermal_points):
            if len(points) < 2:
                raise ValueError("At least two points required")
            xs = []
            for x, y in points:
                if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x):
                    raise ValueError("Invalid curve coordinate")
                _number(y)
                if not 0 <= y <= 1:
                    raise ValueError("Efficiency/derating must be a fraction")
                xs.append(x)
            if any(a >= b for a, b in zip(xs, xs[1:])):
                raise ValueError("Curve x-values must increase strictly")

    @staticmethod
    def _interp(points: tuple[tuple[float, float], ...], x: float) -> float:
        if not points[0][0] <= x <= points[-1][0]:
            raise ValueError("Operating point outside supplied curve (no extrapolation)")
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= x <= x1:
                return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
        raise AssertionError("Invalid interpolation state")

    def screen(self, dc_kw: float, ambient_c: float) -> dict:
        dc_kw = _number(dc_kw)
        if isinstance(ambient_c, bool) or not isinstance(ambient_c, (float, int)) or not isfinite(ambient_c):
            raise ValueError("Invalid ambient temperature")
        if ambient_c <= -273.15:
            raise ValueError("Invalid thermodynamic temperature")
        efficiency = self._interp(self.efficiency_points, dc_kw)
        thermal_fraction = self._interp(self.thermal_points, ambient_c)
        conversion_kw = dc_kw * efficiency
        max_ac_kw = self.ac_rating_kw * thermal_fraction
        return {
            "inverter_id": self.inverter_id,
            "source_note": self.source_note,
            "dc_kw": dc_kw,
            "efficiency": efficiency,
            "thermal_fraction": thermal_fraction,
            "ac_kw": min(conversion_kw, max_ac_kw),
            "conversion_loss_kw": dc_kw - conversion_kw,
            "clipped_kw": max(0.0, conversion_kw - max_ac_kw),
            "mode": "SUPPLIED_CURVE_SCREENING_NOT_OEM_CALIBRATION",
        }
