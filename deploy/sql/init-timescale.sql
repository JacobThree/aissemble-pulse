-- Timescale + core tables for City Pulse (SPEC Appendix B + daily briefs).
-- Runs once on first DB init (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS vehicle_counts (
    time timestamptz NOT NULL,
    camera_location text NOT NULL,
    vehicle_count integer NOT NULL CHECK (vehicle_count >= 0)
);

SELECT create_hypertable('vehicle_counts', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_vehicle_counts_camera_time
    ON vehicle_counts (camera_location, time DESC);

CREATE TABLE IF NOT EXISTS daily_briefs (
    day date PRIMARY KEY,
    body text NOT NULL,
    generated_at timestamptz NOT NULL DEFAULT now()
);

-- Read-only role for Streamlit / dashboards (dev passwords only — rotate for real deploy)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'city_pulse_reader') THEN
        CREATE ROLE city_pulse_reader LOGIN PASSWORD 'city_pulse_reader';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE city_pulse TO city_pulse_reader;
GRANT USAGE ON SCHEMA public TO city_pulse_reader;
GRANT SELECT ON vehicle_counts, daily_briefs TO city_pulse_reader;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO city_pulse_reader;
