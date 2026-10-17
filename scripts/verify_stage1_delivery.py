"""Offline SHA256 source release inventory check; no network/dependencies."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'ASAMA1_DOSYA_MANIFEST.json'


def main():
    try:
        obj = json.loads(MANIFEST.read_text(encoding='utf-8'))
        assert obj['scope'] == 'STAGE1_SYNTHETIC_HES_GES_RES_NO_OT'
        files=obj['files']
        if not files:raise ValueError('Empty inventory')
        for rel,metadata in files.items():
            path=Path(rel)
            if path.is_absolute() or '..' in path.parts or path.as_posix()!=rel:
                raise ValueError('Unsafe manifest path: '+rel)
            full=ROOT / path
            if not full.is_file() or full.is_symlink():
                raise ValueError('Missing/invalid project asset: '+rel)
            if full.stat().st_size != metadata['bytes']:
                raise ValueError('Unexpected file size: '+rel)
            if hashlib.sha256(full.read_bytes()).hexdigest()!=metadata['sha256']:
                raise ValueError('SHA-256 mismatch: '+rel)
        print(f'[STAGE1] Verified {len(files)} project files; SHA-256 OK. Offline simulation only.')
        return 0
    except (KeyError,ValueError,FileNotFoundError,AssertionError,OSError) as exc:
        print('[STAGE1] ASSET VERIFICATION FAILED: '+str(exc),file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
