"""Physical consistency screening grounded in hydropower, PV and wind literature.

Not official IEC procedures, turbine maps or protective controls.
"""
from __future__ import annotations
import math
from collections import defaultdict


def _bounded(label, value, low, high):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:
        raise ValueError('Nonfinite or out-of-range '+label)
    return float(value)


def hydro_efficiency_screen(power_kw, head_m, flow_m3_s, *, rho_kg_m3=1000.0):
    """P/(rho*g*Q*H); losses and reference plane must be verified in field."""
    p=_bounded('power_kw',power_kw,0,1e7)
    h=_bounded('head_m',head_m,0.01,2000)
    q=_bounded('flow_m3_s',flow_m3_s,0.00001,20000)
    rho=_bounded('rho_kg_m3',rho_kg_m3,500,1500)
    available_kw=rho*9.80665*q*h/1000
    eta=p/available_kw
    return {'hydraulic_input_kw':round(available_kw,5),
            'apparent_efficiency':round(eta,6),
            'physically_plausible':0<=eta<=1.0,
            'measurement_scope':'OBSERVATIONAL_ENERGY_BALANCE_NO_IEC_60041_COMPLIANCE',
            'measurement_plane_verified':False,'site_validated':False}


def solar_pr_screen(ac_energy_kwh, dc_stc_capacity_kw, poa_irradiation_kwh_m2):
    """Research PR proxy based on AC yield / STC yield at 1 kW/m².

    Irradiance and energy MUST span exactly the same observation window.
    Meter losses and uncertainty are external acceptance requirements.
    """
    energy=_bounded('ac_energy_kwh',ac_energy_kwh,0,1e12)
    capacity=_bounded('dc_stc_capacity_kw',dc_stc_capacity_kw,.001,1e7)
    poa=_bounded('poa_irradiation_kwh_m2',poa_irradiation_kwh_m2,.001,1e7)
    expected=capacity*poa
    pr=energy/expected
    return {'ac_performance_ratio_proxy':round(pr,6),
            'screening_plausible':pr<=1.25,
            'denominator_reference_kwh':round(expected,6),
            'measurement_scope':'RESEARCH_PR_PROXY_NOT_IEC_PV_PERFORMANCE_CERTIFICATION',
            'synchronized_meter_and_poa_data_verified':False,'site_validated':False}


def wind_bin_screen(points, *, bin_width_ms=1.0, min_bin_samples=3):
    """Descriptive equally spaced power curve bins, not IEC 61400-12-1 procedure."""
    width=_bounded('bin_width_ms',bin_width_ms,.5,3)
    if type(min_bin_samples) is not int or not 2<=min_bin_samples<=100:
        raise ValueError('Invalid bin minimum')
    if not isinstance(points,(list,tuple)) or not 6<=len(points)<=50000:
        raise ValueError('6..50000 wind/power pairs required')
    buckets=defaultdict(list)
    for point in points:
        if not isinstance(point,(tuple,list)) or len(point)!=2:raise ValueError('Expected (wind_m_s, power_kw) pairs')
        v=_bounded('wind_speed_m_s',point[0],0,80)
        p=_bounded('power_kw',point[1],0,1e7)
        idx=math.floor(v/width)
        buckets[idx].append(p)
    output=[]
    for idx, powers in sorted(buckets.items()):
        if len(powers)<min_bin_samples:continue
        mu=math.fsum(powers)/len(powers)
        sd=math.sqrt(math.fsum((p-mu)**2 for p in powers)/len(powers))
        output.append({'wind_bin_start_m_s':round(idx*width,5),
                       'wind_bin_end_m_s':round((idx+1)*width,5),
                       'sample_count':len(powers),
                       'mean_power_kw':round(mu,6),
                       'std_power_kw':round(sd,6)})
    if not output:raise ValueError('No sufficiently populated bins')
    return {'bins':output,'scope':'DESCRIPTIVE_BINS_NOT_IEC_61400_12_1_MEASUREMENT',
            'air_density_corrected':False,'site_validated':False}
