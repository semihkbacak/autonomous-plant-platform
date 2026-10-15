"""Research-only pvlib De Soto calculation, explicit five-parameter input.

No default OEM parameters, no fabricated datasheets or certified MPPT.
See De Soto et al. (2006), DOI 10.1016/j.solener.2005.06.010.
"""
from __future__ import annotations
from math import isfinite

REQUIRED = ('alpha_sc','a_ref','I_L_ref','I_o_ref','R_sh_ref','R_s')

def model_point(module_params: dict, irradiance_w_m2: float, cell_temperature_c: float) -> dict:
    for name in REQUIRED:
        if name not in module_params:
            raise ValueError('Missing measured/fitted parameter: ' + name)
        v = module_params[name]
        if isinstance(v,bool) or not isinstance(v,(int,float)) or not isfinite(v) or v < 0:
            raise ValueError('Invalid model parameter: ' + name)
    if module_params['a_ref'] <= 0 or module_params['I_L_ref'] <= 0 or module_params['I_o_ref'] <= 0 or module_params['R_sh_ref'] <= 0:
        raise ValueError('Nonphysical diode parameter')
    for label, value, low, high in [('irradiance',irradiance_w_m2,0,1600),('cell_temperature',cell_temperature_c,-60,120)]:
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not isfinite(value) or not low <= value <= high:
            raise ValueError('Invalid '+label)
    try:
        from pvlib import pvsystem
    except ImportError as e:
        raise RuntimeError('Install the existing project pvlib dependency for this optional research calculation') from e
    params = pvsystem.calcparams_desoto(
        effective_irradiance=float(irradiance_w_m2),
        temp_cell=float(cell_temperature_c),
        alpha_sc=module_params['alpha_sc'],
        a_ref=module_params['a_ref'],
        I_L_ref=module_params['I_L_ref'],
        I_o_ref=module_params['I_o_ref'],
        R_sh_ref=module_params['R_sh_ref'],
        R_s=module_params['R_s'])
    result = pvsystem.singlediode(*params)
    pmax = float(result['p_mp']); vmpp=float(result['v_mp']); impp=float(result['i_mp'])
    if not all(isfinite(v) and v >= 0 for v in (pmax, vmpp, impp)):
        raise ValueError('Nonphysical computed result')
    return {'dc_module_mpp_w':pmax,'v_mp_v':vmpp,'i_mp_a':impp,
            'scope':'DESOTO_RESEARCH_ONLY_NOT_OEM_OR_FIELD_CERTIFIED',
            'external_parameter_provenance_verified':False,'protection_validated':False}
