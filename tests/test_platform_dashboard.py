"""Read-only unified HES/GES/RES interface tests (no plant equipment)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.platform_dashboard import create_platform_router
from app.wind_analytics_api import create_wind_analytics_router


def _populate_hes(path: Path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE hydro_runs (id INTEGER PRIMARY KEY, scenario TEXT,
                sample_count INTEGER,duration_s REAL, energy_mwh REAL,source_kind TEXT);
            CREATE TABLE hydro_samples (run_id INTEGER,simulation_time_s REAL,power_mw REAL);
            INSERT INTO hydro_runs VALUES (1,'BASELINE',2,5,0.025,'SYNTHETIC_DYNAMIC_1S');
            INSERT INTO hydro_samples VALUES(1,0,0);
            INSERT INTO hydro_samples VALUES(1,5,18);
        """)


def _populate_ges(path: Path):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE simulation_runs (id INTEGER PRIMARY KEY,scenario TEXT,
                interval_count INTEGER,total_energy_kwh REAL);
            CREATE TABLE production_intervals (run_id INTEGER,start_utc TEXT,
                end_utc TEXT,dispatched_power_kw REAL);
            INSERT INTO simulation_runs VALUES(1,'BASELINE_PQ8',2,2.5);
            INSERT INTO production_intervals VALUES(1,'2026-01-01T00:00:00+00:00','2026-01-01T00:15:00+00:00',4);
            INSERT INTO production_intervals VALUES(1,'2026-01-01T00:15:00+00:00','2026-01-01T00:30:00+00:00',6);
        """)


def _populate_res(path: Path):
    # The schema mirrors the existing wind historian; all values synthetic.
    from simulator.wind_history import SCHEMA
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO wind_runs VALUES(1,'GUSTS',2,250,'SYNTHETIC_WIND_SIMULATION_NOT_OEM')")
        db.execute("INSERT INTO wind_intervals VALUES(1,'2026-01-01T00:15:00+00:00',500,400,100,100,0)")
        db.execute("INSERT INTO wind_intervals VALUES(1,'2026-01-01T00:30:00+00:00',600,600,0,150,0)")


@pytest.fixture()
def combined(tmp_path):
    h = tmp_path / 'hes.sqlite3'
    g = tmp_path / 'ges.sqlite3'
    w = tmp_path / 'res.sqlite3'
    _populate_hes(h)
    _populate_ges(g)
    _populate_res(w)
    app = FastAPI()
    app.include_router(create_platform_router(hydro_db=h, solar_db=g, wind_db=w))
    app.include_router(create_wind_analytics_router(w))
    return TestClient(app), (h,g,w)


def test_three_sources_one_port_and_units(combined):
    client, _ = combined
    response = client.get('/api/v1/platform/overview')
    assert response.status_code == 200
    data = response.json()
    assert data['combined_total_suppressed'] is True
    assert data['historical_runs_may_not_be_time_aligned'] is True
    assert set(data['plants']) == {'HES','GES','RES'}
    h, g, w = (data['plants'][k] for k in ('HES','GES','RES'))
    assert h['latest_run']['energy_kwh'] == pytest.approx(25)
    assert h['latest_run']['peak_kw'] == pytest.approx(18000)
    assert g['latest_run']['energy_kwh'] == pytest.approx(2.5)
    assert g['latest_run']['last_recorded_kw'] == pytest.approx(6)
    assert w['latest_run']['energy_kwh'] == pytest.approx(250)
    assert w['latest_run']['sample_count'] == 2
    assert all(v['status']=='HISTORICAL' for v in (h,g,w))
    assert data['plants']['RES']['samples'][-1]['kw'] == pytest.approx(600)


def test_dashboard_and_wind_routes_on_same_app(combined):
    client, _ = combined
    dash = client.get('/platform/dashboard')
    assert dash.status_code == 200
    assert 'HES + GES + RES' in dash.text
    assert '/api/v1/platform/overview' in dash.text
    assert client.get('/api/v1/wind/runs').status_code == 200
    assert len(client.get('/api/v1/wind/runs').json()) == 1
    assert client.get('/wind/dashboard').status_code == 200


def test_missing_source_degrades_without_creating_database(tmp_path):
    missing = tmp_path / 'missing.sqlite3'
    app = FastAPI()
    app.include_router(create_platform_router(
        hydro_db=missing, solar_db=missing, wind_db=missing))
    data = TestClient(app).get('/api/v1/platform/overview').json()
    assert all(not x['available'] for x in data['plants'].values())
    assert all(x['status'] == 'DATABASE_MISSING' for x in data['plants'].values())
    assert not missing.exists()


def test_invalid_ges_suppressed_but_other_plants_work(combined):
    client, (h,g,w) = combined
    with sqlite3.connect(g) as db:
        db.execute("UPDATE simulation_runs SET interval_count=77 WHERE id=1")
    data = client.get('/api/v1/platform/overview').json()['plants']
    assert not data['GES']['available']
    assert data['GES']['status'] == 'DATABASE_INVALID_OR_INCOMPATIBLE'
    assert data['HES']['available'] and data['RES']['available']


def test_query_is_read_only(combined):
    client, files = combined
    before = [x.read_bytes() for x in files]
    assert client.get('/api/v1/platform/overview').status_code == 200
    after = [x.read_bytes() for x in files]
    assert before == after


def test_no_control_routes_exposed_by_unified_module(combined):
    client, _ = combined
    assert client.post('/api/v1/platform/overview').status_code == 405
    assert client.post('/platform/dashboard').status_code == 405


def test_empty_history_handled(tmp_path):
    empty = tmp_path/'empty.sqlite3'
    with sqlite3.connect(empty) as db:
        db.execute('CREATE TABLE wind_runs(id INTEGER PRIMARY KEY,scenario TEXT,interval_count INTEGER,energy_kwh REAL,source_kind TEXT)')
    app=FastAPI()
    app.include_router(create_platform_router(hydro_db=tmp_path/'h', solar_db=tmp_path/'g', wind_db=empty))
    data=TestClient(app).get('/api/v1/platform/overview').json()
    assert data['plants']['RES']['status']=='NO_RUNS'
