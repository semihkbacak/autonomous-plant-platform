"""Independent site acceptance evidence registry, fail-closed.

A file hash proves byte identity, *not* independent authenticity/approval.
This registry never declares site control permissible by itself.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

REQUIREMENTS = {
  "OEM_DATASHEETS": "Site-specific manufacturer documents and parameter approval",
  "EQUIPMENT_INVENTORY": "Serial-number/tag mapping and single line diagrams",
  "INSTRUMENT_TRACEABILITY": "Sensor range, uncertainty, and calibration certificates",
  "FIELD_TIME_SERIES": "Authorized real site time series with sensor quality",
  "HES_TRANSIENT_STUDY": "Detailed water hammer and turbine-governor study for applicable HES",
  "GES_DC_PROTECTION": "String, MPPT, grounding and grid-code studies for applicable GES",
  "RES_LOAD_STUDY": "Power curve, rotor-load and pitch/yaw fault validation for applicable RES",
  "OT_SECURITY_REVIEW": "Site network segmentation and threat review",
  "FAT_RESULTS": "Factory acceptance test evidence",
  "HIL_RESULTS": "Hardware-in-the-loop protection tests",
  "SAT_RESULTS": "Site acceptance test evidence signed by authorized team",
  "EMERGENCY_MANUAL_PROCEDURES": "Documented local emergency and manual override",
  "INDEPENDENT_SAFETY_APPROVAL": "Independent safety-engineering approval",
  "WINDOWS_RELEASE_SIGNING": "Windows binary execution and signing verification",
}

def inventory(evidence_dir: str | Path | None, *, required_plants: tuple[str,...] = ("HES","GES","RES")) -> dict:
    if any(p not in ("HES","GES","RES") for p in required_plants):
        raise ValueError("Unknown plant")
    needed = dict(REQUIREMENTS)
    if "HES" not in required_plants:needed.pop("HES_TRANSIENT_STUDY")
    if "GES" not in required_plants:needed.pop("GES_DC_PROTECTION")
    if "RES" not in required_plants:needed.pop("RES_LOAD_STUDY")
    base = Path(evidence_dir) if evidence_dir is not None else None
    results = {}
    for kind, explanation in needed.items():
        filename = (base / (kind + '.pdf')) if base else None
        if filename and filename.is_file() and not filename.is_symlink() and filename.stat().st_size <= 40_000_000:
            digest = hashlib.sha256(filename.read_bytes()).hexdigest()
            results[kind] = {"file_present":True,"sha256":digest,"independently_reviewed":False,"meaning":explanation}
        else:
            results[kind] = {"file_present":False,"sha256":None,"independently_reviewed":False,"meaning":explanation}
    return {"scope":"EVIDENCE_FILE_INVENTORY_NOT_APPROVAL", "requirements":results,
            "missing_file_kinds":[k for k,v in results.items() if not v["file_present"]],
            "independent_review_complete":False, "site_control_authorized":False,
            "warning":"Even all present PDFs do not imply genuine, applicable, independent approvals"}
