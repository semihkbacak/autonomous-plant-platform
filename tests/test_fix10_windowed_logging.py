"""FIX10: native --windowed EXE must not crash on Uvicorn formatter or diverge from GUI path."""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

from desktop.full_simulator_launcher import _uvicorn_config, smoke_server, LocalServer


def test_uvicorn_config_safe_with_missing_windows_console_streams(monkeypatch):
    from fastapi import FastAPI
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    cfg = _uvicorn_config(FastAPI(), port=0)
    assert cfg.log_config is None
    assert cfg.host == '127.0.0.1'
    assert cfg.port == 0


def test_gui_managed_server_starts_when_no_console_stream_exists(monkeypatch, tmp_path):
    """The frozen Windows GUI has no stdout/stderr; test the actual server path."""
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('GES_HISTORIAN_DB', str(tmp_path/'ges_h.sqlite3'))
    monkeypatch.setenv('RES_HISTORIAN_DB', str(tmp_path/'res_h.sqlite3'))
    monkeypatch.setattr(sys, 'stdout', None)
    monkeypatch.setattr(sys, 'stderr', None)
    response = smoke_server()
    assert response['status'] == 'PASS'
    assert response['gui_server_path_checked'] is True


def test_gui_and_smoke_share_the_same_start_path():
    import inspect
    src=inspect.getsource(smoke_server)
    assert 'LocalServer()' in src
    assert 'local.start(port=0)' in src
    assert "uvicorn.Server(uvicorn.Config(" not in src
    assert "log_config=None" in inspect.getsource(_uvicorn_config)


def test_actual_gui_server_path_serves_all_three_endpoints(monkeypatch, tmp_path):
    # Keep all generated demo/history data in the isolated temporary test directory.
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('GES_HISTORIAN_DB',str(tmp_path/'ges_history.sqlite3'))
    monkeypatch.setenv('RES_HISTORIAN_DB',str(tmp_path/'res_history.sqlite3'))
    response=smoke_server()
    assert response['status']=='PASS'
    assert response['gui_server_path_checked'] is True
    assert response['endpoints_checked']==4
    assert response['physical_control'] is False
