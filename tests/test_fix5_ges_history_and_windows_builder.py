"""FIX5 offline regression for missing GES historian and Windows builder diagnostics."""
from __future__ import annotations
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from tools.prepare_ges_history import ensure_synthetic_ges_history, inspect_history

ROOT = Path(__file__).resolve().parents[1]


def test_first_run_creates_full_ges_analytics_historian_and_is_idempotent(tmp_path):
    dest = tmp_path / 'demo-history.sqlite3'
    assert not dest.exists()
    first = ensure_synthetic_ges_history(dest)
    assert first['scope'] == 'SYNTHETIC_OFFLINE_DEMO_ONLY'
    assert first['runs'] == 1 and first['intervals'] == 4
    assert first['mppt_intervals'] == 16 and first['pq_intervals'] == 8
    content_hash = __import__('hashlib').sha256(dest.read_bytes()).hexdigest()
    second = ensure_synthetic_ges_history(dest)
    assert second == first
    assert __import__('hashlib').sha256(dest.read_bytes()).hexdigest() == content_hash


def test_ges_analytics_endpoints_read_prepared_synthetic_history(tmp_path):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from app.solar_analytics_api import create_solar_analytics_router
    path = tmp_path / 'demo.sqlite3'
    ensure_synthetic_ges_history(path)
    app = FastAPI()
    app.include_router(create_solar_analytics_router(path))
    client = TestClient(app)
    runs = client.get('/solar/analytics/runs')
    assert runs.status_code == 200, runs.text
    assert len(runs.json()) == 1
    run_id = runs.json()[0]['id']
    days = client.get(f'/solar/analytics/runs/{run_id}/days')
    assert days.status_code == 200, days.text
    assert len(days.json()) == 1
    day = days.json()[0]['day']
    content = client.get(f'/solar/analytics/runs/{run_id}/days/{day}')
    assert content.status_code == 200, content.text


def test_existing_non_demo_database_is_never_overwritten(tmp_path):
    target = tmp_path / 'existing.sqlite3'
    with sqlite3.connect(target) as db:
        db.execute('CREATE TABLE important (value TEXT)')
        db.execute('INSERT INTO important VALUES (?)', ('keep me',))
    original = target.read_bytes()
    with pytest.raises((sqlite3.DatabaseError, RuntimeError)):
        ensure_synthetic_ges_history(target)
    assert target.read_bytes() == original


def test_builder_keeps_window_open_and_reports_destination():
    batch = (ROOT/'06_WINDOWS_TAM_EXE_DERLE.cmd').read_text(encoding='utf-8')
    ps = (ROOT/'desktop/build_full_windows_v20.ps1').read_text(encoding='utf-8')
    assert 'pause' in batch
    assert 'WINDOWS_EXE_DERLEME_RAPORU.txt' in batch
    assert 'Start-Transcript' in ps and 'Stop-Transcript' in ps
    assert 'AutonomousPlantSimulatorV20_FIX11.exe' in ps
    assert 'Get-FileHash' in ps
    assert '--self-test' in ps
    assert 'demo_ges_integrated_v04' in ps
