"""Real wind engine, stubbed solar regression if pvlib is unavailable."""
from app.sim_runtime import MODES
from tools.live_simulation_acceptance import evaluate,run


def test_wind_grid_loss_full_day():
    x=evaluate('res','GRID_LOSS')
    assert x['passed'],x
    assert x['energy_kwh']==0
    assert x['steps']==96


def test_wind_normal_and_low_wind():
    normal=evaluate('res','NORMAL')
    calm=evaluate('res','LOW_WIND')
    assert normal['passed'] and calm['passed']
    assert normal['energy_kwh']>0
    assert calm['energy_kwh']==0


def test_wind_high_wind_trip():
    x=evaluate('res','HIGH_WIND')
    assert x['passed'],x
    assert x['peak_kw']==0


def test_wind_fault_and_curtail_are_bounded():
    normal=evaluate('res','NORMAL')
    fault=evaluate('res','FAULT')
    curtailed=evaluate('res','CURTAIL_50')
    assert normal['passed'] and fault['passed'] and curtailed['passed']
    assert fault['energy_kwh']<=normal['energy_kwh']
    assert curtailed['energy_kwh']<=normal['energy_kwh']


def test_bad_plant_is_not_tested():
    try:
        run('real_ot')
    except ValueError:
        return
    raise AssertionError('Unexpectedly accepted real OT plant')
