"""Offline source integrity / software inventory report; NOT a security certification.

No network, no credentials, no repository writes (unless --output selected).
"""
from __future__ import annotations
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
FILE_EXT={'.py','.txt','.md','.json','.yaml','.yml','.sh','.cmd','.ps1','.csv'}
TOP_FOLDERS=('app','core','desktop','research_v2','simulator','scripts','tests','tools','.github','docs')
FILE_MAX=5_000_000

def dependencies():
    packages={}
    for dist in metadata.distributions():
        name=dist.metadata.get('Name','')
        if name:packages[name.lower()]={'name':name,'version':dist.version,'license':dist.metadata.get('License','UNKNOWN')}
    return [packages[k] for k in sorted(packages)]

def source_fingerprint():
    result=[]
    for folder in TOP_FOLDERS:
        base=ROOT/folder
        if not base.exists():continue
        for path in sorted(base.rglob('*')):
            if not path.is_file() or any(p.startswith('.') and p not in ('.github',) for p in path.relative_to(ROOT).parts):continue
            if path.suffix not in FILE_EXT or path.stat().st_size>FILE_MAX:continue
            result.append({'path':str(path.relative_to(ROOT)).replace('\\','/'),
                           'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                           'bytes':path.stat().st_size})
    return result

def report():
    from datetime import datetime,timezone
    return {
        'tool':'Autonomous Plant research-only supply-chain inventory',
        'generated_utc':datetime.now(timezone.utc).isoformat(),
        'field_control_authorized':False,'security_certified':False,
        'production_release_approved':False,
        'source_sha256':source_fingerprint(),
        'installed_packages':dependencies(),
        'caveats':['Third-party OEM ZIP legal and provenance audit outstanding',
                   'No remote vulnerability database consulted',
                   'Inventory is not a vulnerability scan, code signature, or SBOM attestation'],
    }

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    data=json.dumps(report(),sort_keys=True,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(data+'\n',encoding='utf-8')
        print('Inventory:',args.output)
    else:print(data)
    return 0
if __name__=='__main__':raise SystemExit(main())
