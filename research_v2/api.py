"""Optional local research endpoints: NO equipment IO and NO live simulator writes."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field
from research_v2.workspace import ResearchStore, comparison
from research_v2.physics import hydro_ideal_kw,pv_ideal_kw,wind_ideal_kw
from research_v2.engine import ScreeningConfig, run_into_store
from research_v2.provenance import validate_offline_csv
from research_v2.benchmarks import chronological_holdout

DEFAULT_DB=Path('outputs/research_v2/research.sqlite3')
router=APIRouter(prefix='/api/v2/research',tags=['Offline research v2 / no field control'])

def store():return ResearchStore(Path(os.environ.get('APP_RESEARCH_DB',str(DEFAULT_DB))))

class NewSession(BaseModel):
    session_id:str=Field(min_length=1,max_length=48)
    site_id:str=Field(min_length=1,max_length=48)
    plant:str
    scenario:str=Field(min_length=1,max_length=100)
    start_utc:str
    step_s:int=Field(ge=1,le=86400,default=900)
class NewSample(BaseModel):
    step_index:int=Field(ge=0)
    power_kw:float=Field(ge=0,allow_inf_nan=False)
class Measurement(BaseModel):
    step_index:int=Field(ge=0)
    measured_kw:float=Field(ge=0,allow_inf_nan=False)
class Measurements(BaseModel):
    rows:list[Measurement]=Field(max_length=100000)

@router.get('/capabilities')
def capabilities():return {'status':'RESEARCH_PREVIEW','field_control_authorized':False,'site_validated':False,'real_control_ready':False,'supported_plants':['HES','GES','RES']}
@router.post('/sessions')
def create(payload:NewSession):
    try:return store().create(**payload.model_dump())
    except (ValueError,sqlite3.IntegrityError) as e:raise HTTPException(422,str(e)) from e
@router.get('/sessions')
def list_sessions(site_id:str|None=None):
    try:return store().list(site_id)
    except ValueError as e:raise HTTPException(422,str(e)) from e
@router.get('/sessions/{sid}')
def session(sid:str):
    try:return store().get(sid)
    except (KeyError,ValueError) as e:raise HTTPException(404,str(e)) from e
@router.post('/sessions/{sid}/samples')
def sample(sid:str,payload:NewSample):
    try:return store().add(sid,**payload.model_dump())
    except KeyError as e:raise HTTPException(404,str(e)) from e
    except (ValueError,sqlite3.IntegrityError) as e:raise HTTPException(422,str(e)) from e
@router.post('/sessions/{sid}/measurements')
def measurement(sid:str,payload:Measurements):
    try:return {'inserted':store().measurements(sid,[x.model_dump() for x in payload.rows]),'source_verified':False}
    except KeyError as e:raise HTTPException(404,str(e)) from e
    except (ValueError,sqlite3.IntegrityError) as e:raise HTTPException(422,str(e)) from e
@router.get('/sessions/{sid}/validation')
def validation(sid:str):
    try:return store().evaluation(sid)
    except KeyError as e:raise HTTPException(404,str(e)) from e
@router.get('/sessions/{sid}/export.csv',response_class=PlainTextResponse)
def export(sid:str):
    try:return PlainTextResponse(store().export_csv(sid),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="simulation_research.csv"'})
    except KeyError as e:raise HTTPException(404,str(e)) from e
@router.get('/compare')
def compare(ids:str=Query(max_length=600)):
    try:return comparison(store(),ids.split(','))
    except (ValueError,KeyError) as e:raise HTTPException(422,str(e)) from e
@router.get('/physics/ideal-screening')
def physics():return {'formulas':{'HES':'9.81 * flow_m3_s * head_m * efficiency [kW]','GES':'area_m2 * irradiance_w_m2 * efficiency / 1000 [kW]','RES':'0.5 * rho * pi * radius_m^2 * wind_m_s^3 * Cp / 1000 [kW]'},'scope':'IDEAL_SCREENING_ONLY_NOT_OEM_VALIDATED'}

class RunScreening(BaseModel):
    start_utc:str
    days:int=Field(default=1,ge=1,le=31)
    step_s:int=Field(default=900)
    hes_flow_m3_s:float=Field(default=15,ge=0,allow_inf_nan=False)
    hes_head_m:float=Field(default=70,ge=0,allow_inf_nan=False)
    hes_efficiency:float=Field(default=.88,ge=0,le=1,allow_inf_nan=False)
    ges_area_m2:float=Field(default=25000,ge=0,allow_inf_nan=False)
    ges_efficiency:float=Field(default=.18,ge=0,le=1,allow_inf_nan=False)
    res_radius_m:float=Field(default=40,ge=0,allow_inf_nan=False)
    res_cp:float=Field(default=.38,ge=0,le=.593,allow_inf_nan=False)
    res_rho:float=Field(default=1.225,ge=0,allow_inf_nan=False)
    res_rated_kw:float=Field(default=1500,gt=0,allow_inf_nan=False)

@router.post('/sessions/{sid}/run-offline')
def run_offline(sid:str,payload:RunScreening,limit:int=Query(default=96,ge=0,le=3000)):
    """Synthetic screening only. Resumes contiguous local SQLite sequence by index."""
    try:
        return run_into_store(store(),sid,ScreeningConfig(**payload.model_dump()),limit=limit)
    except KeyError as exc:raise HTTPException(404,str(exc)) from exc
    except (ValueError,sqlite3.IntegrityError) as exc:raise HTTPException(422,str(exc)) from exc

@router.get('/sessions/{sid}/export.xlsx')
def xlsx(sid:str):
    try:
        data=store().export_xlsx(sid)
        return Response(content=data,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="research_simulation.xlsx"','X-Content-Type-Options':'nosniff'})
    except KeyError as exc:raise HTTPException(404,str(exc)) from exc

class ChronoData(BaseModel):
    predicted_kw:list[float]=Field(min_length=8,max_length=100000)
    measured_kw:list[float]=Field(min_length=8,max_length=100000)
    train_fraction:float=Field(default=.75,ge=.5,le=.9)

@router.post('/validation/chronological-holdout')
def benchmark(payload:ChronoData):
    try:return chronological_holdout(payload.predicted_kw,payload.measured_kw,payload.train_fraction)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc

class OfflineCSVRequest(BaseModel):
    csv_text:str=Field(min_length=1,max_length=4_000_000)
    site_id:str=Field(min_length=1,max_length=48)
    source_label:str=Field(min_length=1,max_length=100)
    claimed_calibrated:bool=False

@router.post('/validate-offline-csv')
def audit_csv(payload:OfflineCSVRequest):
    try:
        result=validate_offline_csv(payload.csv_text.encode('utf-8'),expected_site_id=payload.site_id,
                                     source_label=payload.source_label,calibrated=payload.claimed_calibrated)
        result.pop('measurements')  # Avoid retaining user records in HTTP logs/responses
        return result
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
