"""Regression: a missing optional historical GES audit should not block a clean install.

The original research fixture is checked byte-for-byte; modified files are never
silently replaced. No actual Windows interpreter/venv is required to test this.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

def _load():
    spec = importlib.util.spec_from_file_location('audit_recovery_under_test', ROOT / 'windows' / 'windows_start.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _digest():
    manifest = json.loads((ROOT / 'WINDOWS_PACKAGE_MANIFEST.json').read_text(encoding='utf-8'))
    return manifest['required_fixtures_sha256']['outputs/ges_oem_shadow_v05/oem_shadow_audit.json']


def test_bundled_audit_matches_original_hash():
    original = ROOT / 'outputs' / 'ges_oem_shadow_v05' / 'oem_shadow_audit.json'
    assert hashlib.sha256(original.read_bytes()).hexdigest() == _digest()


def test_missing_audit_restored_atomically_and_verified(tmp_path):
    m = _load()
    assert m.restore_missing_audit(_digest(), root=tmp_path)
    restored = tmp_path / m._AUDIT_FILE
    assert hashlib.sha256(restored.read_bytes()).hexdigest() == _digest()
    assert not m.restore_missing_audit(_digest(), root=tmp_path)
    assert sorted(p.name for p in restored.parent.iterdir()) == ['oem_shadow_audit.json']


def test_existing_modified_audit_is_never_replaced(tmp_path):
    m = _load()
    target = tmp_path / m._AUDIT_FILE
    target.parent.mkdir(parents=True)
    target.write_text('do not overwrite', encoding='utf-8')
    assert not m.restore_missing_audit(_digest(), root=tmp_path)
    assert target.read_text(encoding='utf-8') == 'do not overwrite'


def test_bad_manifest_digest_rejected_before_writing(tmp_path):
    m = _load()
    with pytest.raises(RuntimeError, match='checksum mismatch'):
        m.restore_missing_audit('f' * 64, root=tmp_path)
    assert not (tmp_path / m._AUDIT_FILE).exists()


def test_windows_menu_one_runs_actual_installer():
    menu = (ROOT / '00_WINDOWS_BASLAT.cmd').read_text(encoding='utf-8')
    assert ':SETUP\ncall "01_WINDOWS_KUR_TEST_VE_BASLAT.cmd"' in menu.replace('\r\n','\n')
