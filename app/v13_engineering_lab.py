"""Read-only engineering feasibility laboratory. Never issues plant commands."""
from __future__ import annotations
import os
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from simulator.engineering_ext.hydro import SurgeScreen, reservoir_mass_balance
from simulator.engineering_ext.wind import ActuatorState, actuator_step, yaw_loss_screen
from simulator.engineering_ext.solar import IVSample, parallel_string_mppt
from core.v13_security import decision
from core.v13_acceptance import evidence_inventory,acceptance_template


def create_v13_lab_router() -> APIRouter:
    router = APIRouter(tags=['v1.3 Research engineering previews — read-only'])

    @router.get('/api/v1/engineering/hydro/surge-screen')
    def surge_screen(flow_m3_s:float=Query(ge=0,le=2000),
                     pipe_diameter_m:float=Query(gt=0,le=20),
                     wave_speed_m_s:float=Query(ge=100,le=2000),
                     closure_s:float=Query(gt=0,le=3600),
                     penstock_length_m:float=Query(gt=0,le=30000)):
        try:
            return SurgeScreen(flow_m3_s,pipe_diameter_m,wave_speed_m_s,closure_s,penstock_length_m).evaluate()
        except ValueError as e:raise HTTPException(422,str(e)) from e

    @router.get('/api/v1/engineering/hydro/reservoir-screen')
    def reservoir_screen(volume_m3:float=Query(ge=0), inflow_m3_s:float=Query(ge=0),
                         release_m3_s:float=Query(ge=0), spill_m3_s:float=Query(ge=0),
                         dt_s:float=Query(gt=0), capacity_m3:float=Query(gt=0)):
        try:return reservoir_mass_balance(volume_m3,inflow_m3_s,release_m3_s,spill_m3_s,dt_s,capacity_m3)
        except ValueError as e:raise HTTPException(422,str(e)) from e

    @router.get('/api/v1/engineering/wind/yaw-screen')
    def wind_yaw(power_kw:float=Query(ge=0),yaw_error_deg:float=Query(ge=-90,le=90)):
        try:return yaw_loss_screen(power_kw,yaw_error_deg)
        except ValueError as e:raise HTTPException(422,str(e)) from e

    @router.get('/api/v1/engineering/wind/pitch-yaw-screen')
    def wind_actuator(pitch_deg:float=Query(ge=0,le=90), yaw_deg:float=Query(ge=-180,le=180),
                      target_pitch_deg:float=Query(ge=0,le=90), target_yaw_deg:float=Query(ge=-180,le=180),
                      dt_s:float=Query(gt=0,le=3600), pitch_stuck:bool=False,yaw_stuck:bool=False):
        try:return actuator_step(ActuatorState(pitch_deg,yaw_deg,pitch_stuck,yaw_stuck),
                                 target_pitch_deg,target_yaw_deg,dt_s)
        except ValueError as e:raise HTTPException(422,str(e)) from e

    @router.get('/api/v1/engineering/solar/parallel-iv-demo')
    def solar_demo(shading_fraction:float=Query(default=.6,ge=0,le=1)):
        # Clearly synthetic illustrative IV curves. Voltage/current points do
        # not come from OEM field measurements or bypass circuit simulation.
        a=tuple(IVSample(v, max(0.0,10.0*(1-v/600))) for v in range(0,601,10))
        b=tuple(IVSample(v, max(0.0,10.0*shading_fraction*(1-v/550))) for v in range(0,601,10))
        result=parallel_string_mppt((a,b),150,550)
        return {'source':'SYNTHETIC_DEMONSTRATION_ONLY',**result}

    @router.get('/api/v1/engineering/identity/policy-preview')
    def policy(role:str='viewer',action:str='read_telemetry', primary_authenticated:bool=False,
               mfa_verified:bool=False,operation_mode:str='SHADOW'):
        return {'scope':'OFFLINE_POLICY_PREVIEW_NOT_ENFORCED_ON_EXISTING_API',
                **decision(role,action,primary_authenticated=primary_authenticated,
                           mfa_verified=mfa_verified,operation_mode=operation_mode)}

    @router.get('/api/v1/engineering/acceptance')
    def readiness():
        return evidence_inventory(os.getenv('APP_SITE_EVIDENCE_DIR'))

    @router.get('/platform/engineering-lab',response_class=HTMLResponse)
    def lab():return HTML

    return router


HTML = '''<!doctype html><html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Engineering Lab v1.3</title>
<style>:root{color-scheme:dark;font-family:system-ui}body{background:#0c1726;color:#ebf4fc;margin:0}header{padding:24px max(20px,calc((100vw - 1150px)/2));background:#15253a}main{max-width:1150px;padding:20px;margin:auto}article{padding:18px;margin:14px 0;border:1px solid #33516f;border-radius:12px;background:#1b2e43}a{color:#89d1ff}h1{font-size:24px}.warning{color:#ffd299}code{color:#8ff3d4}</style></head><body><header><small>AUTONOMOUS PLANT PLATFORM · ARAŞTIRMA</small><h1>HES / GES / RES — Engineering Lab v1.3</h1><a href="/platform/dashboard">← Ortak Dashboard</a></header><main>
<article class="warning"><b>Gerçek tesis kontrolü DEVRE DIŞI.</b> Bunlar parametrik tarama hesaplarıdır; OEM onayı, saha kalibrasyonu, HIL/FAT/SAT veya bağımsız koruma doğrulaması değildir.</article>
<article><h2>HES</h2><p>Joukowsky ideal basınç taraması ve rezervuar kütle dengesi.</p><a href="/docs">Developer Center — GET API örnekleri</a></article>
<article><h2>GES</h2><p>Örneklenmiş iki paralel string I–V verilerinden MPPT taraması; tam bypass diyot modeli veya OEM kalibrasyonu değildir.</p><a href="/api/v1/engineering/solar/parallel-iv-demo">Sentetik paralel string örneği →</a></article>
<article><h2>RES</h2><p>Pitch/yaw hız sınırı ve yaw kaynaklı güç sapması. Yapısal yükler analiz edilmez.</p><a href="/api/v1/engineering/wind/yaw-screen?power_kw=3000&yaw_error_deg=20">Sentetik yaw örneği →</a></article>
<article><h2>İşletim kapıları</h2><p>Offline erişim politikası inceleme ve bağımsız kabul kanıtı envanteri.</p><a href="/api/v1/engineering/acceptance">Kanıt envanteri →</a></article>
</main></body></html>'''
