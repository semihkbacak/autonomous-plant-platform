"""Serialized, opt-in local research sessions; no real command bus."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from threading import RLock
import os
from advanced_v2.engine import AdvancedEngine,ResearchConfig
from advanced_v2.journal import Journal
from advanced_v2.physics import VERSION,SCOPE


def default_path():
    base=os.environ.get('LOCALAPPDATA') if os.name=='nt' else os.environ.get('XDG_STATE_HOME')
    if not base:base=str(Path.home()/'.local'/'state')
    return Path(base)/'AutonomousPlantPlatform'/'advanced'/'research.sqlite3'


class Controller:
    def __init__(self,path):
        self.journal=Journal(path)
        self.lock=RLock()
        self.id=None;self.engine=None;self.state='NOT_CREATED';self.error=None;self.recovered=False
        self.autocount=0
        self.reload()

    def reload(self):
        with self.lock:
            loaded=self.journal.restore()
            if loaded:
                self.id=loaded['id'];self.engine=loaded['engine'];self.state=loaded['state'];self.recovered=True;self.error=None
            else:
                self.id=None;self.engine=None;self.state='NOT_CREATED';self.recovered=False;self.error=None
            return self.status()

    def create(self,config):
        with self.lock:
            if self.state=='RUNNING':raise ValueError('Pause current research run first')
            e=AdvancedEngine(config)
            rid=self.journal.create(e)
            self.id,self.engine,self.state=rid,e,'PAUSED'
            self.recovered=False;self.error=None
            return self.status()

    def status(self):
        if self.engine is None:
            return {'scope':SCOPE,'version':VERSION,'run_id':None,'state':self.state,'error':self.error}
        e=self.engine
        return {'scope':SCOPE,'version':VERSION,'run_id':self.id,'state':self.state,
                'index':e.index,'max_steps':e.config.max_steps,
                'utc':(e.config.start+timedelta(seconds=e.index*900)).isoformat(),
                'total_kwh':e.totals,'latest':e.latest,'recovered':self.recovered,
                'error':self.error,'physical_control':False,'measurement_provenance':'NOT_VERIFIED',
                'database':str(self.journal.path)}

    def start(self):
        with self.lock:
            if self.engine is None or self.state=='COMPLETE':raise ValueError('No resumable research run')
            if self.error:raise ValueError('Error latched; restore last committed checkpoint')
            self.journal.state(self.id,'RUNNING')
            self.state='RUNNING'
            return self.status()

    def pause(self):
        with self.lock:
            if self.engine is None:raise ValueError('No research run')
            if self.state not in ('COMPLETE','FAULT_LATCHED'):
                self.journal.state(self.id,'PAUSED');self.state='PAUSED'
            return self.status()

    def advance(self,count=1):
        if type(count) is not int or not 1<=count<=96:raise ValueError('count must be 1..96')
        with self.lock:
            if self.engine is None or self.state in ('COMPLETE','FAULT_LATCHED'):
                raise ValueError('No research run available for stepping')
            if self.error:raise ValueError('Error latched; reload before resuming')
            for _ in range(count):
                if self.state=='COMPLETE':break
                idx=self.engine.index
                try:
                    doc=self.engine.advance()
                    self.journal.step(self.id,idx,doc,self.engine.snapshot(),self.engine.index>=self.engine.config.max_steps)
                    if self.engine.index>=self.engine.config.max_steps:self.state='COMPLETE'
                except Exception as exc:
                    self.error=type(exc).__name__;self.state='FAULT_LATCHED'
                    raise
            return self.status()

    def auto_step(self):
        with self.lock:
            if self.state=='RUNNING' and not self.error:
                self.autocount+=1
                if self.autocount%2==0:self.advance(1)

    def history(self,limit=300,after=-1,run_id=None):
        with self.lock:return self.journal.rows(run_id or self.id,limit,after) if (run_id or self.id) else []
