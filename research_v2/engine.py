"""Deterministic, OFFLINE multi-day energy simulations on one UTC clock.

Screening models, not OEM or safety/control physics. No industrial IO.
The same second index is shared across HES/GES/RES; measured input is not implied.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from math import isfinite, pi, sin
from typing import Iterator

from research_v2.workspace import parse_utc

UTC = timezone.utc

@dataclass(frozen=True)
class ScreeningConfig:
    start_utc: str
    days: int = 1
    step_s: int = 900
    hes_flow_m3_s: float = 15.0
    hes_head_m: float = 70.0
    hes_efficiency: float = 0.88
    ges_area_m2: float = 25000.0
    ges_efficiency: float = 0.18
    res_radius_m: float = 40.0
    res_cp: float = 0.38
    res_rho: float = 1.225
    res_rated_kw: float = 1500.0

    def __post_init__(self):
        parse_utc(self.start_utc)
        if type(self.days) is not int or not (1 <= self.days <= 31):
            raise ValueError('days must be 1..31')
        if type(self.step_s) is not int or self.step_s not in (60, 300, 900, 1800, 3600):
            raise ValueError('Supported UTC step seconds: 60, 300, 900, 1800, 3600')
        for name, val in self.__dict__.items():
            if name in ('start_utc','days','step_s'): continue
            if isinstance(val, bool) or not isinstance(val,(int,float)) or not isfinite(val) or val < 0:
                raise ValueError('Invalid model input: '+name)
        if not (0 <= self.hes_efficiency <= 1 and 0 <= self.ges_efficiency <= 1 and 0 <= self.res_cp <= 0.593):
            raise ValueError('Efficiency/Cp bounds violated')
        if self.res_rated_kw <= 0: raise ValueError('res_rated_kw must be >0')


def _screening_kw(kind: str, elapsed_seconds: int, config: ScreeningConfig) -> float:
    from research_v2.physics import hydro_ideal_kw, pv_ideal_kw, wind_ideal_kw
    hour = (parse_utc(config.start_utc) + timedelta(seconds=elapsed_seconds)).hour
    minute = (parse_utc(config.start_utc) + timedelta(seconds=elapsed_seconds)).minute
    solar_phase = (hour + minute/60 - 6) / 12
    sunlight = max(0.0, sin(pi*solar_phase)) if 0 <= solar_phase <= 1 else 0.0
    if kind == 'HES': return hydro_ideal_kw(config.hes_flow_m3_s,config.hes_head_m,config.hes_efficiency)
    if kind == 'GES': return pv_ideal_kw(config.ges_area_m2,1000*sunlight,config.ges_efficiency)
    if kind == 'RES':
        # Illustrative synthetic daily wind cycle, not measured weather data.
        wind = max(0.0, 7.5 + 2 * sin(2*pi * (hour+minute/60)/24))
        return min(config.res_rated_kw,wind_ideal_kw(config.res_rho,config.res_radius_m,wind,config.res_cp))
    raise ValueError('Unknown plant')


def iterate_synthetic(kind: str, config: ScreeningConfig, from_step: int = 0) -> Iterator[dict]:
    """Pure deterministic steps; restart from an index yields identical samples."""
    if kind not in ('HES','GES','RES'): raise ValueError('Unknown plant')
    max_steps=config.days*86400//config.step_s
    if type(from_step) is not int or not 0 <= from_step <= max_steps:
        raise ValueError('Invalid resume index')
    start=parse_utc(config.start_utc)
    for idx in range(from_step,max_steps):
        dt=start+timedelta(seconds=idx*config.step_s)
        power=_screening_kw(kind,idx*config.step_s,config)
        yield {'step_index':idx,'utc':dt.isoformat(), 'power_kw':round(power,9),
               'energy_kwh':round(power*config.step_s/3600,9),
               'source_kind':'SYNTHETIC_SCREENING_NOT_OEM'}


def run_into_store(store, session_id: str, config: ScreeningConfig, *, limit: int | None = None) -> dict:
    """Append missing contiguous steps to SQLite, without duplicating after restart.

    Single process writer intended. SQLite foreign key and uniqueness protect integrity.
    """
    session = store.get(session_id)
    if session['plant'] not in ('HES','GES','RES') or session['step_s']!=config.step_s or parse_utc(session['start_utc'])!=parse_utc(config.start_utc):
        raise ValueError('Session configuration mismatch')
    # Restarting with changed area, Cp, days, wind parameters, etc. is forbidden:
    # otherwise one persisted time series could silently mix multiple models.
    store.bind_model_config(session_id, asdict(config))
    start_idx=len(session['samples'])
    remaining= config.days*86400//config.step_s - start_idx
    if remaining<0 or limit is not None and (type(limit) is not int or limit < 0):
        raise ValueError('Invalid limit or existing length')
    for item in iterate_synthetic(session['plant'],config,from_step=start_idx):
        if limit is not None and item['step_index']-start_idx >= limit: break
        store.add(session_id,item['step_index'],item['power_kw'])
    return store.get(session_id)
