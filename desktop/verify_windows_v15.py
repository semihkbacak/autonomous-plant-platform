"""Verify the generated Windows viewer artifact, not code-signing/field safety."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def inspect_pe(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size < 100_000:
        raise ValueError("Executable unexpectedly small")
    with path.open("rb") as f:
        if f.read(2) != b"MZ":
            raise ValueError("Not a Windows PE executable")
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {
        "file": path.name, "bytes": size, "sha256": digest,
        "pe_magic_ok": True, "signed": "NOT_CHECKED",
        "real_ot_control_validated": False, "status": "UNSIGNED_PREVIEW_BUILD",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = inspect_pe(args.exe)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
