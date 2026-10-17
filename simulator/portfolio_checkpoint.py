"""Offline full HES/GES/RES synthetic model checkpoint at a paused boundary.

Not a hot/atomic checkpoint of three asynchronously running production systems.
Pause all three demo engines first. No real equipment support. No pickle.
"""
from __future__ import annotations
from hashlib import sha256
import json
from pathlib import Path
from simulator.hydro import HydroPlantSimulator
from simulator.hydro_checkpoint import encode_checkpoint,decode_checkpoint
from app.sim_runtime import SimulatorSessions,SolarSession,WindSession

MAX_BYTES=350_000


def pack_portfolio(hydro:HydroPlantSimulator, sessions:SimulatorSessions) -> bytes:
    if hydro.auto_tick_enabled or sessions.ges.running or sessions.res.running:
        raise ValueError('Stop and pause all synthetic engines before creating a checkpoint')
    payload={
        'version':1,
        'scope':'SYNTHETIC_PAUSED_PORTFOLIO_NO_FIELD_IO',
        'hes':json.loads(encode_checkpoint(hydro)),
        'ges':json.loads(sessions.ges.export_replay()),
        'res':json.loads(sessions.res.export_replay()),
        'clock_counter':sessions._clock_counter,
    }
    if type(sessions._clock_counter)!=int or not 0<=sessions._clock_counter<=10**12:
        raise ValueError('Invalid synthetic clock counter')
    raw=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    envelope={'payload':payload,'sha256':sha256(raw).hexdigest()}
    doc=json.dumps(envelope,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(doc)>MAX_BYTES:raise ValueError('Portfolio snapshot exceeds local research limit')
    return doc


def unpack_portfolio(raw:bytes) -> tuple[HydroPlantSimulator,SimulatorSessions]:
    if not isinstance(raw,bytes) or not raw or len(raw)>MAX_BYTES:
        raise ValueError('Invalid portfolio snapshot length')
    try:
        doc=json.loads(raw)
        payload=doc['payload']
        canonical=json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
        if doc['sha256']!=sha256(canonical).hexdigest():raise ValueError('Portfolio checksum mismatch')
        if payload['version']!=1 or payload['scope']!='SYNTHETIC_PAUSED_PORTFOLIO_NO_FIELD_IO':
            raise ValueError('Unknown portfolio snapshot')
        h=decode_checkpoint(json.dumps(payload['hes'],sort_keys=True,separators=(',',':')).encode())
        sessions=SimulatorSessions()
        sessions.ges=SolarSession.import_replay(json.dumps(payload['ges'],sort_keys=True,separators=(',',':')).encode())
        sessions.res=WindSession.import_replay(json.dumps(payload['res'],sort_keys=True,separators=(',',':')).encode())
        c=payload['clock_counter']
        if type(c)!=int or not 0<=c<=10**12:raise ValueError('Invalid clock counter')
        sessions._clock_counter=c
        if h.auto_tick_enabled or sessions.ges.running or sessions.res.running:
            raise ValueError('Only paused synthetic portfolio snapshots can be restored')
        return h,sessions
    except (KeyError,TypeError,ValueError,IndexError) as exc:
        raise ValueError('Invalid/incompatible synthetic portfolio checkpoint') from exc


def save_portfolio(path: str|Path, hydro:HydroPlantSimulator, sessions:SimulatorSessions)->dict:
    file=Path(path)
    if file.exists():raise FileExistsError('Cannot replace an existing portfolio snapshot')
    file.parent.mkdir(parents=True,exist_ok=True)
    raw=pack_portfolio(hydro,sessions)
    with file.open('xb') as out:out.write(raw)
    return {'path':str(file),'sha256':sha256(raw).hexdigest(),
            'scope':'OFFLINE_SYNTHETIC_CHECKPOINT_NOT_LIVE_SITE'}


def load_portfolio(path: str|Path, expected_sha256:str):
    file=Path(path)
    if file.stat().st_size>MAX_BYTES:raise ValueError('Oversized portfolio checkpoint')
    raw=file.read_bytes()
    if sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Portfolio file hash mismatch')
    return unpack_portfolio(raw)
