"""UTC production schedules and SIMULATOR-ONLY export dispatch.

Not a grid dispatch / governor / inverter controller. Native simulator output is the
physical upper envelope; requested kW is not reported as actual generation.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math

PLANTS = ('HES', 'GES', 'RES')
# Conservative synthetically declared portfolio export ceilings; not OEM ratings.
SYNTHETIC_EXPORT_CEILINGS_KW = {'HES':30_000.0, 'GES':100_000.0, 'RES':100_000.0}

SQL = '''
CREATE TABLE IF NOT EXISTS production_plans(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 run_id TEXT NOT NULL REFERENCES runs(id),
 plant TEXT NOT NULL CHECK(plant IN ('HES','GES','RES')),
 utc_start TEXT NOT NULL, utc_end TEXT NOT NULL,
 target_kw REAL NOT NULL CHECK(target_kw>=0),
 interval_minutes INTEGER NOT NULL CHECK(interval_minutes IN (15,60,1440)),
 created_utc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_prod_plans ON production_plans(run_id,plant,utc_start);
CREATE TABLE IF NOT EXISTS dispatch_controls(
 run_id TEXT NOT NULL REFERENCES runs(id),
 plant TEXT NOT NULL CHECK(plant IN ('HES','GES','RES')),
 operation TEXT NOT NULL CHECK(operation IN ('AUTO','START','STOP')),
 manual_kw REAL CHECK(manual_kw>=0),
 PRIMARY KEY(run_id,plant)
);
CREATE TABLE IF NOT EXISTS dispatch_audit(
 id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL REFERENCES runs(id),
 event_utc TEXT NOT NULL, actor TEXT NOT NULL, kind TEXT NOT NULL,
 payload_json TEXT NOT NULL, prev_sha TEXT NOT NULL, event_sha TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_dispatch_audit ON dispatch_audit(run_id,id);
CREATE INDEX IF NOT EXISTS idx_samples_dispatch ON samples(run_id,plant,utc_start);
CREATE TRIGGER IF NOT EXISTS dispatch_audit_immutable_update
 BEFORE UPDATE ON dispatch_audit BEGIN SELECT RAISE(ABORT,'append-only dispatch audit'); END;
CREATE TRIGGER IF NOT EXISTS dispatch_audit_immutable_delete
 BEFORE DELETE ON dispatch_audit BEGIN SELECT RAISE(ABORT,'append-only dispatch audit'); END;
'''

def utc_time(value: str) -> datetime:
    if not isinstance(value,str):raise ValueError('UTC timestamp required')
    try:dt = datetime.fromisoformat(value.replace('Z','+00:00'))
    except (TypeError,ValueError) as e:raise ValueError('Invalid ISO 8601 timestamp') from e
    if dt.tzinfo is None or dt.utcoffset()!=timedelta(0) or dt.second or dt.microsecond or dt.minute%15:
        raise ValueError('15-minute-aligned UTC timestamp required')
    return dt.astimezone(timezone.utc)

def power_kw(value:float, plant:str) -> float:
    if plant not in PLANTS:raise ValueError('Unknown plant')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Finite numeric power required')
    if value<0 or value>SYNTHETIC_EXPORT_CEILINGS_KW[plant]:
        raise ValueError('Outside declared synthetic export ceiling')
    return float(value)

def audit(con,run_id,kind,payload,actor='LOCAL_OPERATOR'):
    prev=con.execute('SELECT event_sha FROM dispatch_audit WHERE run_id=? ORDER BY id DESC LIMIT 1',(run_id,)).fetchone()
    prev_sha=prev[0] if prev else '0'*64
    utc=datetime.now(timezone.utc).isoformat()
    doc=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False)
    digest=sha256(json.dumps([run_id,utc,actor,kind,doc,prev_sha],separators=(',',':')).encode()).hexdigest()
    con.execute('INSERT INTO dispatch_audit(run_id,event_utc,actor,kind,payload_json,prev_sha,event_sha) VALUES(?,?,?,?,?,?,?)',
                (run_id,utc,actor,kind,doc,prev_sha,digest))

def verify_audit(con,run_id):
    prev='0'*64
    for row in con.execute('SELECT * FROM dispatch_audit WHERE run_id=? ORDER BY id',(run_id,)):
        d=sha256(json.dumps([row['run_id'],row['event_utc'],row['actor'],row['kind'],row['payload_json'],prev],separators=(',',':')).encode()).hexdigest()
        if row['prev_sha']!=prev or row['event_sha']!=d:
            raise ValueError('Dispatch audit chain damaged')
        prev=d

def active_request(con,run_id,utc_start):
    """Single consistent read of next 15-minute UTC slot dispatch decisions."""
    outcome={}
    for p in PLANTS:
        c=con.execute('SELECT operation,manual_kw FROM dispatch_controls WHERE run_id=? AND plant=?',(run_id,p)).fetchone()
        exists=con.execute('SELECT 1 FROM production_plans WHERE run_id=? AND plant=? LIMIT 1',(run_id,p)).fetchone() is not None
        row=con.execute('SELECT * FROM production_plans WHERE run_id=? AND plant=? AND utc_start<=? AND utc_end>? ORDER BY id DESC LIMIT 1',
                        (run_id,p,utc_start,utc_start)).fetchone()
        # A started plan defaults to 0 output outside its defined time intervals.
        target=float(row['target_kw']) if row else (0.0 if exists else None)
        manual=float(c['manual_kw']) if c and c['manual_kw'] is not None else None
        op=c['operation'] if c else 'AUTO'
        outcome[p]={'target_kw':target,'manual_kw':manual,'operation':op,
                    'plan_id':row['id'] if row else None,'has_plan':exists}
    return outcome

def dispatch_row(row:dict, req:dict) -> dict:
    """Curtail synthetic export only, without forging extra generation."""
    native_kw=float(row['power_kw'])
    native_energy=float(row['energy_kwh'])
    available=min(native_kw,SYNTHETIC_EXPORT_CEILINGS_KW[row['plant']])
    # Independent conservative resource interlocks supplement existing native
    # engine permissives; no positive resource = no allowed export.
    conditions=row.get('conditions') or {}
    interlock=None
    if row['plant']=='GES':
        irr=conditions.get('irradiance_ghi_w_m2')
        if isinstance(irr,(float,int)) and (not math.isfinite(irr) or irr<=0):
            interlock='NO_SOLAR_IRRADIANCE'
    elif row['plant']=='RES':
        wind=conditions.get('wind_speed_m_s')
        if isinstance(wind,(float,int)) and (not math.isfinite(wind) or wind<3 or wind>25):
            interlock='WIND_OUTSIDE_SYNTHETIC_CUT_IN_OUT'
    elif row['plant']=='HES':
        head=conditions.get('net_head_m')
        flow=conditions.get('flow_m3_s')
        if any(isinstance(v,(float,int)) and (not math.isfinite(v) or v<=0) for v in (head,flow)):
            interlock='INSUFFICIENT_HYDRAULIC_RESOURCE'
    if interlock is not None:
        available=0.0
    demand=req.get('manual_kw')
    origin='MANUAL' if demand is not None else 'PLAN' if req.get('target_kw') is not None else 'NATIVE'
    if demand is None:demand=req.get('target_kw')
    op=req.get('operation','AUTO')
    if op=='STOP': permitted=0.0; reason='OPERATOR_STOP'
    else:
        permitted=available if demand is None else min(available,float(demand))
        reason='NO_REQUEST' if demand is None else 'TARGET_MET'
        if demand is not None and available+1e-8 < demand:
            reason='PHYSICAL_AVAILABILITY_LIMIT'
        elif demand is not None and permitted+1e-8<available:
            reason='SYNTHETIC_CURTAILMENT'
        if interlock is not None:
            reason=interlock
        elif op=='START' and available<=1e-8:
            reason='START_ACCEPTED_NO_PHYSICAL_RESOURCE'
    if permitted<=1e-9 and not native_kw: permitted=0.0
    # This is an export envelope model. Intra-slot native hydro output remains
    # unchanged; no hidden hydro governor or reservoir feedback is claimed.
    factor=permitted/native_kw if native_kw>0 else 0.0
    updated=dict(row)
    updated['power_kw']=permitted
    updated['energy_kwh']=native_energy*factor
    updated['units']=[{**u,'native_kw':u.get('kw',0.0),'kw':float(u.get('kw',0.0))*factor} for u in row['units']]
    updated['conditions']={**row['conditions'], 'dispatch':{
        'physical_source':'NATIVE_SIMULATOR_OUTPUT_SYNTHETIC',
        'native_available_kw':native_kw,'available_export_kw':available,
        'requested_kw':demand,'scheduled_kw':req.get('target_kw'),'expected_energy_kwh':(demand*0.25 if demand is not None else None),
        'actual_energy_kwh':updated['energy_kwh'],
        'deviation_kwh':(updated['energy_kwh']-demand*0.25 if demand is not None else None),
        'request_origin':origin,'operation':op,'plan_id':req.get('plan_id'),
        'reason':reason,'physical_input_interlock':interlock,'native_energy_kwh':native_energy,
        'note':'Post-model synthetic export envelope; hydro storage/governor dynamics are not recomputed'}}
    return updated
