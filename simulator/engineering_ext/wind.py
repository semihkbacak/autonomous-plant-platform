"""Research-only wind pitch/yaw actuator proxy. No IEC mechanical loading."""
from __future__ import annotations
from dataclasses import dataclass
from math import cos, isfinite, radians


def _valid(name,x,lo,hi):
    if isinstance(x,bool) or not isinstance(x,(float,int)) or not isfinite(x) or not lo<=x<=hi:
        raise ValueError(f'Invalid {name}')
    return float(x)


@dataclass(frozen=True)
class ActuatorState:
    pitch_deg: float
    yaw_deg: float
    pitch_stuck: bool = False
    yaw_stuck: bool = False


def actuator_step(state: ActuatorState, target_pitch_deg: float, target_yaw_deg: float,
                  dt_s: float, pitch_rate_deg_s:float=2.0,
                  yaw_rate_deg_s:float=0.5) -> dict:
    pitch = _valid('pitch',state.pitch_deg,0,90)
    yaw = _valid('yaw',state.yaw_deg,-180,180)
    target_pitch = _valid('target_pitch',target_pitch_deg,0,90)
    target_yaw = _valid('target_yaw',target_yaw_deg,-180,180)
    dt = _valid('dt',dt_s,0.001,3600)
    pr = _valid('pitch_rate',pitch_rate_deg_s,0,100)
    yr = _valid('yaw_rate',yaw_rate_deg_s,0,100)
    def move(a,b,limit): return a + max(-limit,min(limit,b-a))
    delta_yaw = ((target_yaw-yaw+180) % 360)-180
    new_yaw = ((yaw+max(-yr*dt,min(yr*dt,delta_yaw))+180) % 360)-180
    next_pitch = pitch if state.pitch_stuck else move(pitch,target_pitch,pr*dt)
    next_yaw = yaw if state.yaw_stuck else new_yaw
    return {'pitch_deg':round(next_pitch,5), 'yaw_deg':round(next_yaw,5),
            'pitch_stuck':state.pitch_stuck,'yaw_stuck':state.yaw_stuck,
            'command_complete':abs(next_pitch-target_pitch)<1e-5 and
            abs(((next_yaw-target_yaw+180)%360)-180)<1e-5,
            'scope':'PITCH_YAW_RATE_LIMIT_PROXY_NOT_OEM_LOAD_MODEL'}


def yaw_loss_screen(power_kw:float, yaw_error_deg:float, exponent:float=1.88) -> dict:
    p = _valid('power_kw',power_kw,0,1e7)
    theta = _valid('yaw_error_deg',yaw_error_deg,-90,90)
    exp = _valid('exponent',exponent,1,5)
    corrected = p * max(0.0,cos(radians(theta)))**exp
    return {'screened_power_kw':round(corrected,6),
            'screened_loss_kw':round(p-corrected,6),
            'oem_validated':False,'structural_loads_validated':False,
            'scope':'EMPIRICAL_YAW_SCREEN_ONLY'}
