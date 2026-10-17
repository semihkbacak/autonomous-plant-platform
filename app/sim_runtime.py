"""Local, synthetic, in-memory GES/RES simulation sessions.

Neither external network connections nor PLC/SCADA device adapters are used.
History databases are not opened for writing. Each session is capped at 96
15-minute intervals. The HES engine remains owned by app.main.
"""
from __future__ import annotations

from collections import deque
from hashlib import sha256
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from math import cos, pi, sin, isfinite
from threading import RLock
from typing import Any


MODES = {
    'ges': ('NORMAL', 'GRID_LOSS', 'ESTOP', 'FAULT', 'LOW_LIGHT', 'CURTAIL_50'),
    'res': ('NORMAL', 'GRID_LOSS', 'ESTOP', 'FAULT', 'LOW_WIND', 'HIGH_WIND', 'WAKE', 'CURTAIL_50'),
}


class SessionError(Exception):
    """Invalid state transition or scenario configuration."""


class _Session:
    def __init__(self, plant: str):
        self.plant = plant
        self._lock = RLock()
        self.running = False
        self.mode = 'NORMAL'
        self.index = 0
        self.last_power_kw = 0.0
        self.energy_kwh = 0.0
        self.last_end_utc: str | None = None
        self.last_units: list[dict] = []
        self.last_conditions: dict = {}
        self.power_series: deque[dict] = deque(maxlen=96)
        self.events: deque[dict] = deque(maxlen=50)
        self.error: str | None = None
        self._replay_trace: list[dict] = []
        self._engine: Any = None
        self._inputs: list[Any] | None = None

    def _prepare(self) -> None:
        raise NotImplementedError

    def _compute(self, index: int) -> dict:
        raise NotImplementedError

    def status(self) -> dict:
        with self._lock:
            return {
                'plant': self.plant.upper(),
                'scope': 'SYNTHETIC_IN_MEMORY_NO_OT',
                'running': self.running,
                'mode': self.mode,
                'available_modes': list(MODES[self.plant]),
                'intervals': self.index,
                'max_intervals': 96,
                'last_power_kw': self.last_power_kw,
                'energy_kwh': self.energy_kwh,
                'last_end_utc': self.last_end_utc,
                'units': list(self.last_units),
                'conditions': dict(self.last_conditions),
                'power_series': list(self.power_series),
                'events': list(self.events),
                'error': self.error,
                'historian_written': False,
            }

    def _event(self, name: str) -> None:
        self.events.append({'interval': self.index, 'event': name})

    def start(self) -> dict:
        with self._lock:
            if self.error is not None:
                raise SessionError('Model error latched; reset required')
            if self.index >= 96:
                raise SessionError('Day finished; use reset before starting')
            if self._engine is None:
                self._prepare()
            self.running = True
            self.error = None
            self._event('START')
            return self.status()

    def pause(self) -> dict:
        with self._lock:
            self.running = False
            self._event('PAUSE')
            return self.status()

    def reset(self) -> dict:
        with self._lock:
            self.running = False
            self.mode = 'NORMAL'
            self.index = 0
            self.last_power_kw = 0.0
            self.energy_kwh = 0.0
            self.last_end_utc = None
            self.last_units = []
            self.last_conditions = {}
            self.power_series.clear()
            self._engine = None
            self._inputs = None
            self.error = None
            self._replay_trace.clear()
            self.events.clear()
            self._event('RESET')
            return self.status()

    def configure(self, mode: str) -> dict:
        with self._lock:
            if mode not in MODES[self.plant]:
                raise SessionError('Unsupported synthetic scenario mode')
            self.mode = mode
            self._event('MODE_' + mode)
            return self.status()

    def step(self) -> dict:
        with self._lock:
            if self.index >= 96:
                raise SessionError('Day finished; reset before another step')
            if self._engine is None:
                self._prepare()
            try:
                report = self._compute(self.index)
                kw = report['power_kw']
                energy = report['energy_kwh']
                if not all(isfinite(v) and v >= 0 for v in (kw, energy)):
                    raise ValueError('Invalid simulation energy')
                self.last_power_kw = kw
                self.energy_kwh += energy
                self.last_end_utc = report['end_utc']
                self.last_units = report['units']
                self.last_conditions = dict(report.get('conditions', {}))
                self.power_series.append({'end_utc': report['end_utc'], 'power_kw': kw})
                report_digest = sha256(json.dumps(report, sort_keys=True, default=str,
                                  separators=(',',':'), allow_nan=False).encode('utf-8')).hexdigest()
                self._replay_trace.append({'mode': self.mode, 'sha256': report_digest})
                self.index += 1
                if self.index == 96:
                    self.running = False
                    self._event('DAY_COMPLETED')
                return self.status()
            except Exception as exc:
                self.running = False
                self.error = type(exc).__name__
                self._event('MODEL_ERROR')
                raise

    def export_replay(self) -> bytes:
        """Exact synthetic history for deterministic rehydration, not physical state."""
        with self._lock:
            if self.error is not None:
                raise SessionError('Error-latched live session requires reset; cannot guarantee replay')
            payload = {'schema': 1, 'scope': 'SYNTHETIC_REPLAY_NO_FIELD_IO',
                       'plant': self.plant, 'mode': self.mode, 'running': self.running,
                       'trace': list(self._replay_trace), 'status': self.status()}
            raw=json.dumps(payload,sort_keys=True,default=str,separators=(',',':'),allow_nan=False).encode('utf-8')
            if len(raw)>200_000:raise ValueError('Replay is too large')
            return json.dumps({'payload':payload,'sha256':sha256(raw).hexdigest()},
                              sort_keys=True,default=str,separators=(',',':')).encode('utf-8')

    @classmethod
    def import_replay(cls, raw: bytes):
        """Replay every prior mode + physical simulation step; reject any drift."""
        if not isinstance(raw, bytes) or len(raw)>220_000 or not raw:
            raise ValueError('Invalid live replay size')
        try:
            doc=json.loads(raw)
            p=doc['payload']
            encoded=json.dumps(p,sort_keys=True,default=str,separators=(',',':'),allow_nan=False).encode('utf-8')
            if sha256(encoded).hexdigest()!=doc['sha256']:
                raise ValueError('Replay digest invalid')
            if p['schema']!=1 or p['scope']!='SYNTHETIC_REPLAY_NO_FIELD_IO':
                raise ValueError('Unknown live runtime replay version')
            target=cls()
            if target.plant!=p['plant'] or p['mode'] not in MODES[target.plant]:
                raise ValueError('Incorrect simulator type or mode')
            trace=p['trace']
            if not isinstance(trace,list) or len(trace)>96:
                raise ValueError('Invalid replay history')
            for item in trace:
                if item['mode'] not in MODES[target.plant]:
                    raise ValueError('Unsupported replay mode')
                target.mode=item['mode']
                target.step()
                if target._replay_trace[-1]!=item:
                    raise ValueError('Model changed; exact replay cannot be guaranteed')
            target.mode=p['mode']
            state=p['status']
            if state['intervals']!=target.index or state['last_power_kw']!=target.last_power_kw \
                or state['energy_kwh']!=target.energy_kwh or state['units']!=target.last_units \
                or state['last_end_utc']!=target.last_end_utc or state['error'] is not None:
                raise ValueError('Synthetic replay result mismatch')
            if type(p['running'])!=bool or p['running']!=state['running']:
                raise ValueError('Invalid replay running flag')
            target.running=p['running']
            if not isinstance(state['events'],list) or len(state['events'])>50:
                raise ValueError('Invalid event history')
            target.events=deque(state['events'],maxlen=50)
            if target.status()!=state:
                raise ValueError('Synthetic replay did not reproduce the recorded state')
            return target
        except (KeyError,IndexError,TypeError,ValueError,SessionError) as exc:
            raise ValueError('Corrupt/incompatible synthetic runtime checkpoint') from exc

    def auto_step(self) -> None:
        with self._lock:
            if self.running:
                try:
                    self.step()
                except Exception:
                    # The state captures an error; never crash the HES clock.
                    pass


class SolarSession(_Session):
    def __init__(self):
        super().__init__('ges')

    def _prepare(self) -> None:
        # Heavy imports are intentionally lazy, so docs and unrelated REST APIs
        # do not require weather generation or a GES calculation on startup.
        from demo_ges_integrated_v04 import build_integrated_demo_pipeline
        from simulator.solar.solar_stress import make_stress_intervals
        from simulator.solar.solar_timeseries import SolarTimeSeriesSimulator
        pipeline = build_integrated_demo_pipeline()
        inputs = make_stress_intervals(1)
        engine = SolarTimeSeriesSimulator(pipeline)
        self._engine = engine
        self._inputs = inputs

    def advance_to_daylight(self) -> dict:
        """Fast-forward SYNTHETIC weather only, never a real-world clock."""
        with self._lock:
            for _ in range(48):
                if self.index >= 96 or self.last_conditions.get('irradiance_ghi_w_m2', 0) >= 40:
                    break
                self.step()
            return self.status()

    def _compute(self, index: int) -> dict:
        item = self._inputs[index]
        if self.mode == 'LOW_LIGHT':
            irr = item.weather.irradiance
            weather = replace(item.weather, irradiance=replace(
                irr,
                ghi_w_m2=irr.ghi_w_m2 * .05,
                dni_w_m2=irr.dni_w_m2 * .05,
                dhi_w_m2=irr.dhi_w_m2 * .05,
            ))
        else:
            weather = item.weather
        item = replace(
            item,
            weather=weather,
            grid_available=self.mode != 'GRID_LOSS',
            emergency_stop=self.mode == 'ESTOP',
            fault_inverter_ids=frozenset({'INV_1'}) if self.mode == 'FAULT' else frozenset(),
            requested_target_kw=5.0 if self.mode == 'CURTAIL_50' else None,
        )
        result = self._engine.step(item)
        return {
            'power_kw': result.dispatched_power_kw,
            'energy_kwh': result.interval_energy_kwh,
            'end_utc': result.end_utc.isoformat(),
            'units': [
                {'id': x.inverter_id, 'kw': x.ac_dispatched_kw, 'status': x.status}
                for x in result.inverter_results
            ],
            'conditions': {
                'irradiance_ghi_w_m2': weather.irradiance.ghi_w_m2,
                'ambient_temperature_c': weather.ambient_temperature_c,
                'wind_speed_m_s': weather.wind_speed_m_s,
                'grid_available': item.grid_available,
                'source': 'SYNTHETIC_PV_INVERTER_MPPT',
            },
        }


class WindSession(_Session):
    def __init__(self):
        super().__init__('res')

    def _prepare(self) -> None:
        from simulator.wind_suite import default_farm
        self._engine = default_farm()

    def _compute(self, index: int) -> dict:
        from simulator.wind_physics import WindWeather, WindControl
        phase = index / 96.0
        wind = max(0.0, 7.0 + 1.9 * sin(2 * pi * phase))
        if self.mode == 'LOW_WIND':
            wind = 1.0
        elif self.mode == 'HIGH_WIND':
            wind = 28.0
        weather = WindWeather(
            datetime(2026, 1, 1, tzinfo=timezone.utc)
            + timedelta(minutes=15 * (index + 1)),
            wind,
            270 if self.mode == 'WAKE' else 0,
        )
        control = WindControl(
            grid_available=self.mode != 'GRID_LOSS',
            emergency_stop=self.mode == 'ESTOP',
            fault_ids=frozenset({'WT_1'}) if self.mode == 'FAULT' else frozenset(),
            target_kw=800.0 if self.mode == 'CURTAIL_50' else None,
        )
        result = self._engine.step(weather, control)
        return {
            'power_kw': result.farm_dispatched_kw,
            'energy_kwh': result.energy_kwh,
            'end_utc': result.end_utc.isoformat(),
            'units': [
                {'id': x.turbine_id, 'kw': x.dispatched_kw, 'status': x.status}
                for x in result.turbines
            ],
            'conditions': {
                'wind_speed_m_s': wind,
                'wind_direction_deg': weather.from_direction_deg,
                'grid_available': control.grid_available,
                'source': 'SYNTHETIC_WIND_FARM',
            },
        }


class SimulatorSessions:
    def __init__(self):
        self.ges = SolarSession()
        self.res = WindSession()
        self._clock_counter = 0

    def session(self, plant: str) -> _Session:
        if plant not in ('ges', 'res'):
            raise SessionError('Unknown simulator')
        return getattr(self, plant)

    def export_replay(self) -> bytes:
        """Exact synthetic history for deterministic rehydration, not physical state."""
        with self._lock:
            if self.error is not None:
                raise SessionError('Error-latched live session requires reset; cannot guarantee replay')
            payload = {'schema': 1, 'scope': 'SYNTHETIC_REPLAY_NO_FIELD_IO',
                       'plant': self.plant, 'mode': self.mode, 'running': self.running,
                       'trace': list(self._replay_trace), 'status': self.status()}
            raw=json.dumps(payload,sort_keys=True,default=str,separators=(',',':'),allow_nan=False).encode('utf-8')
            if len(raw)>200_000:raise ValueError('Replay is too large')
            return json.dumps({'payload':payload,'sha256':sha256(raw).hexdigest()},
                              sort_keys=True,default=str,separators=(',',':')).encode('utf-8')

    @classmethod
    def import_replay(cls, raw: bytes):
        """Replay every prior mode + physical simulation step; reject any drift."""
        if not isinstance(raw, bytes) or len(raw)>220_000 or not raw:
            raise ValueError('Invalid live replay size')
        try:
            doc=json.loads(raw)
            p=doc['payload']
            encoded=json.dumps(p,sort_keys=True,default=str,separators=(',',':'),allow_nan=False).encode('utf-8')
            if sha256(encoded).hexdigest()!=doc['sha256']:
                raise ValueError('Replay digest invalid')
            if p['schema']!=1 or p['scope']!='SYNTHETIC_REPLAY_NO_FIELD_IO':
                raise ValueError('Unknown live runtime replay version')
            target=cls()
            if target.plant!=p['plant'] or p['mode'] not in MODES[target.plant]:
                raise ValueError('Incorrect simulator type or mode')
            trace=p['trace']
            if not isinstance(trace,list) or len(trace)>96:
                raise ValueError('Invalid replay history')
            for item in trace:
                if item['mode'] not in MODES[target.plant]:
                    raise ValueError('Unsupported replay mode')
                target.mode=item['mode']
                target.step()
                if target._replay_trace[-1]!=item:
                    raise ValueError('Model changed; exact replay cannot be guaranteed')
            target.mode=p['mode']
            state=p['status']
            if state['intervals']!=target.index or state['last_power_kw']!=target.last_power_kw \
                or state['energy_kwh']!=target.energy_kwh or state['units']!=target.last_units \
                or state['last_end_utc']!=target.last_end_utc or state['error'] is not None:
                raise ValueError('Synthetic replay result mismatch')
            if type(p['running'])!=bool or p['running']!=state['running']:
                raise ValueError('Invalid replay running flag')
            target.running=p['running']
            if not isinstance(state['events'],list) or len(state['events'])>50:
                raise ValueError('Invalid event history')
            target.events=deque(state['events'],maxlen=50)
            if target.status()!=state:
                raise ValueError('Synthetic replay did not reproduce the recorded state')
            return target
        except (KeyError,IndexError,TypeError,ValueError,SessionError) as exc:
            raise ValueError('Corrupt/incompatible synthetic runtime checkpoint') from exc

    def auto_step(self) -> None:
        self._clock_counter += 1
        # The HES clock ticks every second. Advance GES/RES by 15 simulated
        # minutes every two wall-clock seconds while their sessions run.
        if self._clock_counter % 2 == 0:
            self.ges.auto_step()
            self.res.auto_step()
