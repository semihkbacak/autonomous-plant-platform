"""Fail-closed deployment-mode fence. NOT authentication or an OT gateway."""
from __future__ import annotations

import os
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

MODES = {"SIMULATION", "SHADOW"}


def operation_mode() -> str:
    mode = os.getenv("APP_OPERATION_MODE", "SIMULATION").upper().strip()
    if mode not in MODES:
        raise RuntimeError(
            "Unsupported operation mode. Real plant control is NOT implemented; "
            "only SIMULATION or SHADOW is permitted."
        )
    return mode


class OperationModeFence(BaseHTTPMiddleware):
    """Protect shadow mode from *all* HTTP mutations and remote access.

    Direct legacy simulator routes remain available in SIMULATION mode for
    backward compatibility. Use APP_HARDEN_LEGACY=1 to block them. This mode
    is intended ONLY for loopback developer use, never a physical plant.
    """
    async def dispatch(self, request: Request, call_next):
        mode = operation_mode()
        loopback = request.client is not None and request.client.host in (
            "127.0.0.1", "::1", "testclient"
        )
        if not loopback:
            return JSONResponse({"detail": "Local simulator/shadow API only"}, status_code=403)
        if mode == "SHADOW" and request.method.upper() not in ("GET", "HEAD", "OPTIONS"):
            return JSONResponse({"detail": "SHADOW is read-only; commands disabled"}, status_code=403)
        return await call_next(request)
