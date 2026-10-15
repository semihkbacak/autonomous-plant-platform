"""Offline access-policy/MFA primitives. NOT a deployed identity provider.

Never consider possession of a TOTP code alone as authentication: an externally
verified primary identity and a server-side enrollment are also required.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha1
from hmac import new as hmac_new, compare_digest
from math import isfinite
import struct
from time import time
from typing import Literal

ROLES = {
    'viewer': frozenset({'read_telemetry','read_history'}),
    'analyst': frozenset({'read_telemetry','read_history','export_report','review_model'}),
    'sim_operator': frozenset({'read_telemetry','read_history','simulation_command'}),
    'site_reviewer': frozenset({'read_telemetry','read_history','review_evidence'}),
}
# Physical actuator commands do not exist in this access policy.


def decision(role: str, action: str, *, primary_authenticated: bool,
             mfa_verified: bool, operation_mode: str) -> dict:
    if role not in ROLES or action not in set.union(*(set(x) for x in ROLES.values())):
        return {'allowed':False,'reason':'UNKNOWN_ROLE_OR_ACTION'}
    if not primary_authenticated:
        return {'allowed':False,'reason':'PRIMARY_AUTH_REQUIRED'}
    if operation_mode not in ('SIMULATION','SHADOW'):
        return {'allowed':False,'reason':'UNSUPPORTED_OPERATION_MODE'}
    if action == 'simulation_command' and operation_mode != 'SIMULATION':
        return {'allowed':False,'reason':'SHADOW_READ_ONLY'}
    if action in ('simulation_command','export_report','review_evidence') and not mfa_verified:
        return {'allowed':False,'reason':'MFA_REQUIRED'}
    if action not in ROLES[role]:
        return {'allowed':False,'reason':'ROLE_DENIED'}
    return {'allowed':True,'reason':'POLICY_ALLOWED_OFFLINE_ONLY'}


def totp_code(secret: bytes, counter: int, digits: int = 6) -> str:
    """RFC 4226 / RFC 6238 SHA1 calculation for isolated verification tests."""
    if not isinstance(secret, bytes) or len(secret) < 16:
        raise ValueError('Strong enrolled byte secret required')
    if isinstance(counter,bool) or not isinstance(counter,int) or counter < 0:
        raise ValueError('Invalid time counter')
    if digits not in (6,8):
        raise ValueError('TOTP digits must be six or eight')
    h = hmac_new(secret, struct.pack('>Q',counter),sha1).digest()
    off = h[-1] & 15
    value = struct.unpack('>I',h[off:off+4])[0] & 0x7fffffff
    return str(value%(10**digits)).zfill(digits)


@dataclass
class LocalOtpVerifier:
    """Single-process TOTP verification; NOT HA/distributed replay protection."""
    secret: bytes
    last_accepted_counter: int = -1

    def verify(self, code: str, timestamp_s: float, *, drift_steps: int = 1) -> bool:
        if isinstance(timestamp_s,bool) or not isinstance(timestamp_s,(int,float)) or not isfinite(timestamp_s) or timestamp_s < 0:
            return False
        if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdigit():
            return False
        if drift_steps not in (0,1):
            raise ValueError('Only zero or one drift step supported')
        current = int(timestamp_s//30)
        for c in range(max(0,current-drift_steps),current+drift_steps+1):
            if c > self.last_accepted_counter and compare_digest(totp_code(self.secret,c),code):
                self.last_accepted_counter = c
                return True
        return False
