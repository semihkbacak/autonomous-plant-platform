"""Offline test coverage for local release tools only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.v15_launcher import parse_settings, local_environment
from desktop.viewer_entry_v15 import self_test, main
from desktop.verify_windows_v15 import inspect_pe


def test_shadow_default_is_read_only_loopback():
    cfg = parse_settings([])
    assert cfg.host == "127.0.0.1"
    assert cfg.mode == "SHADOW"
    assert local_environment(cfg) == {
        "APP_OPERATION_MODE": "SHADOW",
        "APP_HARDEN_LEGACY": "1",
        "APP_SIM_CONSOLE_WRITES": "0",
    }


def test_simulation_explicit_opt_in():
    cfg = parse_settings(["--mode", "SIMULATION", "--enable-local-sim-commands"])
    assert cfg.host == "127.0.0.1"
    assert local_environment(cfg)["APP_SIM_CONSOLE_WRITES"] == "1"


def test_shadow_never_allows_command_opt_in():
    with pytest.raises(SystemExit):
        parse_settings(["--mode", "SHADOW", "--enable-local-sim-commands"])


@pytest.mark.parametrize('port', ['0', '1', '80', '65536', '-1'])
def test_port_must_be_unprivileged(port):
    with pytest.raises(SystemExit):
        parse_settings(['--port', port])


def test_viewer_self_test_offline():
    assert self_test()['status'] == 'PASS'
    assert self_test()['field_control_validated'] is False
    assert main(['--self-test']) == 0


def test_exe_validation_rejects_non_executable(tmp_path):
    exe = tmp_path / 'bad.exe'
    exe.write_bytes(b'MZfake')
    with pytest.raises(ValueError):
        inspect_pe(exe)


def test_exe_validation_rejects_non_pe_even_large(tmp_path):
    exe = tmp_path / 'bad.exe'
    exe.write_bytes(b'NO' + b'0' * 102000)
    with pytest.raises(ValueError):
        inspect_pe(exe)


def test_release_workflow_is_dispatch_only():
    # Passive textual smoke test; doesn't invoke GitHub or install a runner.
    p = Path(__file__).resolve().parents[1] / '.github/workflows/windows-viewer-preview.yml'
    text = p.read_text(encoding='utf-8')
    assert 'workflow_dispatch' in text
    assert 'upload-artifact@v4' in text
    assert 'schedule:' not in text
    assert '  push:' not in text


def test_linux_viewer_zipapp_runs_without_project_dependencies(tmp_path):
    import subprocess
    import sys
    from tools.build_linux_viewer_v15 import build
    artifact = build(tmp_path / 'viewer.pyz')
    output = subprocess.run(
        [sys.executable, str(artifact), '--self-test'],
        capture_output=True, text=True, check=True, timeout=12,
    )
    data = json.loads(output.stdout)
    assert data['status'] == 'PASS'
    assert data['field_control_validated'] is False


def test_linux_viewer_zipapp_has_no_app_server_code(tmp_path):
    from zipfile import ZipFile
    from tools.build_linux_viewer_v15 import build
    artifact = build(tmp_path / 'viewer.pyz')
    with ZipFile(artifact) as package:
        files = package.namelist()
    assert 'desktop/plant_viewer.py' in files
    assert 'desktop/viewer_entry_v15.py' in files
    assert all(not f.startswith(('app/', 'core/', 'simulator/')) for f in files)
