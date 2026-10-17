"""Create a one-day SYNTHETIC wind historian for offline demonstration.

Never overwrites an existing historian and never touches field equipment.
"""
from __future__ import annotations
import json
import os
import sqlite3
from contextlib import closing
import uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def default_history_path(root=ROOT):
    return Path(root)/'outputs/res_v20_synthetic_demo/wind_history.sqlite3'


def inspect_res_history(path):
    path=Path(path)
    if not path.is_file():raise FileNotFoundError(path)
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Corrupt RES historian')
        n=db.execute('SELECT count(*) FROM wind_runs').fetchone()[0]
        m=db.execute('SELECT count(*) FROM wind_intervals').fetchone()[0]
    if n<1 or m<1:raise ValueError('Incomplete RES historian; not overwriting')
    return {'path':str(path.resolve()),'runs':n,'intervals':m,'source':'SYNTHETIC_WIND_NOT_REAL_SITE'}


def ensure_synthetic_res_history(path=None):
    path=Path(path) if path is not None else default_history_path()
    if path.exists():return inspect_res_history(path)
    from simulator.wind_suite import run_scenario
    from simulator.wind_history import WindHistorian
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.stem+'_tmp_'+uuid.uuid4().hex+'.sqlite3')
    try:
        WindHistorian(tmp).save_run('SYNTHETIC_RES_V20_OFFLINE_DEMO',run_scenario('BASELINE'))
        inspect_res_history(tmp)
        if path.exists():return inspect_res_history(path)
        os.replace(tmp,path)
        return inspect_res_history(path)
    finally:
        tmp.unlink(missing_ok=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--db');args=p.parse_args()
    print(json.dumps(ensure_synthetic_res_history(args.db),ensure_ascii=False))
