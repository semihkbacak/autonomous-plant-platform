"""Deterministic 15-minute three-plant controller over the EXISTING simulators.

HES is integrated at its native 1-second step; GES/RES at their native
15-minute step. Weather/production inputs are SYNTHETIC; every new day
repeats a demo day with fresh GES/RES engine state. These are not site data.
"""
from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from math import isfinite
from typing import Callable

from simulator.hydro import HydroPlantSimulator
from simulator.hydro_checkpoint import encode_checkpoint, decode_checkpoint
from app.sim_runtime import SolarSession, WindSession

SCOPE = 'SYNTHETIC_THREE_PLANT_NO_OT'
MODEL_REVISION = 'stage1-legacy-hes-ges-res-1'


def canonical(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


@dataclass(frozen=True)
class ClockConfig:
    start_utc: str
    days: int = 1
    step_seconds: int = 900

    def __post_init__(self):
        if type(self.days) is not int or not 1 <= self.days <= 31:
            raise ValueError('days must be 1..31')
        if type(self.step_seconds) is not int or self.step_seconds != 900:
            raise ValueError('native GES/RES steps require exactly 900 seconds')
        try:
            dt = datetime.fromisoformat(self.start_utc.replace('Z', '+00:00'))
        except (TypeError, ValueError) as exc:
            raise ValueError('start_utc must be ISO 8601 UTC') from exc
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError('start_utc must specify UTC offset')
        if dt.time().replace(tzinfo=None) != datetime.min.time():
            raise ValueError('start_utc must be 00:00:00 UTC for daily synthetic weather alignment')

    @property
    def start(self) -> datetime:
        return datetime.fromisoformat(self.start_utc.replace('Z','+00:00')).astimezone(timezone.utc)

    @property
    def maximum_steps(self) -> int:
        return self.days * 96


class ThreePlantEngine:
    """Independent simulated portfolio, never uses global app.main hydro clock."""

    def __init__(self, config: ClockConfig,
                 solar_factory: Callable[[], SolarSession] = SolarSession,
                 wind_factory: Callable[[], WindSession] = WindSession):
        self.config = config
        self.solar_factory = solar_factory
        self.wind_factory = wind_factory
        self.hydro = HydroPlantSimulator()
        self.hydro.set_auto_tick(False)
        for unit_id in ('UNIT_1', 'UNIT_2'):
            answer = self.hydro.request_start(unit_id)
            if not answer.accepted:
                raise ValueError(f'Cannot initialize synthetic HES unit: {unit_id}')
        self.solar = solar_factory()
        self.wind = wind_factory()
        self.mode = {'GES':'NORMAL', 'RES':'NORMAL'}
        self.index = 0
        self.totals = {'HES': 0.0, 'GES': 0.0, 'RES': 0.0}
        self.latest = {}

    def _new_day(self):
        self.solar = self.solar_factory()
        self.wind = self.wind_factory()
        self.solar.configure(self.mode['GES'])
        self.wind.configure(self.mode['RES'])

    def advance(self, requests: dict | None = None) -> list[dict]:
        """Complete one *common* UTC slot; never silently skip a plant."""
        if self.index >= self.config.maximum_steps:
            raise ValueError('Multi-day run complete')
        if self.index and self.index % 96 == 0:
            self._new_day()
        start = self.config.start + timedelta(seconds=self.index * 900)
        end = start + timedelta(seconds=900)
        # Native HES tick really represents one simulated second; integrate
        # every power sample to kWh, not last-point power * 15 min.
        hes_kwh = 0.0
        for _ in range(900):
            state = self.hydro.tick()
            hes_kwh += sum(u.active_power_mw * 1000 for u in state.units) / 3600
        hes_kw = hes_kwh * 4
        hes_units = [{'id':u.unit_id, 'kw':u.active_power_mw*1000,
                      'flow_m3_s':u.flow_m3_s,'turbine_efficiency':u.turbine_efficiency,
                      'generator_efficiency':u.generator_efficiency,
                      'status':u.status.value} for u in state.units]
        ges = self.solar.step()
        res = self.wind.step()
        # Session total kWh resets each synthetic day. Derive the *interval*
        # increment from the last status; do not use the portfolio sum.
        # Capture previous daily totals separately (stored on engine).
        ges_interval = ges['energy_kwh'] - getattr(self, '_solar_day_energy_before', 0.0)
        res_interval = res['energy_kwh'] - getattr(self, '_wind_day_energy_before', 0.0)
        self._solar_day_energy_before = ges['energy_kwh']
        self._wind_day_energy_before = res['energy_kwh']
        if self.index and self.index % 96 == 0:
            # At day rollover the newly prepared sessions started at zero.
            ges_interval = ges['energy_kwh']
            res_interval = res['energy_kwh']
        rows = []
        records = (
            ('HES', hes_kw, hes_kwh, hes_units, {'native_tick_s':1,'ticks_in_slot':900,'net_head_m':state.net_head_m,
                   'flow_m3_s':sum(u.flow_m3_s for u in state.units),
                   'source':'SYNTHETIC_HYDRO_TURBINE_GENERATOR'}),
            ('GES', ges['last_power_kw'], ges_interval, ges['units'], ges.get('conditions', {})),
            ('RES', res['last_power_kw'], res_interval, res['units'], res.get('conditions', {})),
        )
        from stage1.dispatch import dispatch_row
        for plant, kw, energy, units, conditions in records:
            if any(type(v) not in (float,int) or not isfinite(v) or v < -1e-8 for v in (kw,energy)):
                raise ValueError(f'Invalid {plant} synthetic power/energy')
            row={'step_index':self.index,'plant':plant,'utc_start':start.isoformat(),
                 'utc_end':end.isoformat(),'power_kw':float(kw),'energy_kwh':float(max(0.0,energy)),
                 'units':units,'conditions':conditions,'scope':SCOPE}
            if requests is not None and plant in requests:
                row=dispatch_row(row,requests[plant])
            self.totals[plant] += row['energy_kwh']
            row['total_kwh']=self.totals[plant]
            rows.append(row)
        self.latest = {r['plant']:r for r in rows}
        self.index += 1
        return rows

    def change_mode(self, plant: str, mode: str):
        if plant not in ('GES','RES'):
            raise ValueError('Only GES/RES demo scenario mode is configurable here')
        from app.sim_runtime import MODES
        if mode not in MODES[plant.lower()]:
            raise ValueError('Unknown synthetic mode')
        session = self.solar if plant == 'GES' else self.wind
        session.configure(mode)
        self.mode[plant] = mode

    def snapshot(self) -> bytes:
        doc = {'schema':1,'scope':SCOPE,'revision':MODEL_REVISION,'config':asdict(self.config),
               'step_index':self.index,'totals':self.totals,'latest':self.latest,'mode':self.mode,
               'solar_day_energy_before':getattr(self,'_solar_day_energy_before',0.0),
               'wind_day_energy_before':getattr(self,'_wind_day_energy_before',0.0),
               'hydro':b64encode(encode_checkpoint(self.hydro)).decode('ascii'),
               'solar':b64encode(self.solar.export_replay()).decode('ascii'),
               'wind':b64encode(self.wind.export_replay()).decode('ascii')}
        raw = canonical(doc)
        if len(raw) > 1_500_000:
            raise ValueError('Checkpoint size limit exceeded')
        return canonical({'payload':doc, 'sha256':sha256(raw).hexdigest()})

    @classmethod
    def recover(cls, raw: bytes, solar_factory=SolarSession, wind_factory=WindSession):
        if not raw or len(raw) > 1_700_000:
            raise ValueError('Missing or oversized checkpoint')
        try:
            doc = json.loads(raw)
            payload = doc['payload']
            if sha256(canonical(payload)).hexdigest() != doc['sha256']:
                raise ValueError('Snapshot checksum mismatch')
            if payload['schema'] != 1 or payload['scope'] != SCOPE or payload['revision'] != MODEL_REVISION:
                raise ValueError('Incompatible snapshot version')
            config = ClockConfig(**payload['config'])
            engine = cls(config, solar_factory, wind_factory)
            engine.index = payload['step_index']
            if type(engine.index) is not int or not 0 <= engine.index <= config.maximum_steps:
                raise ValueError('Invalid recovered clock index')
            engine.hydro = decode_checkpoint(b64decode(payload['hydro'], validate=True))
            engine.solar = solar_factory.import_replay(b64decode(payload['solar'], validate=True))
            engine.wind = wind_factory.import_replay(b64decode(payload['wind'], validate=True))
            engine.mode = payload['mode']
            engine.totals = payload['totals']
            engine.latest = payload['latest']
            engine._solar_day_energy_before = payload['solar_day_energy_before']
            engine._wind_day_energy_before = payload['wind_day_energy_before']
            for plant in ('HES','GES','RES'):
                t = engine.totals[plant]
                if type(t) not in (int,float) or not isfinite(t) or t < 0:
                    raise ValueError('Bad recovered energy')
            if engine.hydro.snapshot().simulation_time_s != engine.index * 900:
                raise ValueError('HES clock drift in recovered checkpoint')
            daily_steps = (engine.index - 1) % 96 + 1 if engine.index else 0
            if engine.solar.index != daily_steps or engine.wind.index != daily_steps:
                raise ValueError('GES/RES day clock drift in checkpoint')
            if engine.mode != {'GES':engine.solar.mode, 'RES':engine.wind.mode}:
                raise ValueError('Saved scenario mismatch')
            return engine
        except (KeyError, IndexError, TypeError, ValueError, UnicodeError) as exc:
            raise ValueError('Cannot recover incompatible/corrupt synthetic checkpoint') from exc
