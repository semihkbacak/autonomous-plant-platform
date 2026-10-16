"""Verify required sample fixtures in a fresh clone, no external services."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "WINDOWS_PACKAGE_MANIFEST.json"


def verify() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = manifest["required_fixtures_sha256"]
    for filename, digest in assets.items():
        file = ROOT / filename
        if not file.is_file():
            raise FileNotFoundError(f"Missing test/research fixture in checkout: {filename}")
        actual = hashlib.sha256(file.read_bytes()).hexdigest()
        if actual != digest:
            raise ValueError(f"Fixture SHA256 mismatch: {filename}")
    print(f"{len(assets)} required release files present; SHA-256 OK")


if __name__ == "__main__":
    try:
        verify()
    except (FileNotFoundError, ValueError) as exc:
        print(f"RELEASE ASSET ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
