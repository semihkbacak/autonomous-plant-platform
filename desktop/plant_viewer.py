"""Windows/Linux read-only desktop viewer for LOCAL simulator/shadow server.

Python standard library only. Never sends POST/PUT/PATCH/DELETE.
A packaged .exe is a VIEWER, not a production server or OT controller.
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler
import webbrowser

BASE = "http://127.0.0.1:8000"
URLS = {
    "HES": "/api/v1/plant", "GES": "/api/v1/sim-console/ges",
    "RES": "/api/v1/sim-console/res",
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Server redirects are disabled")


def validate_local_origin(value: str) -> str:
    u = urlsplit(value)
    if (u.scheme != "http" or u.hostname not in ("127.0.0.1", "localhost")
            or u.port != 8000 or u.username or u.password
            or u.path or u.query or u.fragment):
        raise ValueError("Only the local simulator at 127.0.0.1:8000 is supported")
    return value


def read_json(origin: str, path: str) -> dict:
    validate_local_origin(origin)
    if path not in URLS.values() and path != "/api/v1/site/readiness":
        raise ValueError("Only allowlisted read-only paths may be read")
    opener = build_opener(NoRedirect())
    with opener.open(origin + path, timeout=2) as response:
        if response.status != 200:
            raise ValueError("Server returned non-success HTTP")
        body = response.read(128_001)
        if len(body) > 128_000:
            raise ValueError("Unexpectedly large API response")
    return json.loads(body)


class Viewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Autonomous Plant — Offline Research Viewer")
        self.geometry("660x390")
        self.minsize(520, 340)
        self.executor = ThreadPoolExecutor(max_workers=1)
        self._future = None
        main = ttk.Frame(self, padding=22)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="HES · GES · RES — Read-only local viewer",
                  font=("Arial", 16, "bold")).pack(anchor="w")
        ttk.Label(main, text="SIMULATION / SHADOW ONLY — No equipment control").pack(anchor="w", pady=(4, 20))
        self.labels = {}
        for plant in URLS:
            label = ttk.Label(main, text=f"{plant}: connecting ...", font=("Arial", 12))
            label.pack(anchor="w", pady=5)
            self.labels[plant] = label
        self.status = ttk.Label(main, text="Read-only, local API required")
        self.status.pack(anchor="w", pady=12)
        actions = ttk.Frame(main)
        actions.pack(anchor="w", pady=12)
        ttk.Button(actions, text="Open Dashboard", command=lambda: webbrowser.open(BASE + "/platform/dashboard")).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Open Site Readiness", command=lambda: webbrowser.open(BASE + "/platform/site-transition")).pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.refresh)

    def refresh(self):
        if self._future is None:
            self._future = self.executor.submit(
                lambda: {name: read_json(BASE, path) for name, path in URLS.items()}
            )
        elif self._future.done():
            try:
                data = self._future.result()
                h_kw = sum(float(x["active_power_mw"])*1000 for x in data["HES"]["units"])
                self.labels["HES"].configure(text=f"HES: {h_kw:,.1f} kW · local synthetic model")
                for name in ("GES", "RES"):
                    item = data[name]
                    self.labels[name].configure(text=(
                        f"{name}: {float(item['last_power_kw']):,.1f} kW · "
                        f"{int(item['intervals'])}/96 intervals · "
                        f"{'Running' if item['running'] else 'Stopped'}"
                    ))
                self.status.configure(text="Local simulator connected; no real field telemetry verified")
            except Exception as exc:
                self.status.configure(text=f"Local simulator unavailable: {type(exc).__name__}")
            finally:
                self._future = None
        self.after(2000, self.refresh)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


if __name__ == "__main__":
    validate_local_origin(BASE)
    Viewer().mainloop()
