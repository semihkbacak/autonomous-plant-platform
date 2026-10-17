"""Exact, schema-versioned HES *synthetic* in-memory checkpoint.

No industrial I/O. Never deserialize pickles; JSON model validation and a checksum
protect against inadvertent corruption, not a malicious writer or OT safety risks.
The checkpoint does NOT represent a physical powerplant state.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
from core.models import PlantState, AlarmHistoryEntry
from simulator.hydro import HydroPlantSimulator

SCHEMA=1
LIMIT_BYTES=2_000_000


def canonical(document: dict) -> bytes:
    return json.dumps(document, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def encode_checkpoint(sim: HydroPlantSimulator) -> bytes:
    with sim._lock:
        payload = {
            'schema':SCHEMA,
            'scope':'LOCAL_SYNTHETIC_HES_NO_OT',
            'state':sim.state.model_dump(mode='json'),
            'start_progress':dict(sim._start_progress),
            'stop_progress':dict(sim._stop_progress),
            'auto_tick_enabled':sim.auto_tick_enabled,
            'plant_power_target_mw':sim.plant_power_target_mw,
            'alarm_history':[a.model_dump(mode='json') for a in sim._alarm_history],
            'active_alarm_keys':sorted((list(x) for x in sim._active_alarm_keys),
                                        key=lambda x:(x[0],x[1] or '')),
        }
    raw = canonical(payload)
    envelope = {'payload':payload, 'sha256':hashlib.sha256(raw).hexdigest()}
    data=canonical(envelope)+b'\n'
    if len(data)>LIMIT_BYTES:raise ValueError('Checkpoint too large')
    return data


def decode_checkpoint(raw: bytes) -> HydroPlantSimulator:
    if not isinstance(raw,bytes) or not raw or len(raw)>LIMIT_BYTES:
        raise ValueError('Invalid checkpoint size')
    try:
        doc=json.loads(raw)
        payload=doc['payload']
        if doc['sha256']!=hashlib.sha256(canonical(payload)).hexdigest():
            raise ValueError('Checkpoint content hash mismatch')
        if payload['schema']!=SCHEMA or payload['scope']!='LOCAL_SYNTHETIC_HES_NO_OT':
            raise ValueError('Unrecognized synthetic checkpoint version/scope')
        state=PlantState.model_validate(payload['state'])
        unit_ids={u.unit_id for u in state.units}
        if unit_ids!={'UNIT_1','UNIT_2'} or len(state.units)!=2:
            raise ValueError('Unexpected hydro simulator unit IDs')
        def progress(field):
            p=payload[field]
            if set(p)!=unit_ids or any(type(v)!=int or not 0<=v<=1_000_000 for v in p.values()):
                raise ValueError('Invalid hydro progress checkpoint')
            return p
        start,stop=progress('start_progress'),progress('stop_progress')
        auto=payload['auto_tick_enabled']
        target=payload['plant_power_target_mw']
        if type(auto)!=bool or (target is not None and
            (type(target) not in (float,int) or not math.isfinite(target) or target<0)):
            raise ValueError('Invalid hydro runtime fields')
        history=[AlarmHistoryEntry.model_validate(v) for v in payload['alarm_history']]
        keys=set()
        for code,unit in payload['active_alarm_keys']:
            if type(code)!=str or (unit is not None and unit not in unit_ids):
                raise ValueError('Invalid alarm key')
            keys.add((code,unit))
        sim=HydroPlantSimulator()
        with sim._lock:
            sim.state=state
            sim._start_progress=start
            sim._stop_progress=stop
            sim.auto_tick_enabled=auto
            sim.plant_power_target_mw=target
            sim._alarm_history=history
            sim._active_alarm_keys=keys
        return sim
    except (KeyError,TypeError,IndexError,ValueError) as exc:
        raise ValueError('Invalid or modified synthetic HES checkpoint') from exc


def save_checkpoint(sim: HydroPlantSimulator, filename: str | Path) -> dict:
    file=Path(filename)
    if file.exists():raise FileExistsError('Checkpoint exists; no overwrite')
    file.parent.mkdir(parents=True,exist_ok=True)
    raw=encode_checkpoint(sim)
    with file.open('xb') as out:out.write(raw)
    return {'path':str(file),'sha256':hashlib.sha256(raw).hexdigest(),
            'scope':'SYNTHETIC_ONLY_NOT_OEM_VALIDATED'}


def load_checkpoint(filename: str | Path, expected_sha256: str) -> HydroPlantSimulator:
    path=Path(filename)
    if path.stat().st_size>LIMIT_BYTES:raise ValueError('Checkpoint oversized')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('Checkpoint file SHA-256 mismatch')
    return decode_checkpoint(raw)
