# Security scope — local demo only

- This bundle contains NO industrial device adapter and does NOT authorize plant control.
- Run Uvicorn bound to `127.0.0.1`, never expose to LAN/Internet/OT networks.
- `APP_SIM_CONSOLE_WRITES=1` enables local simulator commands only. It is **not** a password/authentication system.
- `APP_HARDEN_LEGACY=1` rejects direct legacy FastAPI mutation endpoints under `/api/v1/*` except `sim-console` and pure portfolio calculation. This preserves existing READ APIs. The middleware is a **migration aid**, not production security.
- A process on the same host can forge headers. Native desktop applications and proxies require their own authenticated controls and origin model.
- Control ledger writes HTTP attempts only, not actual device commands. SQLite is mutable and needs permissions and backup in future.
- No real-time dependency: controller/safety independence must come from certified site hardware outside this software.
- Real operator access must be implemented through secure remote access with verified identity, policy authorization, audit, segregated OT zones, operator takeover, and testing before enabling any actual effect.
