"""HES screening physics, not a method-of-characteristics hydraulic model.

Joukowsky gives a conservative *instantaneous* wave-pressure estimate under
ideal assumptions. It is NOT sufficient to size surge relief or protect a penstock.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import isfinite


def number(name: str, value: float, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} outside supported screening bounds")
    return float(value)


@dataclass(frozen=True)
class SurgeScreen:
    flow_m3_s: float
    pipe_diameter_m: float
    wave_speed_m_s: float
    closure_s: float
    penstock_length_m: float
    rho_kg_m3: float = 1000.0
    static_pressure_bar: float = 20.0

    def evaluate(self) -> dict:
        from math import pi
        flow = number('flow', self.flow_m3_s, 0, 2000)
        diameter = number('diameter', self.pipe_diameter_m, 0.05, 20)
        wave = number('wave_speed', self.wave_speed_m_s, 100, 2000)
        closure = number('closure', self.closure_s, 0.001, 3600)
        length = number('penstock_length', self.penstock_length_m, 1, 30000)
        rho = number('density', self.rho_kg_m3, 500, 1500)
        static = number('static_pressure', self.static_pressure_bar, 0, 1000)
        velocity = flow / (pi * diameter**2 / 4)
        delta_pa = rho * wave * velocity
        critical_s = 2 * length / wave
        # This is NOT a reliable formula for slow valve closures. Report the
        # upper-bound ideal instantaneous estimate, never imply a safe pressure.
        return {
            'velocity_m_s': round(velocity, 6),
            'two_way_wave_time_s': round(critical_s, 6),
            'fast_closure_indicator': closure <= critical_s,
            'instantaneous_joukowsky_delta_bar': round(delta_pa / 1e5, 6),
            'instantaneous_total_pressure_bar': round(static + delta_pa / 1e5, 6),
            'applicable_as_design_pressure': False,
            'engineering_scope': 'IDEAL_JOUKOWSKY_SCREEN_NOT_TRANSIENT_HYDRAULIC_VALIDATION',
            'requires': ['METHOD_OF_CHARACTERISTICS', 'PIPE_WALL_ELASTICITY', 'BOUNDARY_CONDITIONS', 'FIELD_VALIDATION'],
        }


def reservoir_mass_balance(volume_m3: float, inflow_m3_s: float, release_m3_s: float,
                           spill_m3_s: float, dt_s: float, capacity_m3: float) -> dict:
    current = number('volume', volume_m3, 0, 1e12)
    inflow = number('inflow', inflow_m3_s, 0, 1e6)
    release = number('release', release_m3_s, 0, 1e6)
    spill = number('spill', spill_m3_s, 0, 1e6)
    delta = number('dt', dt_s, 0.001, 86400)
    capacity = number('capacity', capacity_m3, 1, 1e12)
    if current > capacity:
        raise ValueError('Reservoir volume exceeds capacity')
    proposed = current + (inflow - release - spill) * delta
    # Refuse instead of silently inventing water or an automatic spill gate.
    if not 0 <= proposed <= capacity:
        return {'accepted': False, 'proposed_volume_m3': round(proposed, 3),
                'reason': 'BOUNDARY_EXCEEDED', 'applied_flow_adjustment': False}
    return {'accepted': True, 'proposed_volume_m3': round(proposed, 3),
            'reason': 'WITHIN_SCREENING_LIMITS', 'applied_flow_adjustment': False}


def efficiency_map_screen(flow_ratio: float, head_ratio: float,
                          points: list[tuple[float, float, float]]) -> dict:
    """Nearest supplied efficiency sample, not bilinear OEM interpolation."""
    q = number('flow_ratio', flow_ratio, 0, 2)
    h = number('head_ratio', head_ratio, 0, 2)
    if not points or len(points) > 10000:
        raise ValueError('1..10000 supplied points required')
    checked=[]
    for qp, hp, eff in points:
        checked.append((number('sample_flow',qp,0,2), number('sample_head',hp,0,2),
                        number('efficiency',eff,0,1)))
    nearest = min(checked, key=lambda x:(x[0]-q)**2+(x[1]-h)**2)
    return {'efficiency_fraction': nearest[2], 'sample_coordinates': nearest[:2],
            'interpolation': False, 'oem_validated': False,
            'scope': 'NEAREST_DECLARED_MAP_SAMPLE_ONLY'}
