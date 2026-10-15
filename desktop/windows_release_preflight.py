"""Offline Windows bundle inspection; never code-signs or certifies binaries."""
from __future__ import annotations
import argparse,hashlib,json,platform
from pathlib import Path


def inspect(exe:Path,signature_confirmed:bool=False,antivirus_confirmed:bool=False,
            target_os_tested:bool=False)->dict:
    if not exe.is_file() or exe.suffix.lower()!='.exe':
        return {'built':False,'release_approved':False,'reason':'EXE_NOT_FOUND'}
    data=exe.read_bytes()
    if not data.startswith(b'MZ'):
        return {'built':False,'release_approved':False,'reason':'NOT_PE_FILE'}
    # Manual checkboxes never replace independent signer/AV evidence.
    return {'built':True,'sha256':hashlib.sha256(data).hexdigest(),
            'size_bytes':len(data),'tested_on_host':platform.system(),
            'signature_reported_by_operator':signature_confirmed,
            'av_reported_by_operator':antivirus_confirmed,
            'target_os_reported_by_operator':target_os_tested,
            'release_approved':False,
            'reason':'NEEDS_INDEPENDENT_WINDOWS_TEST_SIGNATURE_AND_ENTERPRISE_APPROVAL',
            'capability':'READ_ONLY_VIEWER_NOT_OT_CONTROLLER'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--exe',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args(); result=inspect(a.exe)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['built'] else 2

if __name__=='__main__':raise SystemExit(main())
