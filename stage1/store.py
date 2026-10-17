"""Transactional SQLite journal for three synchronized synthetic models.

One SQL transaction records HES/GES/RES plus their common checkpoint.
Failure leaves the last committed slot intact. No pickle/untrusted code load.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from stage1.engine import ClockConfig, ThreePlantEngine, canonical, MODEL_REVISION, SCOPE
from stage1 import dispatch as dp

SCHEMA = '''
CREATE TABLE IF NOT EXISTS runs(
 id TEXT PRIMARY KEY, config TEXT NOT NULL, config_sha TEXT NOT NULL,
 step_index INTEGER NOT NULL CHECK(step_index>=0),
 state TEXT NOT NULL CHECK(state IN ('PAUSED','RUNNING','COMPLETE','PAUSED_RECOVERED')),
 checkpoint BLOB NOT NULL, snapshot_sha TEXT NOT NULL, chain_sha TEXT NOT NULL,
 created_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS samples(
 run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
 step_index INTEGER NOT NULL, plant TEXT NOT NULL CHECK(plant IN ('HES','GES','RES')),
 utc_start TEXT NOT NULL, utc_end TEXT NOT NULL,
 power_kw REAL NOT NULL CHECK(power_kw>=0), energy_kwh REAL NOT NULL CHECK(energy_kwh>=0),
 total_kwh REAL NOT NULL CHECK(total_kwh>=0), detail_json TEXT NOT NULL,
 PRIMARY KEY(run_id,step_index,plant)
);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_samples_run_step ON samples(run_id,step_index);
'''
INITIAL_CHAIN='0'*64


class Journal:
    def __init__(self,path: str | Path):
        self.path=Path(path).expanduser().resolve()
        self._lock=RLock()
        # No changes to a missing DB until a run is explicitly created.
        if self.path.exists():
            with self.connection() as con:
                self._check_existing(con)
                con.executescript(dp.SQL)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(str(self.path),timeout=20)
        try:
            con.execute('PRAGMA foreign_keys=ON')
            con.execute('PRAGMA busy_timeout=20000')
            con.row_factory=sqlite3.Row
            yield con
        finally:
            con.close()

    @staticmethod
    def _check_existing(con):
        check=con.execute('PRAGMA quick_check').fetchone()
        if check[0]!='ok':
            raise ValueError('Existing simulation database failed integrity check; not overwriting')
        names={x[0] for x in con.execute('SELECT name FROM sqlite_master WHERE type="table"')}
        if not {'runs','samples','meta'}.issubset(names):
            raise ValueError('Existing simulation DB has unexpected schema; not overwriting')

    def create(self,config:ClockConfig,engine:ThreePlantEngine) -> str:
        cp=engine.snapshot()
        run_id=uuid4().hex
        config_raw=canonical({'config':config.__dict__,'model_revision':MODEL_REVISION}).decode('ascii')
        with self._lock, self.connection() as con:
            # Schema install precedes transaction because executescript commits.
            con.executescript(SCHEMA)
            con.executescript(dp.SQL)
            con.execute('BEGIN IMMEDIATE')
            con.execute('INSERT INTO runs VALUES(?,?,?,?,?,?,?,?,?)',
                        (run_id,config_raw,sha256(config_raw.encode()).hexdigest(),0,'PAUSED',cp,
                         sha256(cp).hexdigest(),INITIAL_CHAIN,datetime.now(timezone.utc).isoformat()))
            con.execute("INSERT INTO meta(key,value) VALUES('active_id',?) "
                        'ON CONFLICT(key) DO UPDATE SET value=excluded.value',(run_id,))
            con.commit()
        return run_id

    def _active_row(self,con):
        row=con.execute("SELECT r.* FROM runs r JOIN meta m ON r.id=m.value WHERE m.key='active_id'").fetchone()
        return row

    def load_active(self,solar_factory=None,wind_factory=None):
        if not self.path.exists(): return None
        with self._lock, self.connection() as con:
            r=self._active_row(con)
            if r is None: return None
            dp.verify_audit(con,r['id'])
            if sha256(r['config'].encode()).hexdigest()!=r['config_sha'] or sha256(r['checkpoint']).hexdigest()!=r['snapshot_sha']:
                raise ValueError('Damaged run metadata or snapshot')
            # Verify the complete chain by streaming ordered rows; a partial or
            # duplicated UTC slot cannot pass recovery.
            chain=INITIAL_CHAIN
            total=0
            all_rows=con.execute('SELECT * FROM samples WHERE run_id=? ORDER BY step_index,plant', (r['id'],))
            slots={}
            for rec in all_rows:
                index=rec['step_index']
                if index >= r['step_index'] or index < 0:
                    raise ValueError('Journal contains out-of-range sample')
                detail=json.loads(rec['detail_json'])
                records=slots.setdefault(index, [])
                records.append({**{k:rec[k] for k in ('step_index','plant','utc_start','utc_end','power_kw','energy_kwh','total_kwh')},
                                'units':detail['units'],'conditions':detail['conditions'],'scope':SCOPE})
                total+=1
                if len(records)==3:
                    if set(x['plant'] for x in records)!={'HES','GES','RES'}:
                        raise ValueError('Incomplete or duplicate portfolio slot')
                    if any(x['utc_start']!=records[0]['utc_start'] or x['utc_end']!=records[0]['utc_end'] for x in records):
                        raise ValueError('Portfolio UTC desynchronization')
                    chain=sha256((chain+'|').encode()+canonical(records)).hexdigest()
            if total != r['step_index']*3 or len(slots)!=r['step_index'] or chain!=r['chain_sha']:
                raise ValueError('Incomplete or modified journal; refusing unsafe resume')
            kwargs={}
            if solar_factory:kwargs['solar_factory']=solar_factory
            if wind_factory:kwargs['wind_factory']=wind_factory
            engine=ThreePlantEngine.recover(r['checkpoint'],**kwargs)
            if engine.index!=r['step_index']:
                raise ValueError('Recovered model index differs from database')
            cfg_doc=json.loads(r['config'])
            if cfg_doc['model_revision']!=MODEL_REVISION or cfg_doc['config']!=engine.config.__dict__:
                raise ValueError('Saved model configuration mismatch')
            if r['step_index'] and any(abs(engine.latest[p]['total_kwh']-engine.totals[p])>1e-6 for p in ('HES','GES','RES')):
                raise ValueError('Recovered model energy mismatch')
            # Running must never restart autonomously after a crash.
            state='PAUSED_RECOVERED' if r['state']=='RUNNING' else r['state']
            if state!=r['state']:
                con.execute('BEGIN IMMEDIATE')
                con.execute('UPDATE runs SET state=? WHERE id=? AND state=?', (state,r['id'],r['state']))
                con.commit()
            return {'run_id':r['id'],'state':state,'engine':engine}

    def set_state(self,run_id,state):
        if state not in ('RUNNING','PAUSED','COMPLETE'):raise ValueError('Unknown run state')
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            cursor=con.execute('UPDATE runs SET state=? WHERE id=?',(state,run_id))
            if cursor.rowcount!=1:raise ValueError('Unknown run')
            con.commit()

    def update_checkpoint(self,run_id,engine:ThreePlantEngine):
        cp=engine.snapshot()
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            cursor=con.execute('UPDATE runs SET checkpoint=?,snapshot_sha=? WHERE id=? AND step_index=?',
                               (cp,sha256(cp).hexdigest(),run_id,engine.index))
            if cursor.rowcount!=1:raise ValueError('Concurrent writer or step mismatch')
            con.commit()

    def advance(self,run_id,prior_index,rows,checkpoint:bytes,complete:bool):
        if len(rows)!=3 or set(x['plant'] for x in rows)!={'HES','GES','RES'}:
            raise ValueError('Atomic step requires exactly HES/GES/RES')
        if any(r['step_index']!=prior_index or r['utc_end']!=rows[0]['utc_end'] for r in rows):
            raise ValueError('Slot index / UTC mismatch')
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            run=con.execute('SELECT step_index,chain_sha,state FROM runs WHERE id=?',(run_id,)).fetchone()
            if run is None or run['step_index']!=prior_index or run['state'] not in ('RUNNING','PAUSED','PAUSED_RECOVERED'):
                con.rollback()
                raise ValueError('Concurrent update, completed session or missing run')
            for r in rows:
                con.execute('INSERT INTO samples VALUES(?,?,?,?,?,?,?,?,?)',
                    (run_id,r['step_index'],r['plant'],r['utc_start'],r['utc_end'],r['power_kw'],
                     r['energy_kwh'],r['total_kwh'],canonical({'units':r['units'],'conditions':r['conditions']}).decode()))
            # Dispatch limit evidence is stored in the SAME atomic slot transaction.
            # SQLite rollback removes the samples, checkpoint and audit alike.
            for r in rows:
                disp=r.get('conditions',{}).get('dispatch',{})
                if disp.get('reason') in ('PHYSICAL_AVAILABILITY_LIMIT','NO_SOLAR_IRRADIANCE',
                                         'WIND_OUTSIDE_SYNTHETIC_CUT_IN_OUT','INSUFFICIENT_HYDRAULIC_RESOURCE'):
                    dp.audit(con,run_id,'DISPATCH_LIMITED',{
                        'plant':r['plant'],'step':prior_index,'utc_start':r['utc_start'],
                        'requested_kw':disp.get('requested_kw'),
                        'available_export_kw':disp.get('available_export_kw'),
                        'actual_kw':r['power_kw'],'reason':disp['reason']},actor='SYNTHETIC_ENGINE')
            # Hash serialized in exactly the same HES/GES/RES sorted order as readback.
            serial=sorted(rows,key=lambda x:x['plant'])
            chain=sha256((run['chain_sha']+'|').encode()+canonical(serial)).hexdigest()
            cur=con.execute('UPDATE runs SET step_index=?,checkpoint=?,snapshot_sha=?,chain_sha=?,state=? '
                            'WHERE id=? AND step_index=?',
                            (prior_index+1,checkpoint,sha256(checkpoint).hexdigest(),chain,
                             'COMPLETE' if complete else run['state'],run_id,prior_index))
            if cur.rowcount!=1:
                con.rollback();raise ValueError('Lost write race')
            con.commit()

    def summaries(self,limit=50):
        if not self.path.exists(): return []
        with self.connection() as con:
            return [dict(r) for r in con.execute('SELECT id,step_index,state,created_utc FROM runs ORDER BY created_utc DESC LIMIT ?', (limit,))]

    def samples(self,run_id:str,limit:int=300,after:int=-1):
        if not self.path.exists():return []
        with self.connection() as con:
            records=con.execute('SELECT * FROM samples WHERE run_id=? AND step_index>? ORDER BY step_index,plant LIMIT ?',
                                (run_id,after,limit)).fetchall()
            return [{**{k:r[k] for k in r.keys() if k!='detail_json'},**json.loads(r['detail_json'])} for r in records]


    def dispatch_request(self,run_id:str,utc_start:str):
        with self._lock,self.connection() as con:
            return dp.active_request(con,run_id,utc_start)

    def add_plan(self,run_id:str,plant:str,start_utc:str,end_utc:str,target_kw:float,interval_minutes:int,config:ClockConfig,current_index:int):
        if plant not in dp.PLANTS:raise ValueError('Unknown plant')
        start,end=dp.utc_time(start_utc),dp.utc_time(end_utc)
        if type(interval_minutes) is not int or interval_minutes not in (15,60,1440):
            raise ValueError('Granularity must be 15/60/1440 minutes')
        if start>=end or (end-start).total_seconds()!=interval_minutes*60:
            raise ValueError('One plan entry must match the selected granularity')
        if not (config.start<=start<end<=config.start+timedelta(days=config.days)):
            raise ValueError('Outside current simulation UTC range')
        if start<config.start+timedelta(seconds=current_index*900):
            raise ValueError('Past or already committed UTC intervals are immutable')
        target_kw=dp.power_kw(target_kw,plant)
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            overlap=con.execute('SELECT id FROM production_plans WHERE run_id=? AND plant=? AND utc_start<? AND utc_end>? LIMIT 1',
                                (run_id,plant,end.isoformat(),start.isoformat())).fetchone()
            if overlap:
                dp.audit(con,run_id,'PLAN_REJECTED',{'plant':plant,'reason':'OVERLAPPING_UTC_SLOT','start':start.isoformat()})
                con.commit();raise ValueError('Overlapping plan interval; remove the future entry before replacing')
            cur=con.execute('INSERT INTO production_plans(run_id,plant,utc_start,utc_end,target_kw,interval_minutes,created_utc) VALUES(?,?,?,?,?,?,?)',
                            (run_id,plant,start.isoformat(),end.isoformat(),target_kw,interval_minutes,datetime.now(timezone.utc).isoformat()))
            dp.audit(con,run_id,'PLAN_CREATED',{'id':cur.lastrowid,'plant':plant,'start':start.isoformat(),'end':end.isoformat(),'target_kw':target_kw})
            con.commit()
            return cur.lastrowid

    def cancel_plan(self,run_id:str,entry_id:int,now_utc:str):
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM production_plans WHERE run_id=? AND id=?',(run_id,entry_id)).fetchone()
            if row is None or row['utc_start']<now_utc:
                dp.audit(con,run_id,'PLAN_DELETE_REJECTED',{'id':entry_id,'reason':'NOT_FUTURE_OR_MISSING'})
                con.commit();raise ValueError('Can remove only future plan entries')
            con.execute('DELETE FROM production_plans WHERE id=?',(entry_id,))
            dp.audit(con,run_id,'PLAN_REMOVED',{'id':entry_id,'plant':row['plant'],'start':row['utc_start'],'end':row['utc_end'],'target_kw':row['target_kw']})
            con.commit()

    def set_manual(self,run_id:str,plant:str,value:float|None):
        if plant not in dp.PLANTS:raise ValueError('Unknown plant')
        if value is not None:value=dp.power_kw(value,plant)
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute('INSERT INTO dispatch_controls(run_id,plant,operation,manual_kw) VALUES(?,?,?,?) ON CONFLICT(run_id,plant) DO UPDATE SET manual_kw=excluded.manual_kw',
                        (run_id,plant,'AUTO',value))
            dp.audit(con,run_id,'MANUAL_SETPOINT',{'plant':plant,'kw':value})
            con.commit()

    def reject_command(self,run_id:str,kind:str,plant:str,reason:str):
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            dp.audit(con,run_id,kind,{'plant':str(plant)[:60], 'reason':str(reason)[:160]})
            con.commit()

    def set_operation(self,run_id:str,plant:str,operation:str,now_utc:str):
        if plant not in dp.PLANTS or operation not in ('AUTO','START','STOP'):
            raise ValueError('Invalid plant or operation')
        with self._lock,self.connection() as con:
            con.execute('BEGIN IMMEDIATE')
            req=dp.active_request(con,run_id,now_utc)[plant]
            if operation=='START' and req['has_plan'] and not (req['manual_kw'] or req['target_kw']):
                dp.audit(con,run_id,'COMMAND_REJECTED',{'plant':plant,'operation':operation,'reason':'NO_ACTIVE_POSITIVE_PLAN'})
                con.commit()
                raise ValueError('START denied: no positive scheduled target at this UTC slot')
            con.execute('INSERT INTO dispatch_controls(run_id,plant,operation,manual_kw) VALUES(?,?,?,NULL) ON CONFLICT(run_id,plant) DO UPDATE SET operation=excluded.operation',
                        (run_id,plant,operation))
            dp.audit(con,run_id,'OPERATOR_COMMAND',{'plant':plant,'operation':operation,'utc':now_utc})
            con.commit()

    def plans(self,run_id:str):
        with self.connection() as con:
            return [dict(x) for x in con.execute('SELECT * FROM production_plans WHERE run_id=? ORDER BY utc_start,plant',(run_id,))]

    def plan_report(self,run_id:str,now_utc:str):
        now=dp.utc_time(now_utc)
        with self.connection() as con:
            rows=con.execute('''SELECT p.*, COALESCE(SUM(s.energy_kwh),0) AS actual_kwh,
                        COUNT(s.step_index) AS recorded_slots
                        FROM production_plans p LEFT JOIN samples s
                          ON s.run_id=p.run_id AND s.plant=p.plant
                         AND s.utc_start>=p.utc_start AND s.utc_end<=p.utc_end
                        WHERE p.run_id=? GROUP BY p.id ORDER BY p.utc_start,p.plant''' ,(run_id,)).fetchall()
            output=[]
            for row in rows:
                r=dict(row)
                start,end=dp.utc_time(r['utc_start']),dp.utc_time(r['utc_end'])
                elapsed_hours=max(0.0,min((now-start).total_seconds(),(end-start).total_seconds())/3600)
                expected=float(r['target_kw'])*int(r['interval_minutes'])/60
                elapsed_expected=float(r['target_kw'])*elapsed_hours
                r.update({'expected_kwh':expected,'elapsed_expected_kwh':elapsed_expected,
                          'deviation_elapsed_kwh':float(r['actual_kwh'])-elapsed_expected,
                          'remaining_expected_kwh':max(0.,expected-elapsed_expected),
                          'status':'NOT_STARTED' if now<=start else 'COMPLETE' if now>=end else 'ACTIVE'})
                output.append(r)
            return output

    def audit_events(self,run_id:str,limit=200):
        with self.connection() as con:
            dp.verify_audit(con,run_id)
            return [dict(x) for x in con.execute('SELECT * FROM dispatch_audit WHERE run_id=? ORDER BY id DESC LIMIT ?',(run_id,limit))]

    def backup(self,dest:Path):
        """Explicit local-only consistent SQLite backup; never overwrite."""
        dest=Path(dest).resolve()
        if dest.exists() or dest==self.path:raise FileExistsError('Backup destination exists')
        dest.parent.mkdir(parents=True,exist_ok=True)
        with self._lock,self.connection() as source:
            target=sqlite3.connect(str(dest))
            try:
                source.backup(target)
            except Exception:
                target.close();dest.unlink(missing_ok=True);raise
            finally:
                target.close()
        return {'file':str(dest),'sha256':sha256(dest.read_bytes()).hexdigest()}
