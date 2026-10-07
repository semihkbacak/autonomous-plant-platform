# Architecture — v0.2 Simulator

This repository currently runs **only a local synthetic digital twin**. It does not connect to any real PLC, SCADA, RTU, protection relay or industrial network.

```text
FastAPI API
   │
   ├── Runtime control
   │      └── automatic 1 s simulator clock
   │
   ├── Unit commands
   │      ├── START request
   │      └── STOP request
   │
   ├── Safety / permissive checks
   │
   └── Hydro digital twin
          ├── Unit state machines
          ├── electrical demo signals
          ├── mechanical/process demo signals
          └── headpond state
```

All process values are synthetic and are intended only for software development and demonstration.

Future adapters will sit below the platform core:

```text
Platform Core
    │
Adapter Interface
    ├── Simulator (current)
    ├── OPC UA (future)
    ├── Modbus TCP (future)
    └── MQTT (future)
```
