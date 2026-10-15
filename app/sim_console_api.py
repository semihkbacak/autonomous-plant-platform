"""Explicit opt-in, loopback-only command gateway for synthetic simulators.

This is NOT a production authorization mechanism. Do not expose on public
interfaces, containers with shared ingress, or an actual industrial OT network.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.sim_runtime import SimulatorSessions, SessionError


class ModeInput(BaseModel):
    mode: str = Field(min_length=1, max_length=30)


class HESUnitInput(BaseModel):
    unit_id: str = Field(pattern=r'^UNIT_[12]$')


def create_sim_console_router(sessions: SimulatorSessions, hydro) -> APIRouter:
    router = APIRouter(prefix='/api/v1/sim-console', tags=['Simulation Console (local only)'])

    def require_local_write(request: Request, confirm: str | None) -> None:
        if os.getenv('APP_SIM_CONSOLE_WRITES') != '1':
            raise HTTPException(403, 'Console writes disabled: opt-in required')
        if request.client is None or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
            raise HTTPException(403, 'Simulator console accepts only local requests')
        if confirm != 'SIMULATION_ONLY':
            raise HTTPException(403, 'Explicit simulation confirmation header required')
        origin = request.headers.get('origin')
        if origin:
            parsed = urlsplit(origin)
            if parsed.scheme not in ('http', 'https') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
                raise HTTPException(403, 'Cross-origin control request rejected')
            host = request.url.hostname
            if parsed.port != request.url.port or (host not in (parsed.hostname, '127.0.0.1', 'localhost', '::1')):
                raise HTTPException(403, 'Origin/host mismatch')

    def session(plant: str):
        try:
            return sessions.session(plant)
        except SessionError as exc:
            raise HTTPException(404, str(exc)) from exc

    def guarded(plant: str, action, *args):
        try:
            return getattr(session(plant), action)(*args)
        except SessionError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, 'Synthetic model rejected input') from exc

    @router.get('/{plant}')
    def state(plant: str):
        if plant == 'hes':
            snapshot = hydro.snapshot()
            return {
                'plant': 'HES', 'scope': 'SYNTHETIC_IN_MEMORY_NO_OT',
                'running': hydro.auto_tick_enabled,
                'intervals': snapshot.simulation_time_s,
                'last_power_kw': sum(u.active_power_mw for u in snapshot.units) * 1000,
                'units': [
                    {'id': u.unit_id, 'kw': u.active_power_mw * 1000, 'status': u.status.value}
                    for u in snapshot.units
                ],
            }
        return session(plant).status()

    @router.post('/{plant}/start')
    def start(plant: str, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return guarded(plant, 'start')

    @router.post('/{plant}/pause')
    def pause(plant: str, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return guarded(plant, 'pause')

    @router.post('/{plant}/step')
    def step(plant: str, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return guarded(plant, 'step')

    @router.post('/{plant}/reset')
    def reset(plant: str, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return guarded(plant, 'reset')

    @router.post('/{plant}/mode')
    def mode(plant: str, body: ModeInput, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return guarded(plant, 'configure', body.mode)

    @router.post('/hes/auto')
    def hydro_auto(active: bool, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return hydro.set_auto_tick(active)

    @router.post('/hes/unit/start')
    def hydro_start(body: HESUnitInput, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return hydro.request_start(body.unit_id)

    @router.post('/hes/unit/stop')
    def hydro_stop(body: HESUnitInput, request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return hydro.request_stop(body.unit_id)

    @router.post('/hes/tick')
    def hydro_tick(request: Request, x_sim_console_confirm: str | None = Header(None)):
        require_local_write(request, x_sim_console_confirm)
        return hydro.tick()

    return router
