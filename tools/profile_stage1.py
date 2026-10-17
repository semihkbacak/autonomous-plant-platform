"""Measure native simulator calculation separately from synthetic automatic wait.

--toy-sessions replaces GES/RES with tiny deterministic synthetic fixtures;
results from that mode must NEVER be presented as complete PV/wind physics timing.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time

from stage1.engine import ClockConfig
from stage1.controller import Coordinator
from app.sim_runtime import SolarSession,WindSession

class TestSolar(SolarSession):
    def _prepare(self):self._engine=object()
    def _compute(self,i):
        return {'power_kw':4,'energy_kwh':1,'units':[{'id':'S','kw':4}],
                'conditions':{'source':'TOY_NOT_PVLIB'},'end_utc':'2026-01-01T00:15:00+00:00'}

class TestWind(WindSession):
    def _prepare(self):self._engine=object()
    def _compute(self,i):
        return {'power_kw':8,'energy_kwh':2,'units':[{'id':'W','kw':8}],
                'conditions':{'source':'TOY_NOT_WIND_PHYSICS'},'end_utc':'2026-01-01T00:15:00+00:00'}

def profile(steps=4,toy=False):
    if not 1<=steps<=96:raise ValueError('steps must be 1..96')
    with TemporaryDirectory(prefix='app-stage1-profile-') as d:
        kwargs={'solar_factory':TestSolar,'wind_factory':TestWind} if toy else {}
        c=Coordinator(Path(d)/'profile.sqlite3',**kwargs)
        c.create(ClockConfig('2026-01-01T00:00:00+00:00',1))
        t0=perf_counter();cpu=process_time()
        c.advance(steps)
        wall=perf_counter()-t0;cpu_used=process_time()-cpu
        p=c.profile
        return {'scope':'SIMULATION_ONLY','fixture':'HES_NATIVE_GES_RES_TOY' if toy else 'NATIVE_HES_GES_RES',
                'steps':steps,'elapsed_wall_s':round(wall,5),'elapsed_process_cpu_s':round(cpu_used,5),
                'engine_compute_and_checkpoint_s':round(p['compute_s'],5),
                'sqlite_transaction_s':round(p['journal_s'],5),
                'other_and_dispatch_read_s':round(max(0,wall-p['compute_s']-p['journal_s']),5),
                'step_mean_wall_s':round(wall/steps,5),
                'automatic_wait_s':0,
                'automatic_modes':{'NORMAL':'one step every two 1-second loop ticks',
                                   'FAST':'one step per loop tick',
                                   'MAX':'up to four steps per loop tick'},
                'note':'No auto-mode sleep included in this microbenchmark; real PV/wind timing requires pvlib environment.'}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--toy-sessions',action='store_true')
    p.add_argument('--steps',type=int,default=4)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    result=profile(args.steps,args.toy_sessions)
    content=json.dumps(result,indent=2,ensure_ascii=False)+'\n'
    print(content)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(content,encoding='utf-8')
