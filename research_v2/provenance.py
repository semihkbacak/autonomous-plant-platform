"""Local read-only CSV import checks; hashes are integrity metadata, NOT trust proof."""
from __future__ import annotations
import csv
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any
from research_v2.workspace import parse_utc,valid_power

MAX_CSV_BYTES=4_000_000

def validate_offline_csv(raw:bytes, *, expected_site_id: str, source_label:str, calibrated:bool=False) -> dict[str,Any]:
    if not isinstance(raw,bytes) or len(raw)>MAX_CSV_BYTES or not raw:
        raise ValueError('CSV empty or oversized')
    if not expected_site_id or not expected_site_id.isascii() or not source_label.strip() or len(source_label)>100:
        raise ValueError('Missing provenance metadata')
    from research_v2.workspace import valid_id
    valid_id(expected_site_id)
    try:
        content=raw.decode('utf-8-sig')
    except UnicodeError as exc:
        raise ValueError('CSV must be UTF-8') from exc
    records=list(csv.DictReader(StringIO(content)))
    if len(records)>10000 or not records:raise ValueError('CSV must have 1..10000 measurements')
    required={'site_id','timestamp_utc','power_kw','quality'}
    if not required.issubset(set(records[0])):raise ValueError('CSV must include site_id,timestamp_utc,power_kw,quality')
    previous=None;values=[]
    for row in records:
        if row['site_id']!=expected_site_id:raise ValueError('Unexpected site identifier')
        if row['quality']!='GOOD':raise ValueError('Only GOOD records allowed for comparison')
        at=parse_utc(row['timestamp_utc'])
        if previous is not None and at<=previous:raise ValueError('Timestamps must be strictly increasing')
        previous=at
        try: value=valid_power(float(row['power_kw']))
        except (TypeError,ValueError) as exc:raise ValueError('Invalid measured power') from exc
        values.append({'timestamp_utc':at.isoformat(),'power_kw':value})
    return {'status':'QUARANTINED_UNVERIFIED','sha256':sha256(raw).hexdigest(),
            'source_label':source_label,'site_id':expected_site_id,'claimed_calibrated':bool(calibrated),
            'independently_verified':False,'rows':len(values),'measurements':values}
