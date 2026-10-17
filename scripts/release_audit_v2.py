"""Offline distribution preflight; does not claim certification or vulnerability clearance."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
def main():
 manifest=json.loads((ROOT/'WINDOWS_PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
 for name,expected in manifest['required_fixtures_sha256'].items():
  p=ROOT/name
  if not p.is_file():raise SystemExit('MISSING '+name)
  if hashlib.sha256(p.read_bytes()).hexdigest()!=expected:raise SystemExit('HASH MISMATCH '+name)
 print('FIVE LEGACY FIXTURES VERIFIED; licensing and OEM provenance not certified')
if __name__=='__main__':main()
