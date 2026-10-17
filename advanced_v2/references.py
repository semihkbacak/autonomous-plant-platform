"""Independent open-source / conservation references for synthetic research.

These comparisons do NOT validate the site, OEM curves, protection devices,
or physical controller. They test only selected idealized mathematical cases.
"""
from __future__ import annotations

from math import pi
from advanced_v2.physics import iv_curve,cp_approx


def pvlib_standard_irradiance_check():
    """Cross-check synthetic single-diode substrings against pvlib 0.16.1.

    Exactly 3 series substrings and 2 parallel strings at 1000 W/m2, 25 C;
    the same DECLARED synthetic diode coefficients, not a manufacturer fit.
    """
    try:
        from pvlib.pvsystem import singlediode
    except ImportError as exc:
        raise RuntimeError('pvlib is required for independent PV reference check') from exc
    parameters={'photocurrent':9.2,'saturation_current':1.0e-8,
                'resistance_series':0.12,'resistance_shunt':550.0,'nNsVth':1.14}
    reference=singlediode(**parameters)
    ref_power_w=float(reference['p_mp'])*3*2
    ours=max(item['p'] for item in iv_curve(1000,25,((1,1,1),(1,1,1))))
    deviation=abs(ours-ref_power_w)/ref_power_w
    return {'scope':'SYNTHETIC_COEFFICIENT_REFERENCE_NOT_OEM_CALIBRATION',
            'reference':'pvlib.pvsystem.singlediode',
            'reference_power_w':round(ref_power_w,5),
            'internal_power_w':round(ours,5),
            'relative_error_pct':round(deviation*100,5),
            'check_tolerance_pct':12.0,'within_reference_tolerance':deviation<=.12,
            'site_validated':False}


def independent_law_checks():
    """Conservation and Betz sanity checks with fixed research exemplars."""
    rho_air=1.225;radius=24;wind_ms=10
    betz_limit=2*(.5*rho_air*pi*radius**2*wind_ms**3*(16/27)/1000)
    cp_peak=max(cp_approx(x/10,2) for x in range(10,200))
    head=130; q=4;gravity=9.81
    hydraulic_ideal_kw=1000*gravity*q*head/1000
    return {'scope':'ANALYTICAL_SANITY_BOUNDS_NOT_SITE_ACCEPTANCE',
            'wind_betz_ceiling_at_10ms_kw':round(betz_limit,4),
            'parametric_cp_peak':round(cp_peak,5),
            'cp_below_16_27':cp_peak <= 16/27,
            'hydro_ideal_kw_at_4m3s_130m':round(hydraulic_ideal_kw,4),
            'pv_reference':'Call pvlib_standard_irradiance_check for separate library reference',
            'site_validated':False,'physical_control':False}
