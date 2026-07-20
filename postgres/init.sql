
CREATE ROLE llm_reader LOGIN PASSWORD 'llm_password';

ALTER ROLE llm_reader
SET statement_timeout = '5s';

CREATE TABLE satellites (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    launch_date     DATE NOT NULL,
    orbit_type      VARCHAR(50),
    inclination_deg REAL,
    status          VARCHAR(30)
);

INSERT INTO satellites
(name, launch_date, orbit_type, inclination_deg, status)
VALUES
('Kosmos-2553', '2022-02-05', 'LEO', 97.4, 'ACTIVE'),
('Luch-5X',     '2023-08-17', 'GEO', 0.0, 'ACTIVE'),
('Meteor-M3',   '2024-11-28', 'SSO', 98.6, 'TESTING');


CREATE TABLE telemetry (
    id              BIGSERIAL PRIMARY KEY,
    satellite_id    INTEGER NOT NULL
        REFERENCES satellites(id),
    timestamp_utc   TIMESTAMP NOT NULL,
    latitude        DOUBLE PRECISION,
    longitude       DOUBLE PRECISION,
    altitude_km     DOUBLE PRECISION,
    velocity_kms    DOUBLE PRECISION,
    battery_percent INTEGER,
    temperature_c   REAL
);

INSERT INTO telemetry
(
satellite_id,
timestamp_utc,
latitude,
longitude,
altitude_km,
velocity_kms,
battery_percent,
temperature_c
)
VALUES
(1,'2026-07-01 10:00:00',55.73,37.61,521.2,7.62,94,18.5),
(1,'2026-07-01 10:05:00',56.12,39.04,521.4,7.62,94,18.7),
(2,'2026-07-01 10:00:00',0.0,52.1,35786,3.07,87,24.1),
(3,'2026-07-01 10:00:00',63.1,-14.2,814.3,7.45,100,12.0);


CREATE TABLE events (
    id              BIGSERIAL PRIMARY KEY,
    satellite_id    INTEGER
        REFERENCES satellites(id),
    event_time      TIMESTAMP NOT NULL,
    severity        VARCHAR(20),
    message         TEXT
);

INSERT INTO events
(
satellite_id,
event_time,
severity,
message
)
VALUES
(1,'2026-07-01 09:30:00','INFO','Attitude control initialized'),
(1,'2026-07-01 09:45:00','WARNING','Temperature exceeded nominal range'),
(2,'2026-07-01 08:15:00','INFO','Telemetry session completed'),
(3,'2026-07-01 11:00:00','ERROR','Telemetry packet checksum mismatch');


CREATE INDEX idx_telemetry_satellite
ON telemetry(satellite_id);

CREATE INDEX idx_telemetry_time
ON telemetry(timestamp_utc);

CREATE INDEX idx_events_satellite
ON events(satellite_id);

CREATE INDEX idx_events_time
ON events(event_time);


GRANT CONNECT ON DATABASE postgres TO llm_reader;

GRANT USAGE ON SCHEMA public TO llm_reader;

GRANT SELECT ON satellites TO llm_reader;
GRANT SELECT ON telemetry TO llm_reader;
GRANT SELECT ON events TO llm_reader;

WITH inserted_satellites AS (
      INSERT INTO satellites (name, launch_date, orbit_type, inclination_deg, status)
      SELECT
        'TEST-MCP-20260713-' || lpad(series_value::text, 3, '0'),
        DATE '2024-01-01' + series_value,
        CASE series_value % 3
          WHEN 0 THEN 'LEO'
          WHEN 1 THEN 'MEO'
          ELSE 'GEO'
        END,
        CASE series_value % 3
          WHEN 0 THEN 97.4
          WHEN 1 THEN 55.0
          ELSE 0.0
        END,
        CASE series_value % 4
          WHEN 0 THEN 'ACTIVE'
          WHEN 1 THEN 'TESTING'
          WHEN 2 THEN 'MAINTENANCE'
          ELSE 'INACTIVE'
        END
      FROM generate_series(1, 100) AS series_value
      RETURNING id
    ),
    numbered_satellites AS (
      SELECT id, row_number() OVER (ORDER BY id) AS sequence_number
      FROM inserted_satellites
    ),
    inserted_telemetry AS (
      INSERT INTO telemetry (
        satellite_id, timestamp_utc, latitude, longitude, altitude_km,
        velocity_kms, battery_percent, temperature_c
      )
      SELECT
        id,
        TIMESTAMP '2026-07-13 12:00:00' + sequence_number * INTERVAL '1 minute',
        -60.0 + sequence_number * 1.2,
        -170.0 + sequence_number * 3.4,
        CASE sequence_number % 3
          WHEN 0 THEN 520.0 + sequence_number * 0.1
          WHEN 1 THEN 20200.0 + sequence_number * 0.2
          ELSE 35786.0
        END,
        CASE sequence_number % 3
          WHEN 0 THEN 7.62
          WHEN 1 THEN 3.89
          ELSE 3.07
        END,
        50 + sequence_number % 51,
        5.0 + sequence_number * 0.25
      FROM numbered_satellites
      RETURNING id
    ),
    inserted_events AS (
      INSERT INTO events (satellite_id, event_time, severity, message)
      SELECT
        id,
        TIMESTAMP '2026-07-13 12:00:00' + sequence_number * INTERVAL '1 minute',
        CASE sequence_number % 4
          WHEN 0 THEN 'INFO'
          WHEN 1 THEN 'WARNING'
          WHEN 2 THEN 'ERROR'
          ELSE 'DEBUG'
        END,
        'Synthetic MCP test event #' || sequence_number
      FROM numbered_satellites
      RETURNING id
    )
    SELECT
      (SELECT count(*) FROM inserted_satellites) AS satellites_inserted,
      (SELECT count(*) FROM inserted_telemetry) AS telemetry_inserted,
      (SELECT count(*) FROM inserted_events) AS events_inserted;