"""Transparent, bounded SYNTHETIC research physics; not OEM or site calibrated.

All state is JSON-safe and determined by the scenario, step index, and prior
state; no real process connection, field actuator, live weather or hidden RNG.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from math import cos, exp, isfinite, log, pi, sin, sqrt

SCOPE = 'SYNTHETIC_RESEARCH_NO_OT'
VERSION = 'stage2-5-synthetic-2026-10'


def clamp(x: float, lo: float, hi: float) -> float:
    x = float(x)
    if not isfinite(x):
        raise ValueError('Nonfinite physical input')
    return max(lo, min(hi, x))


def check_nonnegative(**items):
    for name, value in items.items():
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value) or value < 0:
            raise ValueError(f'Invalid nonnegative {name}')


def _segment_voltage(current: float, photocurrent: float, temperature_c: float) -> float:
    """Illustrative diode/bypass approximation for one PV substring (V)."""
    if photocurrent <= 1e-8 or current >= photocurrent:
        return -0.45  # bypass diode conducts; no negative system power
    thermal = (273.15 + temperature_c) / 298.15
    a = 1.14 * thermal
    saturation = 1.0e-8 * exp(clamp((temperature_c - 25) / 18.0, -10, 10))
    # Iterative shunt-current correction within the single-diode family.
    v = 0.0
    for _ in range(4):
        shunt_current = max(0.0, v) / 550.0
        diode_current = max(1e-10, photocurrent - current - shunt_current)
        v = a * log(1 + diode_current / saturation) - 0.12 * current
    return max(-0.45, v)


def iv_curve(irradiance_wm2: float, temp_c: float, shade: tuple[tuple[float, ...], ...], samples: int = 64) -> list[dict]:
    """Parallel strings of three bypass-protected SERIES substrings.

    Exact string I/V points are interpolated onto a shared terminal voltage.
    Inputs and parameters are clearly SYNTHETIC and not fitted OEM curves.
    """
    check_nonnegative(irradiance_wm2=irradiance_wm2)
    if not -40 <= temp_c <= 110 or not 24 <= samples <= 256:
        raise ValueError('Invalid PV temperature or sample count')
    if not shade or len(shade) > 8 or any(len(s) != 3 for s in shade):
        raise ValueError('Expected 1..8 parallel strings of three PV substrings')
    for s in shade:
        for f in s:
            if not 0 <= f <= 1 or not isfinite(f):
                raise ValueError('Shading factors must be finite 0..1')
    if irradiance_wm2 <= 1e-6:
        return [{'v': 0.0, 'i': 0.0, 'p': 0.0}]
    strings = []
    high_v = 0.0
    for factors in shade:
        currents = [max(0.0, 9.2 * irradiance_wm2 / 1000 * f * (1+0.00048*(temp_c-25))) for f in factors]
        high_i = max(currents)
        path = []
        for k in range(samples + 1):
            amp = high_i * k / samples
            volt = sum(_segment_voltage(amp, photo, temp_c) for photo in currents)
            path.append((max(0.0, volt), amp))
        # Sort by V so interpolation across (V,I) can be monotonic.
        path.sort(key=lambda t: t[0])
        high_v = max(high_v, path[-1][0])
        strings.append(path)
    result = []
    for k in range(samples + 1):
        voltage = high_v * k / samples
        parallel_current = 0.0
        for path in strings:
            if voltage >= path[-1][0]:
                continue
            for j in range(1, len(path)):
                (v0, i0), (v1, i1) = path[j-1], path[j]
                if v0 <= voltage <= v1 and v1 > v0:
                    parallel_current += max(0.0, i0 + (i1-i0)*(voltage-v0)/(v1-v0))
                    break
        result.append({'v': round(voltage, 4), 'i': round(parallel_current, 5),
                       'p': round(voltage*parallel_current, 5)})
    return result


@dataclass
class PVState:
    voltage_v: float = 44.0
    last_power_w: float = 0.0
    last_voltage_v: float = 44.0
    direction: int = 1
    cell_temperature_c: float = 25.0


class SolarPhysics:
    def __init__(self, state: PVState | None = None):
        self.state = state or PVState()

    @staticmethod
    def _at(curve, v):
        if len(curve) == 1: return 0.0, 0.0
        idx = min(range(len(curve)), key=lambda i: abs(curve[i]['v'] - v))
        return curve[idx]['p'], curve[idx]['i']

    def advance(self, irradiance_wm2: float, air_temp_c: float, shade=None, algorithm='INC_COND', fault='NONE'):
        if algorithm not in ('PO', 'INC_COND', 'GLOBAL'):
            raise ValueError('MPPT algorithm must be PO/INC_COND/GLOBAL')
        if fault not in ('NONE', 'GRID_LOSS', 'INVERTER_TRIP', 'HOT_INVERTER', 'STRING_OPEN'):
            raise ValueError('Unsupported PV fault')
        if shade is None: shade = ((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))
        if fault == 'STRING_OPEN':shade = shade[:1]
        cell_c = clamp(air_temp_c + 0.027 * irradiance_wm2, -30, 95)
        # First-order cell thermal response, 15 minute physical interval.
        self.state.cell_temperature_c += (cell_c - self.state.cell_temperature_c) * 0.65
        curve = iv_curve(irradiance_wm2, self.state.cell_temperature_c, shade)
        peak = max(curve, key=lambda r: r['p'])
        vmax = curve[-1]['v']
        voltage = clamp(self.state.voltage_v, 0, vmax)
        for _ in range(16):  # finite-speed controller substeps, not perfect instantaneous MPP
            p, amps = self._at(curve, voltage)
            step = max(0.12, vmax * 0.007)
            if algorithm == 'GLOBAL':
                voltage += clamp(peak['v'] - voltage, -1.5*step, 1.5*step)
            elif algorithm == 'PO':
                if p + 1e-9 < self.state.last_power_w:
                    self.state.direction *= -1
                voltage += self.state.direction * step
            else:  # Incremental conductance: sign of dP/dV ~ I + V*dI/dV
                _pplus, iplus = self._at(curve, min(vmax, voltage+step))
                _pminus, iminus = self._at(curve, max(0.0, voltage-step))
                slope = amps + voltage * (iplus-iminus) / max(1e-6, 2*step)
                voltage += step if slope > 0.02 else (-step if slope < -0.02 else 0.0)
            voltage = clamp(voltage, 0, vmax)
            self.state.last_power_w = p
        dc_w, amps = self._at(curve, voltage)
        # Two small research PV strings, inverter rated 1.0kW; intentionally not a utility-scale plant.
        dc_w = min(1100.0, dc_w)
        hot_derate = 0.6 if fault == 'HOT_INVERTER' else 1.0
        thermal_derate = clamp(1 - 0.008 * max(0, self.state.cell_temperature_c - 58), 0.6, 1)
        efficiency = clamp(0.965 - 0.055*(1-min(1.0,dc_w/1000))**2, 0, 1)
        ac_w = min(1000.0 * hot_derate * thermal_derate, dc_w * efficiency)
        if fault in ('GRID_LOSS', 'INVERTER_TRIP'): ac_w = 0
        self.state.voltage_v = voltage
        return {'plant':'GES','power_kw':round(ac_w/1000,6),'energy_kwh':round(ac_w/4000,6),
                'dc_kw':round(dc_w/1000,6),'inverter_efficiency':round(efficiency,4),
                'voltage_v':round(voltage,3),'current_a':round(amps,3),
                'global_mpp_kw':round(peak['p']/1000,6),'cell_temperature_c':round(self.state.cell_temperature_c,2),
                'irradiance_wm2':irradiance_wm2,'mppt':algorithm,'fault':fault,
                'iv_curve':curve,'scope':SCOPE}

    def checkpoint(self):return asdict(self.state)
    @classmethod
    def recover(cls, doc):return cls(PVState(**doc))


@dataclass
class WindState:
    rotor_rad_s: float = 1.15
    pitch_deg: float = 2.0
    yaw_deg: float = 0.0
    last_power_kw: float = 0.0


def cp_approx(tsr: float, pitch_deg: float) -> float:
    """Conventional parametric Cp(lambda,beta) envelope, never a certified curve."""
    tsr = clamp(tsr, 0.05, 30)
    pitch_deg = clamp(pitch_deg, 0, 90)
    den = 1/(tsr + 0.08*pitch_deg) - 0.035/(pitch_deg**3+1)
    if den <= 1e-7:return 0.0
    lam_i = 1/den
    cp = 0.5176*(116/lam_i-0.4*pitch_deg-5)*exp(clamp(-21/lam_i, -60, 0)) + 0.0068*tsr
    return clamp(cp,0.0,0.50)  # under Betz limit 16/27


class WindPhysics:
    def __init__(self, states=None):
        self.states = [WindState(**s) for s in states] if states is not None else [WindState(),WindState()]
        if len(self.states) != 2:raise ValueError('Two synthetic wind turbines required')

    def advance(self, step_index:int, wind_ms:float, wind_direction_deg:float=0, fault:str='NONE'):
        check_nonnegative(wind_ms=wind_ms)
        if fault not in ('NONE','PITCH_STUCK','YAW_STUCK','BRAKE','HIGH_WIND','GRID_LOSS'):
            raise ValueError('Unsupported wind fault')
        rho, radius, rated_kw = 1.225, 24.0, 400.0
        swept = pi*radius**2
        outputs=[]
        e_kwh=0.0
        # Deterministic 10-second substeps across 15 minutes.
        for sub in range(90):
            turb = clamp(wind_ms*(1 + 0.09*sin(0.12*step_index+0.38*sub)
                                   + 0.04*sin(0.89*step_index+0.17*sub)),0,38)
            downstream = turb
            for t,state in enumerate(self.states):
                local = turb if t==0 else downstream
                yaw_target = wind_direction_deg
                if fault != 'YAW_STUCK':
                    mismatch = (yaw_target - state.yaw_deg + 180)%360 - 180
                    state.yaw_deg += clamp(mismatch,-0.5,0.5)  # 0.05 deg/s
                yaw_error = ((wind_direction_deg-state.yaw_deg+180)%360)-180
                effective_v = local * abs(cos(yaw_error*pi/180))**1.5
                target_pitch = 20.0 if effective_v > 14 else (4.0 if effective_v > 11 else 1.0)
                if fault in ('BRAKE','HIGH_WIND') or effective_v>=25:target_pitch=75.0
                if fault!='PITCH_STUCK':
                    state.pitch_deg += clamp(target_pitch-state.pitch_deg,-1.5,1.5)
                tsr = state.rotor_rad_s*radius/max(effective_v,0.1)
                cp=cp_approx(tsr,state.pitch_deg)
                aero_kw=0.5*rho*swept*effective_v**3*cp/1000
                # Torque imbalance on rotor moment of inertia, with basic generator load.
                turbine_torque = 1000*aero_kw/max(0.3,state.rotor_rad_s)
                electrical_ref_kw = min(rated_kw, aero_kw*0.90)
                generator_torque = 1000*electrical_ref_kw/max(0.4,state.rotor_rad_s)
                inertia = 160_000.0
                acceleration=(turbine_torque-generator_torque-250*state.rotor_rad_s)/inertia
                state.rotor_rad_s=clamp(state.rotor_rad_s+acceleration*10,0.15,3.5)
                power_kw = max(0.0,min(rated_kw, electrical_ref_kw))
                if fault in ('BRAKE','HIGH_WIND','GRID_LOSS') or effective_v<3 or effective_v>25:
                    power_kw=0.0
                    if fault in ('BRAKE','HIGH_WIND'):state.rotor_rad_s=max(0.15,state.rotor_rad_s-0.08)
                state.last_power_kw=power_kw
                e_kwh += power_kw *10/3600
                if t==0:
                    # Jensen-type deficit for downwind turbine with D=48m and x=240m.
                    ct = 0.75 if state.pitch_deg < 20 else 0.2
                    deficit = (1 - sqrt(1-ct))/(1+2*0.045*240/48)**2
                    downstream=turb*(1-deficit)
        for index,state in enumerate(self.states):
            outputs.append({'id':f'WT_{index+1}','power_kw':round(state.last_power_kw,3),
                            'rotor_rpm':round(state.rotor_rad_s*60/(2*pi),2),
                            'pitch_deg':round(state.pitch_deg,2),'yaw_deg':round(state.yaw_deg,2)})
        return {'plant':'RES','power_kw':round(sum(x['power_kw'] for x in outputs),5),
                'energy_kwh':round(e_kwh,5),'wind_ms':wind_ms,'wind_direction_deg':wind_direction_deg,
                'turbines':outputs,'fault':fault,'scope':SCOPE}

    def checkpoint(self):return [asdict(x) for x in self.states]
    @classmethod
    def recover(cls, data):return cls(data)


@dataclass
class HydroState:
    reservoir_m3:float=400_000.0
    nozzle_flow_m3s:float=3.0
    runner_rad_s:float=62.83
    integrator:float=0.0
    grid_frequency_hz:float=50.0
    voltage_pu:float=1.0


class HydroPhysics:
    def __init__(self,state:HydroState|None=None):self.state=state or HydroState()

    def advance(self, demand_kw:float, inflow_m3s:float=8.0, fault:str='NONE'):
        check_nonnegative(demand_kw=demand_kw,inflow_m3s=inflow_m3s)
        if fault not in ('NONE','NOZZLE_STUCK','LOAD_REJECTION','LOW_RESERVOIR','GRID_LOSS'):
            raise ValueError('Unsupported hydro fault')
        rho,g,wave=1000.0,9.81,1050.0
        energy=0.0
        max_surge_bar=0.0
        env_release=0.8
        for _ in range(90):
            state=self.state
            effective_storage=state.reservoir_m3
            head_m=clamp(130.0+(effective_storage-400_000)/110_000,95,145)
            measured_kw=rho*g*max(0,state.nozzle_flow_m3s)*head_m*.87/1000
            error=demand_kw-measured_kw
            state.integrator=clamp(state.integrator+error*10, -200_000, 200_000)
            target_flow = clamp(demand_kw*1000/(rho*g*head_m*.87) + error*0.000045+state.integrator*0.0000006,0,12)
            if fault in ('LOAD_REJECTION','GRID_LOSS'):target_flow=0.0
            if fault=='LOW_RESERVOIR':target_flow=min(target_flow,0.8)
            old_flow=state.nozzle_flow_m3s
            if fault!='NOZZLE_STUCK':
                state.nozzle_flow_m3s += clamp((target_flow-old_flow)*10/85, -0.5,0.5)
            state.nozzle_flow_m3s=clamp(state.nozzle_flow_m3s,0,12)
            # Local illustrative Joukowsky envelope, not a pipe MOC solution.
            pipe_area=pi*1.5**2/4
            surge_bar = rho*wave*abs(state.nozzle_flow_m3s-old_flow)/pipe_area/100_000
            max_surge_bar=max(max_surge_bar,surge_bar)
            turbine_kw=rho*g*state.nozzle_flow_m3s*head_m*.87/1000
            omega_ref=62.83
            mechanical_torque=turbine_kw*1000/max(state.runner_rad_s,5)
            grid_torque=min(190_000.0, demand_kw*1000/max(state.runner_rad_s,5))
            accel=(mechanical_torque-grid_torque-450*(state.runner_rad_s-omega_ref))/80_000
            state.runner_rad_s=clamp(state.runner_rad_s+accel*10,40,93)
            state.grid_frequency_hz=clamp(50*state.runner_rad_s/omega_ref,30,75)
            state.voltage_pu+=clamp((1.0-state.voltage_pu)*0.11,-0.1,0.1)
            # Electrical production cannot exceed turbine mechanical power.
            electric_kw=turbine_kw*.95
            if fault in ('GRID_LOSS','LOAD_REJECTION'):electric_kw=0
            energy += electric_kw*10/3600
            state.reservoir_m3=clamp(state.reservoir_m3+10*(inflow_m3s-env_release-state.nozzle_flow_m3s),5000,750000)
        return {'plant':'HES','power_kw':round(energy*4,5),'energy_kwh':round(energy,5),
                'net_head_m':round(130+(self.state.reservoir_m3-400000)/110000,3),
                'nozzle_m3s':round(self.state.nozzle_flow_m3s,4),
                'reservoir_m3':round(self.state.reservoir_m3,2),
                'frequency_hz':round(self.state.grid_frequency_hz,4),
                'voltage_pu':round(self.state.voltage_pu,4),
                'max_joukowsky_bar':round(max_surge_bar,5),
                'runner_rpm':round(self.state.runner_rad_s*60/(2*pi),2),
                'fault':fault,'scope':SCOPE}

    def checkpoint(self):return asdict(self.state)
    @classmethod
    def recover(cls,data):return cls(HydroState(**data))
