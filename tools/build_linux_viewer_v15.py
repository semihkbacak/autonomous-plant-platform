"""Create a standard-library-only Linux viewer .pyz, not a standalone ELF.

Requires Python 3 + tkinter on the destination. Viewer makes read-only
requests to the local-only simulator API; never controls equipment.
"""
from __future__ import annotations

import argparse
import tempfile
import zipapp
from pathlib import Path
from shutil import copy2


def build(target: Path, *, source_root: Path | None = None) -> Path:
    source_root = source_root or Path(__file__).resolve().parents[1]
    entry = source_root / "desktop/viewer_entry_v15.py"
    viewer = source_root / "desktop/plant_viewer.py"
    if not entry.is_file() or not viewer.is_file():
        raise FileNotFoundError("Need both viewer entry and plant_viewer.py")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="autoplant-pyz-") as directory:
        stage = Path(directory)
        pkg = stage / "desktop"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (stage / "__main__.py").write_text(
            "from desktop.viewer_entry_v15 import main\n"
            "raise SystemExit(main())\n", encoding="utf-8"
        )
        copy2(entry, pkg / entry.name)
        copy2(viewer, pkg / viewer.name)
        zipapp.create_archive(stage, target=target, interpreter="/usr/bin/env python3")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist/AutonomousPlantViewer-Linux.pyz"))
    args = parser.parse_args()
    built = build(args.output)
    print(f"LINUX READ-ONLY VIEWER PYZ CREATED: {built}")
    print("Requires system Python 3 + tkinter; NOT a fully standalone binary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
