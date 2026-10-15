"""Cross-platform read-only viewer entry point for PyInstaller.

Use --self-test for headless, offline verification on Windows CI.
"""
from __future__ import annotations

import argparse
import json

from desktop.plant_viewer import URLS, Viewer, validate_local_origin

VERSION = "1.5.0-rc1-viewer"


def self_test() -> dict[str, object]:
    validate_local_origin("http://127.0.0.1:8000")
    rejects = (
        "http://example.org:8000", "http://127.0.0.1:8001",
        "https://127.0.0.1:8000", "http://127.0.0.1:8000/path",
        "http://bad@127.0.0.1:8000",
    )
    for url in rejects:
        try:
            validate_local_origin(url)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"Rejected URL unexpectedly accepted: {url}")
    if sorted(URLS) != ["GES", "HES", "RES"]:
        raise AssertionError("Unexpected plant endpoint allowlist")
    return {
        "status": "PASS",
        "version": VERSION,
        "mode": "READ_ONLY_LOCAL_VIEWER",
        "field_control_validated": False,
        "windows_gui_tested": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(VERSION)
        return 0
    if args.self_test:
        print(json.dumps(self_test(), ensure_ascii=False, sort_keys=True))
        return 0
    Viewer().mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
