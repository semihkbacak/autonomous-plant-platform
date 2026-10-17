"""Transparent screening formulas; not OEM validated physics or protection."""
from __future__ import annotations
from math import isfinite, pi

def number(value,name,positive=False):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or (positive and value<=0):
        raise ValueError('Invalid '+name)
    return float(value)

def hydro_ideal_kw(flow_m3_s,head_m,efficiency):
    q=number(flow_m3_s,'flow');h=number(head_m,'head');e=number(efficiency,'efficiency')
    if min(q,h)<0 or not 0<=e<=1:raise ValueError('Out of range')
    return 9.81*q*h*e

def pv_ideal_kw(area_m2,irradiance_w_m2,efficiency):
    a=number(area_m2,'area');g=number(irradiance_w_m2,'irradiance');e=number(efficiency,'efficiency')
    if min(a,g)<0 or not 0<=e<=1:raise ValueError('Out of range')
    return a*g*e/1000

def wind_ideal_kw(air_density_kg_m3,rotor_radius_m,wind_m_s,cp):
    rho=number(air_density_kg_m3,'density',True);r=number(rotor_radius_m,'radius');v=number(wind_m_s,'wind');c=number(cp,'cp')
    if min(r,v,c)<0 or c>16/27:raise ValueError('Invalid ideal power coefficient/range')
    return .5*rho*pi*r*r*v**3*c/1000
