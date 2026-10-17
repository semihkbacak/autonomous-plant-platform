"""CycloneDX-style installed Python inventory; not a vulnerability or license approval."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from importlib import metadata
import json
from pathlib import Path
import re


def document():
    components=[]
    known=set()
    for dist in metadata.distributions():
        name=dist.metadata.get('Name','').strip()
        version=dist.version.strip()
        if not name or not version:continue
        safe=re.sub(r'[-_.]+','-',name).lower()
        key=(safe,version)
        if key in known:continue
        known.add(key)
        components.append({'type':'library','name':name,'version':version,
                           'purl':f'pkg:pypi/{safe}@{version}',
                           'licenses':[], # Never infer licensing permission from metadata.
                           'properties':[{'name':'app:license_review','value':'NOT_VERIFIED'}]})
    components.sort(key=lambda c:(c['name'].lower(),c['version']))
    return {'bomFormat':'CycloneDX','specVersion':'1.6','version':1,
            'metadata':{'timestamp':datetime.now(timezone.utc).isoformat(),
                        'component':{'type':'application','name':'Autonomous Plant Platform',
                                     'version':'2.0-research-rc4'}},
            'components':components}


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--output',required=True)
    args=ap.parse_args(argv)
    target=Path(args.output)
    target.parent.mkdir(parents=True,exist_ok=True)
    payload=document()
    target.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(f"Installed-package SBOM written: {target} ({len(payload['components'])} packages)")
    return 0

if __name__=='__main__':raise SystemExit(main())
