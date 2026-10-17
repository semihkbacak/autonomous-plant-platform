"""All-or-nothing SQLite history/checkpoint with chain integrity, Windows-safe close.

A verified SHA chain detects accidental/unauthorized edits, not a cryptographic
signature. An attacker with DB write access can rewrite chain and snapshots.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timezone
from hashlib import sha256
from pathlib import Path
import json
import sqlite3
from threading import RLock
from uuid import uuid4

from advanced_v2.engine import AdvancedEngine, ResearchConfig, canonical
from advanced_v2.physics import SCOPE, VERSION

ZERO = '0'*64
DDL = '''
CREATE TABLE IF NOT EXISTS research_runs (
 id TEXT PRIMARY KEY, config TEXT NOT NULL, config_sha TEXT NOT NULL,
 state TEXT NOT NULL, step_index INTEGER NOT NULL, snapshot BLOB NOT NULL,
 snapshot_sha TEXT NOT NULL, chain_sha TEXT NOT NULL, created_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS research_steps (
 run_id TEXT NOT NULL REFERENCES research_runs(id) ON DELETE CASCADE,
 step_index INTEGER NOT NULL, utc_start TEXT NOT NULL, utc_end TEXT NOT NULL,
 payload TEXT NOT NULL, payload_sha TEXT NOT NULL,
 PRIMARY KEY(run_id,step_index)
);
CREATE TABLE IF NOT EXISTS research_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_research_history ON research_steps(run_id,step_index);
'''


class Journal:
    def __init__(self,path):
        self.path=Path(path).expanduser().resolve()
        self.lock=RLock()
        if self.path.exists():
            with self.connection() as db:self._integrity(db)

    @contextmanager
    def connection(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(str(self.path),timeout=20)
        db.row_factory=sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA busy_timeout=20000')
            yield db
        finally:db.close()  # unlike `with sqlite3.connect`, explicit close on Windows

    @staticmethod
    def _integrity(db):
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':
            raise ValueError('Damaged research DB; refusing to overwrite')
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'research_runs','research_steps','research_meta'}.issubset(names):
            raise ValueError('Not an advanced research journal; refusing overwrite')

    def create(self,engine:AdvancedEngine):
        cp=engine.snapshot()
        config=canonical({'config':engine.config.__dict__,'version':VERSION}).decode('ascii')
        rid=uuid4().hex
        with self.lock,self.connection() as db:
            db.executescript(DDL)
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO research_runs VALUES(?,?,?,?,?,?,?,?,?)',(
                    rid,config,sha256(config.encode()).hexdigest(),'PAUSED',0,cp,
                    sha256(cp).hexdigest(),ZERO,datetime.now(timezone.utc).isoformat()))
                db.execute("INSERT INTO research_meta VALUES('active',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(rid,))
                db.commit()
            except Exception:db.rollback();raise
        return rid

    def restore(self):
        if not self.path.exists():return None
        with self.lock,self.connection() as db:
            r=db.execute("SELECT r.* FROM research_runs r JOIN research_meta m ON m.value=r.id WHERE m.key='active'").fetchone()
            if r is None:return None
            if sha256(r['config'].encode()).hexdigest()!=r['config_sha'] or sha256(r['snapshot']).hexdigest()!=r['snapshot_sha']:
                raise ValueError('Research metadata/checkpoint integrity failure')
            engine=AdvancedEngine.recover(r['snapshot'])
            if engine.index!=r['step_index']:raise ValueError('Clock/checkpoint index mismatch')
            config_doc=json.loads(r['config'])
            if config_doc['config']!=engine.config.__dict__ or config_doc['version']!=VERSION:
                raise ValueError('Research configuration checksum mismatch')
            chain=ZERO
            count=0
            prev_end=None
            rows=db.execute('SELECT * FROM research_steps WHERE run_id=? ORDER BY step_index',(r['id'],))
            for rec in rows:
                if rec['step_index']!=count:raise ValueError('Missing/reordered research time slot')
                encoded=rec['payload'].encode('ascii')
                digest=sha256(encoded).hexdigest()
                if digest!=rec['payload_sha']:raise ValueError('Modified research sample')
                doc=json.loads(encoded)
                if (doc['index']!=count or doc['utc_start']!=rec['utc_start'] or doc['utc_end']!=rec['utc_end'] or
                    set(doc['rows'])!={'HES','GES','RES'} or doc['scope']!=SCOPE):
                    raise ValueError('Incompatible/incomplete research slot')
                if prev_end is not None and prev_end!=rec['utc_start']:
                    raise ValueError('Discontinuous UTC time history')
                prev_end=rec['utc_end']
                chain=sha256((chain+'|'+digest).encode('ascii')).hexdigest()
                count+=1
            if count!=engine.index or chain!=r['chain_sha']:
                raise ValueError('Research sample chain does not match checkpoint')
            return {'id':r['id'],'engine':engine,
                    'state':'COMPLETE' if r['state']=='COMPLETE' else 'PAUSED_RECOVERED'}

    def step(self,rid,expected_index,doc,checkpoint,complete=False):
        encoded=canonical(doc).decode('ascii')
        digest=sha256(encoded.encode('ascii')).hexdigest()
        snap_sha=sha256(checkpoint).hexdigest()
        with self.lock,self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                old=db.execute('SELECT step_index,chain_sha FROM research_runs WHERE id=?',(rid,)).fetchone()
                if not old or old['step_index']!=expected_index:raise ValueError('Concurrent step/write conflict')
                db.execute('INSERT INTO research_steps VALUES(?,?,?,?,?,?)',(
                    rid,expected_index,doc['utc_start'],doc['utc_end'],encoded,digest))
                chain=sha256((old['chain_sha']+'|'+digest).encode('ascii')).hexdigest()
                upd=db.execute('UPDATE research_runs SET step_index=?,snapshot=?,snapshot_sha=?,chain_sha=?,state=? '
                               'WHERE id=? AND step_index=?',(
                    expected_index+1,checkpoint,snap_sha,chain,'COMPLETE' if complete else 'PAUSED',rid,expected_index))
                if upd.rowcount!=1:raise ValueError('Lost research commit race')
                db.commit()
            except Exception:db.rollback();raise

    def state(self,rid,state):
        if state not in ('RUNNING','PAUSED','COMPLETE'):raise ValueError('Invalid research state')
        with self.lock,self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                if db.execute('UPDATE research_runs SET state=? WHERE id=?',(state,rid)).rowcount!=1:
                    raise ValueError('Unknown research run')
                db.commit()
            except Exception:db.rollback();raise

    def rows(self,rid,limit=300,after=-1):
        if not self.path.exists():return []
        with self.connection() as db:
            found=db.execute('SELECT payload FROM research_steps WHERE run_id=? AND step_index>? '
                             'ORDER BY step_index LIMIT ?',(rid,after,min(limit,10000))).fetchall()
            return [json.loads(x[0]) for x in found]

    def runs(self):
        if not self.path.exists():return []
        with self.connection() as db:
            return [dict(x) for x in db.execute('SELECT id,step_index,state,created_utc FROM research_runs '
                                               'ORDER BY created_utc DESC LIMIT 50')]

    def backup(self,target):
        target=Path(target).resolve()
        if target.exists() or target==self.path:raise FileExistsError('Backup already exists')
        target.parent.mkdir(parents=True,exist_ok=True)
        with self.lock,self.connection() as db:
            other=sqlite3.connect(str(target))
            try:db.backup(other)
            finally:other.close()
        return {'path':str(target),'sha256':sha256(target.read_bytes()).hexdigest()}
