# FIX8 — Windows FastAPI router / EXE compilation fix

This patch addresses the Windows regression failure:

`AttributeError: '_IncludedRouter' object has no attribute 'path'`

In `desktop/full_simulator_launcher.py`, the desktop `--self-test` now uses
FastAPI `TestClient` to verify **actual HTTP 200 responses and synthetic-mode
scope** for the GES, RES, and live twins endpoints. It no longer assumes each
internal route object has a `.path` attribute. The local Uvicorn `--smoke-server`
check remains required after the EXE is built.

## Windows install / compile

1. Close the old desktop EXE and local port-8000 simulator.
2. Right-click the FIX8 ZIP -> Extract All. **Never start from ZIP preview**.
3. Start `02_YALNIZ_TEST.cmd`. Wait for the full Windows test result.
4. Start `06_WINDOWS_TAM_EXE_DERLE.cmd` in the extracted project folder.
5. On success keep the complete
   `dist\AutonomousPlantSimulatorV20_FIX8\` folder; run
   `AutonomousPlantSimulatorV20_FIX8.exe` with its `_internal` directory.

If build fails, send `WINDOWS_EXE_DERLEME_RAPORU.txt` (no passwords/tokens).

## Limits

This work was validated with Linux and the locally available FastAPI version.
The exact 0.143.2 package from the user's Windows run and the Windows native EXE
cannot be run in this Linux environment. The real Windows full regression and
native EXE smoke/GUI checks are required before external distribution.
Simulation data remain synthetic; no PLC/SCADA connection is permitted.
