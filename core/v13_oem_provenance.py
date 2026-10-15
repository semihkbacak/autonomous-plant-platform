"""Claim-based OEM parameter registry, no independent attestation."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
import json

DEVICES={'PV_MODULE','SOLAR_INVERTER','HYDRO_TURBINE','WIND_TURBINE'}

@dataclass(frozen=True)
class Claim:
    device_type:str
    vendor:str
    model:str
    parameter:str
    value:float
    unit:str
    source_sha256:str
    source_kind:str

    def __post_init__(self):
        if self.device_type not in DEVICES or self.source_kind not in ('DECLARED_DATASHEET','RESEARCH_ESTIMATE','FIELD_EXPORT'):
            raise ValueError('Unknown device/source kind')
        for string in (self.vendor,self.model,self.parameter,self.unit):
            if not isinstance(string,str) or not 1<=len(string)<=128 or any(x in string for x in '\r\n\x00'):
                raise ValueError('Invalid parameter identity')
        if isinstance(self.value,bool) or not isinstance(self.value,(float,int)) or not isfinite(self.value):
            raise ValueError('Nonfinite OEM parameter value')
        if len(self.source_sha256)!=64 or not all(c in '0123456789abcdef' for c in self.source_sha256):
            raise ValueError('Source requires lowercase sha256 hash')


def review_claims(claims:list[Claim]) -> dict:
    if not claims or len(claims)>20000:
        raise ValueError('Must supply 1..20000 claims')
    identities=[(c.device_type,c.vendor,c.model,c.parameter) for c in claims]
    if len(identities)!=len(set(identities)):
        raise ValueError('Conflicting duplicate OEM claims')
    counts={x:sum(c.source_kind==x for c in claims) for x in ('DECLARED_DATASHEET','RESEARCH_ESTIMATE','FIELD_EXPORT')}
    payload=[c.__dict__ for c in claims]
    return {
        'claim_count':len(claims),'source_kinds':counts,
        'inventory_sha256':sha256(json.dumps(payload,sort_keys=True,allow_nan=False).encode()).hexdigest(),
        'accepted_as_claimed':counts['DECLARED_DATASHEET'],
        'oem_model_certified':False,'site_validated':False,'real_control_ready':False,
        'reason':'SOURCE_HASH_AND_DECLARED_VALUES_DO_NOT_ESTABLISH_AUTHENTICITY',
    }
