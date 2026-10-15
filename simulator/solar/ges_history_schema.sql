
-- GES STEP 11 - ADDITIVE INVERTER HISTORIAN SCHEMA
-- Existing HES and production tables are not modified.

CREATE TABLE IF NOT EXISTS ges_parameter_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    component_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ges_inverter_intervals (
    run_id INTEGER NOT NULL,
    inverter_id TEXT NOT NULL,
    start_utc TEXT NOT NULL,
    end_utc TEXT NOT NULL,

    dc_voltage_v REAL,

    dc_offered_kw REAL NOT NULL
        CHECK(dc_offered_kw >= 0),

    dc_accepted_kw REAL NOT NULL
        CHECK(dc_accepted_kw >= 0),

    dc_rejected_kw REAL NOT NULL
        CHECK(dc_rejected_kw >= 0),

    ac_unclipped_kw REAL NOT NULL
        CHECK(ac_unclipped_kw >= 0),

    ac_available_kw REAL NOT NULL
        CHECK(ac_available_kw >= 0),

    ac_dispatched_kw REAL NOT NULL
        CHECK(ac_dispatched_kw >= 0),

    conversion_loss_kw REAL NOT NULL
        CHECK(conversion_loss_kw >= 0),

    clipping_loss_kw REAL NOT NULL
        CHECK(clipping_loss_kw >= 0),

    curtailment_kw REAL NOT NULL
        CHECK(curtailment_kw >= 0),

    interval_energy_kwh REAL NOT NULL
        CHECK(interval_energy_kwh >= 0),

    status TEXT NOT NULL,

    active_alarms_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,

    quality_flags_json TEXT NOT NULL,
    source_types_json TEXT NOT NULL,

    parameter_snapshot_id TEXT NOT NULL,

    source_timestamp_utc TEXT,
    received_at_utc TEXT,

    power_time_semantics TEXT NOT NULL,

    PRIMARY KEY (
        run_id,
        inverter_id,
        start_utc
    ),

    FOREIGN KEY (run_id, start_utc)
        REFERENCES production_intervals (
            run_id,
            start_utc
        ),

    FOREIGN KEY (parameter_snapshot_id)
        REFERENCES ges_parameter_snapshots (
            snapshot_id
        )
);

CREATE TABLE IF NOT EXISTS ges_inverter_alarm_events (
    run_id INTEGER NOT NULL,
    inverter_id TEXT NOT NULL,

    interval_start_utc TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,

    code TEXT NOT NULL,

    transition TEXT NOT NULL
        CHECK(transition IN ('RAISED', 'CLEARED')),

    time_semantics TEXT NOT NULL,

    PRIMARY KEY (
        run_id,
        inverter_id,
        interval_start_utc,
        code,
        transition
    ),

    FOREIGN KEY (
        run_id,
        inverter_id,
        interval_start_utc
    )
        REFERENCES ges_inverter_intervals (
            run_id,
            inverter_id,
            start_utc
        )
);

CREATE INDEX IF NOT EXISTS ges_inverter_history_lookup
    ON ges_inverter_intervals (
        run_id,
        inverter_id,
        start_utc
    );
