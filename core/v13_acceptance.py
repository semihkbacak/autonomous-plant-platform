"""Evidence gate metadata only. Cannot create regulatory or OEM approvals."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime,timezone
from pathlib import Path
from hashlib import sha256
import json

GATES = ('OEM_GES','OEM_HES','OEM_RES','PROCESS_SAFETY','OT_SECURITY','HIL_FAT','SAT','PILOT','WINDOWS_RELEASE')


def evidence_inventory(root:Path|str|None) -> dict:
    base=Path(root) if root else None
    items=[]
    for gate in GATES:
        found=[]
        folder=base/gate if base else None
        if folder and folder.is_dir() and not folder.is_symlink():
            for f in sorted(folder.iterdir()):
                if f.is_file() and not f.is_symlink() and f.suffix.lower() in ('.pdf','.json','.csv','.txt') and 0<f.stat().st_size<=10_000_000:
                    found.append({'name':f.name,'sha256':sha256(f.read_bytes()).hexdigest()})
        items.append({'gate':gate,'documents':found,'approval':'NOT_INDEPENDENTLY_VERIFIED'})
    return {'eligible_for_real_site_control':False,'count_unverified':len(GATES),
            'evidence':items,'scope':'DOCUMENT_INVENTORY_NOT_SIGNOFF'}


def acceptance_template(site_id:str, plant:str) -> dict:
    if not site_id or len(site_id)>48 or not site_id.replace('_','').replace('-','').isalnum():
        raise ValueError('Invalid site id')
    if plant not in ('HES','GES','RES'):
        raise ValueError('Unknown plant')
    return {'site_id':site_id,'plant':plant,'created_utc':datetime.now(timezone.utc).isoformat(),
            'tests':[{'gate':gate,'criterion':'SITE_SPECIFIC_CRITERIA_REQUIRED',
                      'witness':'NOT_ASSIGNED','result':'NOT_RUN','evidence_hash':None}
                     for gate in GATES],
            'authorized_to_control':False,'vendor_validated':False,
            'operator_signoff':None,'independent_reviewer_signoff':None}
