
"""
Guarded GES v0.4 source integration.

Run once from the project root.
Existing SQLite databases are not modified by this installer.
"""
from pathlib import Path
from shutil import copy2


def replace_once(
    source: str,
    old: str,
    new: str,
    label: str,
) -> str:

    if (
        old not in source
        or source.count(old) != 1
    ):
        raise RuntimeError(
            f"Unexpected {label} source layout; "
            "no files changed"
        )

    return source.replace(
        old,
        new,
        1,
    )


root = Path(__file__).resolve().parent

interval_path = (
    root / "simulator/solar/solar_timeseries.py"
)

historian_path = (
    root / "simulator/solar/historian.py"
)

mppt_path = (
    root / "simulator/solar/multi_mppt_physics.py"
)

original_interval = interval_path.read_text(
    encoding="utf-8"
)

original_history = historian_path.read_text(
    encoding="utf-8"
)

original_mppt = mppt_path.read_text(
    encoding="utf-8"
)

if (
    "mppt_reports: tuple = ()" in original_interval
    or "initialize_mppt_schema(db)" in original_history
    or "    poa: POAResult | None = None" in original_mppt
):
    raise SystemExit(
        "v0.4 integration already present; stopped safely"
    )


# ============================================================
# SOLAR INTERVAL RESULTS
# ============================================================

interval = replace_once(
    original_interval,

    "    inverter_results: tuple[InverterResult, ...] = ()",

    "    inverter_results: tuple[InverterResult, ...] = ()\n"
    "    mppt_reports: tuple = ()  # per-channel MPPT results\n"
    "    pq_reports: tuple = ()  # Q requests, not measured output",

    "SolarIntervalResult",
)


interval = replace_once(
    interval,

    "            inverter_results=tuple(\n"
    "                plant.inverter_results\n"
    "            ),",

    "            inverter_results=tuple(\n"
    "                plant.inverter_results\n"
    "            ),\n"
    "            mppt_reports=tuple(getattr(response, 'mppt_reports', ())),\n"
    "            pq_reports=tuple(getattr(response, 'pq_reports', ())),",

    "interval result construction",
)


# ============================================================
# SOLAR HISTORIAN
# ============================================================

history = replace_once(
    original_history,

    "from simulator.solar.solar_timeseries import (\n"
    "    SolarTimeSeriesSimulator,\n"
    ")",

    "from simulator.solar.solar_timeseries import (\n"
    "    SolarTimeSeriesSimulator,\n"
    ")\n"
    "from simulator.solar.mppt_history import (\n"
    "    initialize_mppt_schema, append_mppt_interval,\n"
    ")",

    "Historian import",
)


history = replace_once(
    history,

    "            initialize_ges_inverter_schema(db)",

    "            initialize_ges_inverter_schema(db)\n"
    "            initialize_mppt_schema(db)",

    "Historian schema",
)


history = replace_once(
    history,

    "                    )\n\n"
    "            # -----------------------------------------------\n"
    "            # SAVE PLANT ALARM TRANSITIONS",

    "                    )\n\n"
    "                # Save MPPT and P-Q within the same transaction.\n"
    "                append_mppt_interval(db, run_id, record)\n\n"
    "            # -----------------------------------------------\n"
    "            # SAVE PLANT ALARM TRANSITIONS",

    "Historian interval insertion",
)


# ============================================================
# REUSE EXISTING MPPT POA + DE SOTO RESULTS
# ============================================================

mppt = replace_once(
    original_mppt,

    "    PVArrayConfiguration,\n"
    "    calculate_pv_array_from_poa,",

    "    PVArrayConfiguration,\n"
    "    PVArrayDCResult,\n"
    "    calculate_pv_array_from_poa,",

    "MPPT PV imports",
)


mppt = replace_once(
    mppt,

    "    PVSurface,\n"
    "    SolarSite,\n"
    "    calculate_poa,",

    "    PVSurface,\n"
    "    SolarSite,\n"
    "    POAResult,\n"
    "    calculate_poa,",

    "MPPT POA imports",
)


mppt = replace_once(
    mppt,

    "    reasons: tuple[str, ...]\n\n\n"
    "@dataclass(frozen=True)\n"
    "class MultiMPPTResult:",

    "    reasons: tuple[str, ...]\n"
    "    poa: POAResult | None = None\n"
    "    dc: PVArrayDCResult | None = None\n\n\n"
    "@dataclass(frozen=True)\n"
    "class MultiMPPTResult:",

    "MPPT channel data",
)


mppt = replace_once(
    mppt,

    "                reasons=tuple(reasons),\n"
    "            )\n"
    "        )",

    "                reasons=tuple(reasons),\n"
    "                poa=poa_cache[item.surface],\n"
    "                dc=dc,\n"
    "            )\n"
    "        )",

    "MPPT channel result",
)


# ============================================================
# VALIDATE BEFORE CHANGING ANY FILE
# ============================================================

compile(
    interval,
    str(interval_path),
    "exec",
)

compile(
    history,
    str(historian_path),
    "exec",
)

compile(
    mppt,
    str(mppt_path),
    "exec",
)

changes = (
    (interval_path, interval),
    (historian_path, history),
    (mppt_path, mppt),
)

for path, content in changes:

    backup = path.with_suffix(
        path.suffix + ".before_ges_v04"
    )

    if backup.exists():
        raise RuntimeError(
            f"Backup exists: {backup}; stopped safely"
        )


# ============================================================
# BACK UP AND APPLY
# ============================================================

for path, content in changes:

    backup = path.with_suffix(
        path.suffix + ".before_ges_v04"
    )

    copy2(path, backup)

    path.write_text(
        content,
        encoding="utf-8",
    )

print(
    "GES v0.4 source integration complete. "
    "Three original files backed up."
)
