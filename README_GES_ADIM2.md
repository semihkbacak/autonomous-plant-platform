# GES v0.3 – Adım 2: PV Temperature + De Soto DC I–V Model

This is an incremental package. **Do not delete Stage 1 files.** It adds:

- `simulator/solar/solar_temperature.py` – PV temperature (Faiman)
- `simulator/solar/pv_array.py` – De Soto five-parameter + single-diode PV array DC MPP
- `tests/test_solar_pv_dc.py` – 18 tests
- `demo_ges_dc.py` – synthetic GHI/DNI/DHI → POA → DC MPP walkthrough

Extract at the **project root** of `autonomous-plant-platform`, preserving paths.

```bash
source .venv/bin/activate
python -m pytest tests/test_solar_resource.py tests/test_solar_pv_dc.py -q
python -m pytest -q
python demo_ges_dc.py
```

Requires `pvlib==0.16.1` and existing project requirements.

Scientific references:
- pvlib `temperature.faiman`: https://pvlib-python.readthedocs.io/en/v0.16.1/reference/generated/pvlib.temperature.faiman.html
- pvlib `pvsystem.calcparams_desoto`: https://pvlib-python.readthedocs.io/en/v0.16.1/reference/generated/pvlib.pvsystem.calcparams_desoto.html
- pvlib `pvsystem.singlediode`: https://pvlib-python.readthedocs.io/en/v0.16.1/reference/generated/pvlib.pvsystem.singlediode.html

**Limitations:** reference De Soto coefficients are synthetic, uncalibrated. They are not a real module datasheet. No inverter, AC power, thermal transient, soiling physics, shading geometry, MPPT controller dynamics, or OT command integration yet. Numerical/physics invariants are useful but are not independent validation against field measurements.
