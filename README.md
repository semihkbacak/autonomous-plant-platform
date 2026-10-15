# Autonomous Plant Platform

**HES + GES + RES | Simulation-first energy plant digital twins and decision-support research platform**

> **Release status:** v1.5 preview — research / synthetic simulation / offline SHADOW analysis.  
> **NOT FOR REAL-TIME OT CONTROL.** No production PLC/SCADA command channel, field acceptance, OEM certification, or unattended plant-control approval is included.

[![Windows viewer preview](https://github.com/semihkbacak/autonomous-plant-platform/actions/workflows/windows-viewer-preview.yml/badge.svg)](https://github.com/semihkbacak/autonomous-plant-platform/actions/workflows/windows-viewer-preview.yml)

## Overview / Genel bakış

Autonomous Plant Platform explores a modular, vendor-independent software architecture for **hydroelectric (HES), photovoltaic (GES), and wind (RES)** energy systems. A single FastAPI service provides synthetic simulators, read-only analytics, historical scenario reports and development-oriented interfaces.

Bu proje, hidroelektrik, güneş ve rüzgâr enerji santralleri için üretici bağımsız bir **sentetik simülasyon ve karar destek araştırma platformudur**. Gerçek bir tesisi devralmaz; saha kumandası veya bağımsız elektriksel/mekanik koruma sistemi değildir.

## What is implemented / Mevcut yazılım kapsamı

| Plant | Simulator and research coverage |
|---|---|
| HES | Two-unit hydro simulator, state machine, governor/dispatch, safety checks, alarms, historical scenarios, synthetic research models |
| GES | Synthetic PV/inverter/MPPT simulation, shading and AC/P-Q analysis, scenarios, historian and research/validation tools |
| RES | Synthetic wind generation simulation, turbine scenarios, historian, research models for pitch/yaw and fault injection |
| Shared | FastAPI, dashboards, centralized synthetic alarms, engineering diagnostics, offline CSV-based SHADOW analysis, test suite |

These are software capabilities, **not** claims of OEM-level digital-twin fidelity or operational safety certification. The three simulators do not imply a common synchronized physical clock.

## Installation / Linux kurulumu

Requires Python 3 and the packages in `requirements.txt`. The project has been tested by the contributor in a Python 3.14 virtual environment; dependency compatibility must be checked on other Python versions.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pytest -q --assert=plain -x
```

Start read-only/offline-oriented **SHADOW** mode (the default):

```bash
python -m tools.v15_launcher
```

For **local synthetic simulation only**, explicitly enable simulator commands:

```bash
python -m tools.v15_launcher --mode SIMULATION --enable-local-sim-commands
```

The launcher binds to `127.0.0.1:8000` by default. Do not expose this development server to a public interface or an OT network. If port 8000 is occupied, shut down the old instance or use `--port 8001` (the Windows preview viewer currently expects its local default endpoint).

## Interfaces / Arayüzler

With the server running locally:

- [Unified dashboard](http://127.0.0.1:8000/platform/dashboard)
- [Synthetic alarms](http://127.0.0.1:8000/platform/alarms)
- [Engineering diagnostics](http://127.0.0.1:8000/platform/engineering)
- [SHADOW/site preparation](http://127.0.0.1:8000/platform/site-transition)
- [Research / evidence](http://127.0.0.1:8000/platform/research)
- [API Developer Center](http://127.0.0.1:8000/docs)

These URLs refer to a server running on **your own computer**. A SHADOW mode screen does not imply a live site connection.

## Windows viewer preview

The Windows preview is a **read-only viewer**, **not** the complete plant simulator or a plant-control application. It queries the local FastAPI service and does not create a remote OT connection.

A native Windows environment (or the `windows-viewer-preview.yml` GitHub Actions workflow) can build the unsigned preview:

```powershell
powershell -ExecutionPolicy Bypass -File desktop\build_windows_v15.ps1
```

The produced executable is checked with an offline self-test and SHA-256 report. GUI usability, code signing, malware screening and target Windows releases require additional validation before external distribution.

## Scientific and site-validation status / Gerçek tesis sınırı

The research models and validation tools do **not** replace:

- Manufacturer-approved component curves, control logic and limits
- Authorized plant data, site-specific calibration and uncertainty assessment
- Hydraulic transients, electrical protection and aeroelastic validation as applicable
- Independent OT safety systems, safe failure modes and authorized engineering review
- Cybersecurity architecture and tested access controls in a site-specific environment
- Hardware-in-the-loop tests, factory/site acceptance tests (FAT/SAT) and supervised pilot operation

No real-plant control or autonomous unattended operation is authorized by this repository. See `docs/RELEASE_GATES_TR.md`, `docs/SECURITY_AND_OT_BOUNDARY_TR.md`, and `docs/LITERATUR_TARAMASI_TR.md` for evidence requirements and references.

## Project layout

```text
app/             FastAPI APIs and UI
core/            shared research, security and validation primitives
simulator/       synthetic hydro, PV and wind models
tests/           automated regression tests
tools/           launchers and offline engineering utilities
desktop/         read-only viewer and Windows packaging
scripts/         local helper scripts
examples/        synthetic example datasets
docs/            release gates, literature and engineering limitations
.github/         preview CI workflows
```

`outputs/`, SQLite historians, secrets, local configuration, virtual environments and manufacturer-proprietary data must not be committed.

## Testing and contributions

Before submitting a PR:

```bash
python -m pytest -q --assert=plain -x
git diff --cached --check
```

A contributor-reported local development snapshot passed **662 automated tests** (2026-10-15). This is a historical snapshot, **not** a guarantee that every future commit, operating system or installation passes. Review GitHub CI results for each new commit.

Please submit changes through a review branch/PR. Label synthetic examples clearly and never include plant credentials, real production telemetry or proprietary OEM documents without appropriate rights.

## License / Lisans

**License has not yet been declared in this repository.** All code and third-party data must be reviewed for ownership and compatible redistribution rights before commercial or public packaged distribution. GitHub public visibility by itself does not grant third-party reuse permission.
