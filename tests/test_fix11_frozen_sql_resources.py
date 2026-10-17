"""FIX11 regression: Windows PyInstaller must bundle non-Python SQL resources.

No Windows executable is fabricated by these tests. They guard both build
recipes and the frozen runtime's fail-closed resource validation.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NAME = 'AutonomousPlantSimulatorV20_FIX11'
SQL_RELATIVE_PATH = Path('simulator/solar/ges_history_schema.sql')


def test_ges_sql_schema_present_and_has_expected_tables():
    schema = (ROOT / SQL_RELATIVE_PATH).read_text(encoding='utf-8')
    assert 'CREATE TABLE IF NOT EXISTS' in schema.upper()
    assert 'ges_mppt' in schema.lower() or 'ges_inverter' in schema.lower()


def test_windows_builder_explicitly_packages_and_hashes_schema():
    script = (ROOT / 'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    assert "$schemaSrc = Join-Path $root 'simulator\\solar\\ges_history_schema.sql'" in script
    assert "'--add-data',($schemaSrc + ';simulator/solar')" in script
    assert "$bundledSchema = Join-Path $root 'dist\\" + NAME + "\\_internal\\simulator\\solar\\ges_history_schema.sql'" in script
    assert 'Get-FileHash -LiteralPath $schemaSrc -Algorithm SHA256' in script
    assert 'Get-FileHash -LiteralPath $bundledSchema -Algorithm SHA256' in script
    assert 'Bundled SQL schema is missing' in script
    assert 'Bundled SQL schema has incorrect contents' in script
    # Fail hard before ever claiming success.
    assert script.index('Bundled SQL schema is missing') < script.index('& $exe --self-test')


def test_github_ci_packages_and_checks_schema():
    workflow = (ROOT / '.github/workflows/research-v20-windows-bundle.yml').read_text(encoding='utf-8')
    assert "$schema = (Resolve-Path 'simulator/solar/ges_history_schema.sql').Path" in workflow
    assert '--add-data "$schema;simulator/solar"' in workflow
    assert 'Bundled ges_history_schema.sql missing from Windows EXE folder' in workflow
    assert 'Bundled SQL hash mismatch' in workflow
    assert NAME in workflow


def test_frozen_app_fails_early_for_missing_schema(monkeypatch, tmp_path):
    from desktop.full_simulator_launcher import _prepare_bundled_runtime
    package = tmp_path / '_internal'
    model = package / 'models/hes_anomaly_iforest.joblib'
    model.parent.mkdir(parents=True)
    model.write_bytes(b'model placeholder, never loaded by this test')
    static = package / 'app/static'
    static.mkdir(parents=True)
    for name in ('solar_dashboard.html','solar_inverter_dashboard.html'):
        (static/name).write_text('test only',encoding='utf-8')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(package), raising=False)
    with pytest.raises(RuntimeError, match=r'simulator/solar/ges_history_schema.sql') as exc:
        _prepare_bundled_runtime()
    assert r'simulator\solar\ges_history_schema.sql' not in str(exc.value)


def test_frozen_app_accepts_full_asset_layout_without_real_site_io(monkeypatch, tmp_path):
    from desktop.full_simulator_launcher import _prepare_bundled_runtime
    package = tmp_path / '_internal'
    (package / 'models').mkdir(parents=True)
    (package / 'models/hes_anomaly_iforest.joblib').write_bytes(b'test model placeholder')
    static = package / 'app/static'
    static.mkdir(parents=True)
    for name in ('solar_dashboard.html','solar_inverter_dashboard.html'):
        (static / name).write_text('<html>demo</html>',encoding='utf-8')
    schema = package / SQL_RELATIVE_PATH
    schema.parent.mkdir(parents=True)
    schema.write_bytes((ROOT / SQL_RELATIVE_PATH).read_bytes())
    assert hashlib.sha256(schema.read_bytes()).digest() == hashlib.sha256((ROOT/SQL_RELATIVE_PATH).read_bytes()).digest()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(package), raising=False)
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path / 'localappdata'))
    monkeypatch.chdir(ROOT)
    _prepare_bundled_runtime()
    assert Path.cwd()==package
    assert Path(__import__('os').environ['APP_RESEARCH_DB']).parent.is_dir()
