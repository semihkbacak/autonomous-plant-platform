"""Parallel shaded PV strings: sampled IV aggregation for research screening.

Input IV curves must be supplied from measurements or a separately validated
model. No inverter integration, MPPT dynamics or bypass topology certification.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class IVSample:
    voltage_v: float
    current_a: float


def _validate_curve(points: tuple[IVSample, ...]) -> None:
    if not 2 <= len(points) <= 5000:
        raise ValueError('Each string requires 2..5000 voltage/current samples')
    last = -1.0
    for p in points:
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v)
               for v in (p.voltage_v,p.current_a)):
            raise ValueError('Nonfinite IV sample')
        if p.voltage_v < 0 or p.current_a < 0 or p.voltage_v <= last:
            raise ValueError('Voltage must increase strictly; current must be nonnegative')
        last = p.voltage_v


def _current(points: tuple[IVSample, ...], voltage: float) -> float:
    if voltage < points[0].voltage_v or voltage > points[-1].voltage_v:
        return 0.0  # No extrapolation; source data must cover desired voltage.
    for a,b in zip(points, points[1:]):
        if a.voltage_v <= voltage <= b.voltage_v:
            t = (voltage-a.voltage_v)/(b.voltage_v-a.voltage_v)
            return max(0.0, a.current_a + t*(b.current_a-a.current_a))
    return points[-1].current_a


def parallel_string_mppt(strings: tuple[tuple[IVSample, ...], ...],
                         mppt_min_v: float, mppt_max_v: float,
                         samples: int = 1001) -> dict:
    if not 1 <= len(strings) <= 48:
        raise ValueError('1..48 IV strings supported')
    for curve in strings:
        _validate_curve(curve)
    for x in (mppt_min_v,mppt_max_v):
        if isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x):
            raise ValueError('MPPT voltage must be finite')
    if not 0 <= mppt_min_v < mppt_max_v <= 2000:
        raise ValueError('Invalid MPPT window')
    if isinstance(samples,bool) or not isinstance(samples,int) or not 50 <= samples <= 20000:
        raise ValueError('Invalid sampling resolution')
    # Only overlapping measured voltage domains can be meaningfully summed.
    start = max(c[0].voltage_v for c in strings)
    end = min(c[-1].voltage_v for c in strings)
    if start >= end:
        raise ValueError('String IV voltage domains do not overlap')
    candidates=[]
    for i in range(samples):
        v=start+(end-start)*i/(samples-1)
        p=v*sum(_current(curve,v) for curve in strings)
        candidates.append((v,p))
    overall = max(candidates,key=lambda x:x[1])
    bounded = [x for x in candidates if mppt_min_v <= x[0] <= mppt_max_v]
    within = max(bounded,key=lambda x:x[1]) if bounded else (0.0,0.0)
    local = sum(candidates[i][1]>candidates[i-1][1] and
                candidates[i][1]>=candidates[i+1][1]
                for i in range(1,len(candidates)-1))
    return {
        'string_count': len(strings), 'global_mpp_v':round(overall[0],4),
        'global_mpp_w':round(overall[1],4),
        'mppt_window_mpp_v':round(within[0],4),
        'mppt_window_mpp_w':round(within[1],4),
        'local_peaks_detected':local, 'window_limit_w':round(overall[1]-within[1],4),
        'sample_resolution':samples, 'physical_bypass_model':False,
        'oem_calibrated':False, 'scope':'SAMPLED_PARALLEL_IV_SCREEN_ONLY',
    }
