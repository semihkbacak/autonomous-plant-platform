"""Offline site tag contracts. Does not connect to OPC UA/Modbus/PLC/SCADA."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
import re

PLANTS = {'HES','GES','RES'}
UNITS = {'kW','MW','kWh','MWh','V','A','Hz','m3/s','m','degC','m/s','rpm','bar','mm/s'}

@dataclass(frozen=True)
class Tag:
    site_id: str
    plant: str
    equipment: str
    name: str
    unit: str
    lower: float
    upper: float
    max_age_s: int = 300
    source: str = 'AUTHORIZED_OFFLINE_EXPORT'

    def __post_init__(self):
        for name, val in [('site_id',self.site_id),('equipment',self.equipment),('name',self.name)]:
            if not re.fullmatch('[a-zA-Z0-9_-]{1,48}',val):
                raise ValueError(f'Invalid {name}')
        if self.plant not in PLANTS or self.unit not in UNITS:
            raise ValueError('Invalid plant or engineering unit')
        if self.source != 'AUTHORIZED_OFFLINE_EXPORT':
            raise ValueError('Unknown offline source')
        if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not isfinite(x)
               for x in (self.lower,self.upper)) or self.lower >= self.upper:
            raise ValueError('Invalid bounds')
        if isinstance(self.max_age_s,bool) or not isinstance(self.max_age_s,int) or not 1<=self.max_age_s<=86400:
            raise ValueError('Invalid max age')


def validate_register(tags: list[Tag]) -> dict:
    if not 1 <= len(tags) <= 10000:
        raise ValueError('Invalid tag count')
    ids=[(t.site_id,t.plant,t.equipment,t.name) for t in tags]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate measurement contract')
    return {'tags':len(tags),'source':'OFFLINE_ONLY', 'physical_control_capable':False,
            'independent_asset_mapping_verified':False}


def check_measurement(tag: Tag, value: float, unit: str, timestamp_utc:datetime,
                      now_utc:datetime, quality: str) -> dict:
    if timestamp_utc.tzinfo is None or timestamp_utc.utcoffset()!=timedelta(0):
        return {'usable':False,'reason':'TIMESTAMP_NOT_UTC'}
    if now_utc.tzinfo is None or now_utc.utcoffset()!=timedelta(0):
        return {'usable':False,'reason':'CLOCK_NOT_UTC'}
    if unit != tag.unit:
        return {'usable':False,'reason':'UNIT_MISMATCH'}
    if isinstance(value,bool) or not isinstance(value,(float,int)) or not isfinite(value):
        return {'usable':False,'reason':'NONFINITE_VALUE'}
    if quality != 'GOOD':
        return {'usable':False,'reason':'SOURCE_QUALITY_BAD'}
    age=(now_utc-timestamp_utc).total_seconds()
    if age < -2:
        return {'usable':False,'reason':'FUTURE_TIMESTAMP'}
    if age > tag.max_age_s:
        return {'usable':False,'reason':'STALE_DATA'}
    if not tag.lower <= value <= tag.upper:
        return {'usable':False,'reason':'RANGE_VIOLATION'}
    return {'usable':True,'reason':'STRUCTURALLY_VALID_UNVERIFIED_PROVENANCE',
            'field_calibrated':False,'source_authenticated':False}
