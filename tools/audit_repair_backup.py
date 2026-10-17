"""Lossless off-project backup for local synthetic simulator source repairs.

Never stores duplicate tests under the pytest root. No destructive overwrites.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent.parent

def backup_files(paths: list[str], *, root: Path = ROOT, dest: Path | None = None) -> Path:
    root = root.resolve()
    if dest is None:
        dest = root.parent / 'AutonomousPlant_RepairBackups'
    dest = dest.expanduser().resolve()
    if dest == root or root in dest.parents:
        raise ValueError('Backups must reside OUTSIDE the project root')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = dest / stamp
    records = []
    for name in paths:
        path = (root / name).resolve()
        if not path.is_file() or root not in path.parents or path.is_symlink():
            raise ValueError('Unsafe/missing source: ' + name)
        records.append((path, path.relative_to(root)))
    target.mkdir(parents=True, exist_ok=False)
    try:
        manifest = {}
        for source, rel in records:
            output = target / rel
            output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,output)
            manifest[rel.as_posix()] = hashlib.sha256(output.read_bytes()).hexdigest()
        (target / 'MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    except Exception:
        shutil.rmtree(target)
        raise
    return target

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('files',nargs='+',help='Project-relative file paths')
    p.add_argument('--dest',type=Path)
    a=p.parse_args()
    print(backup_files(a.files,dest=a.dest))
