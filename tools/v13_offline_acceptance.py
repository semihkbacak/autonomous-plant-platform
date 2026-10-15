"""Run deterministic engineering smoke tests and write honest JSON evidence."""
from __future__ import annotations
import argparse,json
from pathlib import Path
from datetime import datetime,timezone
from simulator.engineering_ext.hydro import SurgeScreen,reservoir_mass_balance
from simulator.engineering_ext.wind import ActuatorState,actuator_step
from simulator.engineering_ext.solar import IVSample,parallel_string_mppt
from core.v13_security import decision
from core.v13_acceptance import evidence_inventory


def execute() -> dict:
    hydro=SurgeScreen(2.5,1.2,1100,3,900).evaluate()
    water=reservoir_mass_balance(5000,3,2,0.5,60,10000)
    wind=actuator_step(ActuatorState(3,0),10,15,5)
    curve=(IVSample(0,10),IVSample(300,8),IVSample(500,0))
    solar=parallel_string_mppt((curve,curve),150,450,samples=501)
    access=decision('sim_operator','simulation_command',primary_authenticated=True,mfa_verified=True,operation_mode='SHADOW')
    checks={
        'surge_positive':hydro['instantaneous_joukowsky_delta_bar']>0,
        'hydro_not_certified':not hydro['applicable_as_design_pressure'],
        'mass_balance':water['accepted'],
        'wind_pitch_rate':wind['pitch_deg']==10,
        'solar_parallel_positive':solar['global_mpp_w']>0,
        'solar_not_oem':not solar['oem_calibrated'],
        'shadow_commands_denied':not access['allowed'],
        'real_control_off':not evidence_inventory(None)['eligible_for_real_site_control'],
    }
    return {'generated_utc':datetime.now(timezone.utc).isoformat(),
            'scope':'SYNTHETIC_SIMULATOR_RESEARCH_ONLY',
            'checks':checks,'passed':all(checks.values()),
            'oem_field_hil_fat_sat_passed':False,'real_control_enabled':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report',type=Path,required=True)
    args=p.parse_args()
    result=execute()
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print('REPORT:',args.report)
    return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
