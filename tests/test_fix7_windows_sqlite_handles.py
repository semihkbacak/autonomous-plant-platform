"""Regression: Windows cannot replace/unlink a SQLite file while it is open.

Validate closed read-only SQLite connections before publication even on Linux,
where POSIX rename would otherwise hide this bug.
"""
from __future__ import annotations

import os
import sqlite3

import pytest

from tools.prepare_ges_history import ensure_synthetic_ges_history
from tools.prepare_res_history import ensure_synthetic_res_history


@pytest.mark.parametrize('plant', ['ges', 'res'])
def test_windows_style_sqlite_locking_simulated_on_all_platforms(tmp_path, monkeypatch, plant):
    actual_connect = sqlite3.connect
    actual_replace = os.replace
    live_readers = []
    observed_replace = []

    class TrackedReadOnlyConnection:
        def __init__(self, actual):
            self.actual = actual
            self.closed = False
            live_readers.append(self)

        def __getattr__(self, item):
            return getattr(self.actual, item)

        def close(self):
            self.actual.close()
            self.closed = True

    def tracked_connect(database, *args, **kwargs):
        db = actual_connect(database, *args, **kwargs)
        if str(database).endswith('?mode=ro'):
            return TrackedReadOnlyConnection(db)
        return db

    def windows_like_replace(src, dest, *args, **kwargs):
        assert all(item.closed for item in live_readers), (
            'Windows would reject os.replace: a SQLite read-only handle remains open'
        )
        observed_replace.append((src, dest))
        return actual_replace(src, dest, *args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', tracked_connect)
    monkeypatch.setattr(os, 'replace', windows_like_replace)
    dest = tmp_path / ('demo_ges.sqlite3' if plant == 'ges' else 'demo_res.sqlite3')
    result = (ensure_synthetic_ges_history(dest) if plant == 'ges'
              else ensure_synthetic_res_history(dest))
    assert result['runs'] == 1
    assert len(observed_replace) == 1
    assert live_readers and all(conn.closed for conn in live_readers)
    again = (ensure_synthetic_ges_history(dest) if plant == 'ges'
             else ensure_synthetic_res_history(dest))
    assert again == result
    assert all(conn.closed for conn in live_readers)


def test_smoke_server_checks_live_twin_endpoints():
    from desktop.full_simulator_launcher import smoke_server
    proof = smoke_server()
    assert proof['status'] == 'PASS'
    assert proof['endpoints_checked'] == 4
    assert proof['physical_control'] is False


def test_windows_exe_builder_rejects_failing_regression():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    ps = (root/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    ci = (root/'.github/workflows/research-v20-windows-bundle.yml').read_text(encoding='utf-8')
    cmd = (root/'06_WINDOWS_TAM_EXE_DERLE.cmd').read_text(encoding='utf-8')
    assert 'Running complete Windows regression before native EXE build' in ps
    assert "& $py -m pytest -q --assert=plain" in ps
    assert "if ($LASTEXITCODE -ne 0) { throw 'Windows regression tests failed; EXE build aborted.' }" in ps
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in ps
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in ci
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in cmd
