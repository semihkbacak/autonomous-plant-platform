"""Local-only launcher for a simulated/shadow energy platform.

Never expose this application to an OT network. This is not an OT gateway.
"""
from __future__ import annotations

import argparse
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LaunchSettings:
    mode: str
    host: str
    port: int
    allow_local_sim_commands: bool


def parse_settings(argv: list[str] | None = None) -> LaunchSettings:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("SHADOW", "SIMULATION"), default="SHADOW")
    parser.add_argument("--enable-local-sim-commands", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if args.enable_local_sim_commands and args.mode != "SIMULATION":
        parser.error("Commands may be enabled only in SIMULATION mode")
    if not 1024 <= args.port <= 65535:
        parser.error("Use an unprivileged TCP port between 1024 and 65535")
    return LaunchSettings(args.mode, "127.0.0.1", args.port, args.enable_local_sim_commands)


def local_environment(settings: LaunchSettings) -> dict[str, str]:
    """Return overrides; no OT authentication or privileged access implied."""
    return {
        "APP_OPERATION_MODE": settings.mode,
        "APP_HARDEN_LEGACY": "1",
        "APP_SIM_CONSOLE_WRITES": "1" if settings.allow_local_sim_commands else "0",
    }


def main(argv: list[str] | None = None) -> int:
    settings = parse_settings(argv)
    os.environ.update(local_environment(settings))
    import uvicorn

    print("Autonomous Plant Platform — LOCAL ONLY / NOT FIELD CONTROL")
    print(f"Mode: {settings.mode}; simulator writes: {settings.allow_local_sim_commands}")
    print(f"UI: http://{settings.host}:{settings.port}/platform/dashboard")
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
