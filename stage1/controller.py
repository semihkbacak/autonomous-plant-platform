"""Single-writer, fail-closed synchronized synthetic portfolio coordinator."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from uuid import uuid4
from time import perf_counter
import os

from stage1.engine import ClockConfig, ThreePlantEngine, MODEL_REVISION, SCOPE
from stage1.store import Journal


def default_path() -> Path:
    base = os.environ.get('LOCALAPPDATA') if os.name == 'nt' else os.environ.get('XDG_STATE_HOME')
    if not base:
        base = str(Path.home() / '.local' / 'state')
    return Path(base) / 'AutonomousPlantPlatform' / 'stage1' / 'synchronized.sqlite3'


class Coordinator:
    def __init__(self, path: str | Path, solar_factory=None, wind_factory=None):
        self.journal = Journal(path)
        self.lock = RLock()
        self.factories={}
        if solar_factory:self.factories['solar_factory']=solar_factory
        if wind_factory:self.factories['wind_factory']=wind_factory
        self.run_id=None
        self.engine=None
        self.state='NOT_CREATED'
        self.recovered=False
        self.error=None
        self.autocount=0
        self.speed_mode="NORMAL"
        self.profile={"steps":0,"compute_s":0.0,"journal_s":0.0,"last_compute_s":0.0,"last_journal_s":0.0}
        # Automatic rehydration from only the LAST committed triple-row slot.
        self.reload()

    def reload(self):
        with self.lock:
            record=self.journal.load_active(**self.factories)
            if record:
                self.run_id=record['run_id']
                self.engine=record['engine']
                self.state=record['state']
                self.recovered=True
                self.error=None
            else:
                self.run_id=None
                self.engine=None
                self.state='NOT_CREATED'
            return self.status()

    def create(self, config:ClockConfig):
        with self.lock:
            if self.state=='RUNNING':
                raise ValueError('Pause the previous run before creating a new one')
            e=ThreePlantEngine(config,**self.factories)
            new_id=self.journal.create(config,e)
            self.run_id,self.engine,self.state=new_id,e,'PAUSED'
            self.error=None
            self.recovered=False
            self.profile={'steps':0,'compute_s':0.0,'journal_s':0.0,'last_compute_s':0.0,'last_journal_s':0.0}
            return self.status()

    def status(self):
        if self.engine is None:
            return {'scope':SCOPE,'run_id':None,'state':'NOT_CREATED','recovered':False,
                    'utc':None, 'error':self.error,'model_revision':MODEL_REVISION}
        engine=self.engine
        now=engine.config.start+timedelta(seconds=engine.index*900)
        return {'scope':SCOPE,'run_id':self.run_id,'state':self.state,'recovered':self.recovered,
                'model_revision':MODEL_REVISION,'utc':now.isoformat(),
                'index':engine.index,'max_steps':engine.config.maximum_steps,
                'step_seconds':900,'days':engine.config.days,'start_utc':engine.config.start.isoformat(),
                'total_kwh':dict(engine.totals),'latest':engine.latest,'scenario':dict(engine.mode),
                'error':self.error,'journal':str(self.journal.path),
                'weather_source':'REPEATED_SYNTHETIC_DEMO_DAY_NO_MEASURED_DATA',
                'physical_control':False,'dispatch_kind':'SYNTHETIC_EXPORT_ENVELOPE',
                'speed_mode':self.speed_mode,'profile':dict(self.profile),
                'dispatch':self.journal.dispatch_request(self.run_id,now.isoformat())}

    def start(self):
        with self.lock:
            if not self.engine or self.state=='COMPLETE':raise ValueError('No resumable run')
            if self.error:raise ValueError('Model/database error latched; reload required')
            self.journal.set_state(self.run_id,'RUNNING')
            self.state='RUNNING'
            return self.status()

    def pause(self):
        with self.lock:
            if not self.engine:raise ValueError('No run')
            if self.state=='COMPLETE':return self.status()
            self.journal.set_state(self.run_id,'PAUSED')
            self.state='PAUSED'
            return self.status()

    def set_mode(self,plant,mode):
        with self.lock:
            if not self.engine or self.state=='RUNNING':
                raise ValueError('Pause before changing a synthetic scenario')
            self.engine.change_mode(plant,mode)
            try:self.journal.update_checkpoint(self.run_id,self.engine)
            except Exception:
                self.error='JOURNAL_COMMIT_FAILED'; raise
            return self.status()

    def advance(self,count:int=1):
        if type(count) is not int or not 1<=count<=96:
            raise ValueError('Step count must be 1..96')
        with self.lock:
            if not self.engine or self.state=='COMPLETE':raise ValueError('No running/paused session')
            if self.error:raise ValueError('Error latched; restart/reload before stepping')
            for _ in range(count):
                if self.state=='COMPLETE':break
                before=self.engine.index
                try:
                    utc=(self.engine.config.start+timedelta(seconds=before*900)).isoformat()
                    requests=self.journal.dispatch_request(self.run_id,utc)
                    t0=perf_counter()
                    rows=self.engine.advance(requests if any(v['has_plan'] or v['manual_kw'] is not None or v['operation']!='AUTO' for v in requests.values()) else None)
                    cp=self.engine.snapshot()
                    t1=perf_counter()
                    done=self.engine.index==self.engine.config.maximum_steps
                    self.journal.advance(self.run_id,before,rows,cp,done)
                    t2=perf_counter()
                    self.profile['steps']+=1
                    self.profile['compute_s']+=t1-t0
                    self.profile['journal_s']+=t2-t1
                    self.profile['last_compute_s']=t1-t0
                    self.profile['last_journal_s']=t2-t1
                    if done:self.state='COMPLETE'
                except Exception as exc:
                    # Do not allow using partially advanced memory state.
                    # Last valid checkpoint remains persisted transactionally.
                    self.error=type(exc).__name__
                    self.state='FAULT_LATCHED'
                    raise
            return self.status()

    def auto_step(self):
        with self.lock:
            if self.state!='RUNNING' or self.error:return
            self.autocount+=1
            # Two wall seconds per 15 simulated minutes, matching old demo pace.
            if self.speed_mode=='NORMAL' and self.autocount%2:
                return
            self.advance({'NORMAL':1,'FAST':1,'MAX':4}[self.speed_mode])

    def set_speed(self,mode:str):
        if mode not in ('NORMAL','FAST','MAX'):
            raise ValueError('Unknown speed mode')
        with self.lock:
            self.speed_mode=mode
            self.autocount=0
            return self.status()

    def add_plan(self,plant,start_utc,end_utc,target_kw,interval_minutes):
        with self.lock:
            if not self.engine or self.state=='COMPLETE' or self.error:raise ValueError('No editable run')
            # No in-flight slot writes: this lock serializes UI writes and advances.
            try:
                self.journal.add_plan(self.run_id,plant,start_utc,end_utc,target_kw,interval_minutes,self.engine.config,self.engine.index)
            except ValueError as exc:
                # Overlaps are already logged atomically by the journal.
                if 'Overlapping plan' not in str(exc):
                    self.journal.reject_command(self.run_id,'PLAN_REJECTED',plant,str(exc))
                raise
            return self.status()

    def remove_plan(self,entry_id):
        with self.lock:
            if not self.engine or self.error:raise ValueError('No editable run')
            now=(self.engine.config.start+timedelta(seconds=self.engine.index*900)).isoformat()
            self.journal.cancel_plan(self.run_id,entry_id,now)
            return self.status()

    def manual_setpoint(self,plant,kw):
        with self.lock:
            if not self.engine or self.state=='COMPLETE' or self.error:raise ValueError('No editable run')
            try:self.journal.set_manual(self.run_id,plant,kw)
            except ValueError as exc:
                self.journal.reject_command(self.run_id,'COMMAND_REJECTED',plant,str(exc))
                raise
            return self.status()

    def operator_command(self,plant,operation):
        with self.lock:
            if not self.engine or self.state=='COMPLETE' or self.error:raise ValueError('No editable run')
            now=(self.engine.config.start+timedelta(seconds=self.engine.index*900)).isoformat()
            # Scenario and hydro safety modes cannot be bypassed by an export START.
            if operation=='START':
                if plant in ('GES','RES') and self.engine.mode[plant] in ('GRID_LOSS','ESTOP','FAULT'):
                    reason='START blocked by native synthetic plant safety scenario'
                    self.journal.reject_command(self.run_id,'COMMAND_REJECTED',plant,reason)
                    raise ValueError(reason)
                if plant=='HES' and (self.engine.hydro.state.emergency_stop or self.engine.hydro.state.maintenance_lock):
                    reason='START blocked by native HES safety state'
                    self.journal.reject_command(self.run_id,'COMMAND_REJECTED',plant,reason)
                    raise ValueError(reason)
            try:self.journal.set_operation(self.run_id,plant,operation,now)
            except ValueError as exc:
                if 'START denied' not in str(exc):
                    self.journal.reject_command(self.run_id,'COMMAND_REJECTED',plant,str(exc))
                raise
            return self.status()

    def export_rows(self,limit=10000,after=-1):
        with self.lock:
            if not self.run_id:return []
            return self.journal.samples(self.run_id,limit,after)
