"""v1.3: realistic SOFTWARE safety boundaries; no physical certification."""
from datetime import datetime,timedelta,timezone
from math import inf,nan
from pathlib import Path
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from simulator.engineering_ext.hydro import SurgeScreen,reservoir_mass_balance,efficiency_map_screen
from simulator.engineering_ext.solar import IVSample,parallel_string_mppt
from simulator.engineering_ext.wind import ActuatorState, actuator_step,yaw_loss_screen
from core.v13_site_contract import Tag,validate_register,check_measurement
from core.v13_security import totp_code,LocalOtpVerifier,decision
from core.v13_acceptance import evidence_inventory,acceptance_template,GATES
from core.v13_oem_provenance import Claim,review_claims
from app.v13_engineering_lab import create_v13_lab_router


def test_surge_joukowsky_relation():
    a=SurgeScreen(2,1,1000,0.5,1000).evaluate()
    b=SurgeScreen(4,1,1000,0.5,1000).evaluate()
    assert b['instantaneous_joukowsky_delta_bar'] == pytest.approx(2*a['instantaneous_joukowsky_delta_bar'],abs=0.000001)
    assert a['fast_closure_indicator']
    assert not a['applicable_as_design_pressure']
    assert 'METHOD_OF_CHARACTERISTICS' in a['requires']


def test_slow_closure_not_certified():
    r=SurgeScreen(1,1,1200,100,500).evaluate()
    assert not r['fast_closure_indicator']
    assert not r['applicable_as_design_pressure']


@pytest.mark.parametrize('parameter,bad', [('flow_m3_s',-1),('flow_m3_s',nan),('wave_speed_m_s',inf),
                                       ('pipe_diameter_m',0),('closure_s',0),('penstock_length_m',0),
                                       ('rho_kg_m3',float('nan')),('static_pressure_bar',-1)])
def test_bad_hydro_params_rejected(parameter,bad):
    base=dict(flow_m3_s=1,pipe_diameter_m=1,wave_speed_m_s=1000,closure_s=1,penstock_length_m=1000)
    base[parameter]=bad
    with pytest.raises(ValueError):SurgeScreen(**base).evaluate()


def test_hydro_water_balance_and_boundaries():
    a=reservoir_mass_balance(500,3,1,1,10,1000)
    assert a['accepted'] and a['proposed_volume_m3']==510
    b=reservoir_mass_balance(995,10,0,0,1,1000)
    assert not b['accepted'] and not b['applied_flow_adjustment']
    c=reservoir_mass_balance(1,0,3,0,1,1000)
    assert not c['accepted']


def test_turbine_map_not_oem_interpolation():
    a=efficiency_map_screen(1,1,[(1,1,.88),(.2,.5,.67)])
    assert a['efficiency_fraction']==pytest.approx(.88)
    assert not a['oem_validated'] and not a['interpolation']


def test_parallel_solar_sum_and_limits():
    c=(IVSample(0,10),IVSample(200,8),IVSample(400,0))
    a=parallel_string_mppt((c,),100,300)
    b=parallel_string_mppt((c,c),100,300)
    assert b['global_mpp_w']==pytest.approx(a['global_mpp_w']*2,rel=1e-10)
    assert b['mppt_window_mpp_w']<=b['global_mpp_w']
    assert not b['oem_calibrated']


def test_solar_window_missing_returns_zero():
    c=(IVSample(0,10),IVSample(10,0))
    r=parallel_string_mppt((c,),100,150)
    assert r['mppt_window_mpp_w']==0
    assert r['window_limit_w']>0


@pytest.mark.parametrize('curve', [
    (IVSample(0,10),IVSample(0,0)),
    (IVSample(10,1),IVSample(0,0)),
    (IVSample(0,-1),IVSample(10,0)),
    (IVSample(0,nan),IVSample(10,0)),
    (IVSample(0,10),),
])
def test_solar_invalid_iv_rejected(curve):
    with pytest.raises(ValueError):parallel_string_mppt((curve,),1,9)


def test_parallel_iv_requires_overlapping_measured_domain():
    with pytest.raises(ValueError):parallel_string_mppt(((IVSample(0,10),IVSample(5,0)),
                                                        (IVSample(10,10),IVSample(20,0))),1,15)


def test_wind_rate_limit_and_stuck():
    a=actuator_step(ActuatorState(0,0),20,30,1,pitch_rate_deg_s=3,yaw_rate_deg_s=2)
    assert a['pitch_deg']==3 and a['yaw_deg']==2
    b=actuator_step(ActuatorState(0,0,True,True),20,30,10)
    assert b['pitch_deg']==0 and b['yaw_deg']==0 and not b['command_complete']


def test_wind_yaw_loss_at_zero_and_large_angle():
    assert yaw_loss_screen(3000,0)['screened_power_kw']==3000
    assert yaw_loss_screen(3000,60)['screened_power_kw']<3000
    assert not yaw_loss_screen(1000,30)['structural_loads_validated']


@pytest.mark.parametrize('input_', [-1,nan,inf,True])
def test_yaw_reject_bad_power(input_):
    with pytest.raises(ValueError):yaw_loss_screen(input_,20)


def tag():return Tag('SITE_A','HES','UNIT_1','POWER','kW',0,10000,100)


def test_site_tags_validated_but_not_authenticated():
    t=tag(); validate_register([t]); now=datetime(2026,1,1,tzinfo=timezone.utc)
    report=check_measurement(t,400,'kW',now,now,'GOOD')
    assert report['usable'] and not report['source_authenticated']


@pytest.mark.parametrize('value,unit,shift,quality,reason',[
    (400,'MW',0,'GOOD','UNIT_MISMATCH'),
    (float('nan'),'kW',0,'GOOD','NONFINITE_VALUE'),
    (400,'kW',-360,'GOOD','STALE_DATA'),
    (400,'kW',360,'GOOD','FUTURE_TIMESTAMP'),
    (400,'kW',0,'BAD','SOURCE_QUALITY_BAD'),
    (20000,'kW',0,'GOOD','RANGE_VIOLATION'),
])
def test_site_measurement_failure(value,unit,shift,quality,reason):
    now=datetime(2026,1,1,tzinfo=timezone.utc)
    r=check_measurement(tag(),value,unit,now+timedelta(seconds=shift),now,quality)
    assert not r['usable'] and r['reason']==reason


def test_bad_tags_and_duplicate_rejected():
    with pytest.raises(ValueError):Tag('SITE_A','GES','INV_1','CURRENT','banana',0,10)
    with pytest.raises(ValueError):validate_register([tag(),tag()])


def test_policy_fail_closed_even_if_totp_verified():
    p=decision('sim_operator','simulation_command',primary_authenticated=True,mfa_verified=True,operation_mode='SHADOW')
    assert not p['allowed'] and p['reason']=='SHADOW_READ_ONLY'
    assert not decision('viewer','simulation_command',primary_authenticated=True,mfa_verified=True,operation_mode='SIMULATION')['allowed']
    assert not decision('sim_operator','simulation_command',primary_authenticated=False,mfa_verified=True,operation_mode='SIMULATION')['allowed']
    assert not decision('sim_operator','simulation_command',primary_authenticated=True,mfa_verified=False,operation_mode='SIMULATION')['allowed']
    assert not decision('sim_operator','simulation_command',primary_authenticated=True,mfa_verified=True,operation_mode='REAL')['allowed']


def test_totp_rfc_vector_and_no_replay():
    # RFC 6238 SHA1: time=59s 8-digit 94287082 (RFC public test secret).
    secret=b'12345678901234567890'
    assert totp_code(secret,1,8)=='94287082'
    verifier=LocalOtpVerifier(secret)
    token=totp_code(secret,1)
    assert verifier.verify(token,59,drift_steps=0)
    assert not verifier.verify(token,59,drift_steps=0)


def test_totp_reject_short_secret_and_invalid_token():
    with pytest.raises(ValueError):totp_code(b'123',1)
    assert not LocalOtpVerifier(b'1234567890123456').verify('abcdef',90)


def test_evidence_attachments_not_self_approving(tmp_path):
    (tmp_path/'OEM_GES').mkdir()
    (tmp_path/'OEM_GES'/'datasheet.pdf').write_bytes(b'SYNTHETIC DOCUMENT')
    r=evidence_inventory(tmp_path)
    assert r['count_unverified']==len(GATES)
    assert not r['eligible_for_real_site_control']
    assert r['evidence'][0]['documents'][0]['sha256']


def test_acceptance_template_never_preapproved():
    r=acceptance_template('DEMO_1','RES')
    assert len(r['tests'])==len(GATES)
    assert all(t['result']=='NOT_RUN' for t in r['tests'])
    assert not r['authorized_to_control']


def test_oem_claim_provenance_not_certification():
    c=Claim('PV_MODULE','DEMO','X','voc',45,'V','0'*64,'DECLARED_DATASHEET')
    a=review_claims([c])
    assert a['accepted_as_claimed']==1 and not a['oem_model_certified']
    with pytest.raises(ValueError):review_claims([c,c])


def test_research_api_methods_are_get_only():
    app=FastAPI();app.include_router(create_v13_lab_router()); client=TestClient(app)
    urls=['/api/v1/engineering/hydro/surge-screen',
          '/api/v1/engineering/hydro/reservoir-screen',
          '/api/v1/engineering/wind/yaw-screen',
          '/api/v1/engineering/wind/pitch-yaw-screen',
          '/api/v1/engineering/solar/parallel-iv-demo',
          '/api/v1/engineering/identity/policy-preview',
          '/api/v1/engineering/acceptance']
    spec=client.get('/openapi.json').json()['paths']
    assert all(set(spec[u])=={'get'} for u in urls)
    assert client.post('/api/v1/engineering/acceptance').status_code==405
    assert 'Gerçek tesis kontrolü DEVRE DIŞI' in client.get('/platform/engineering-lab').text


def test_endpoints_return_screening_only():
    app=FastAPI();app.include_router(create_v13_lab_router());c=TestClient(app)
    r=c.get('/api/v1/engineering/hydro/surge-screen',params=dict(flow_m3_s=2,pipe_diameter_m=1,
        wave_speed_m_s=1000,closure_s=1,penstock_length_m=500))
    assert r.status_code==200 and not r.json()['applicable_as_design_pressure']
    assert c.get('/api/v1/engineering/solar/parallel-iv-demo').status_code==200
    assert not c.get('/api/v1/engineering/acceptance').json()['eligible_for_real_site_control']
