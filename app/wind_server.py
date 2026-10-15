"""Independent read-only RES history dashboard server.

Start: RES_HISTORIAN_DB=/path/to/wind_history.sqlite3 \
       python -m uvicorn app.wind_server:app --host 127.0.0.1 --port 8001
"""
from __future__ import annotations
import os
from fastapi import FastAPI
from app.wind_analytics_api import create_wind_analytics_router

app = FastAPI(title='Autonomous Plant Platform - RES Simulator Analytics')
app.include_router(create_wind_analytics_router(
    os.environ.get('RES_HISTORIAN_DB', 'outputs/res_v10/wind_history.sqlite3')
))

@app.get('/health')
def health():
    return {'status': 'ok', 'mode': 'simulator-only', 'unit': 'RES'}
