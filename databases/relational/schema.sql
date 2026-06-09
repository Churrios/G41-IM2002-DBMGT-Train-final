-- ============================================================
--  TransitFlow PostgreSQL Schema
--  Seed data is loaded separately by: python skeleton/seed_postgres.py
--
--  TWO ROLES:
--    1. Relational  → dual-network transit data you design below
--    2. Vector      → policy documents for RAG (provided — do not modify)
-- ============================================================

-- ============================================================
--  STUDENT TASK — Design and create your relational tables here
--
--  Start from the mock data in train-mock-data/:
--    metro_stations.json, national_rail_stations.json
--    metro_schedules.json, national_rail_schedules.json
--    national_rail_seat_layouts.json
--    registered_users.json
--    bookings.json, metro_travel_history.json
--    payments.json, feedback.json
--
--  Think about:
--    - What tables do you need?
--    - What columns and data types?
--    - Which fields are primary keys? Which are foreign keys?
--    - What constraints make sense?
--
--  Apply your schema with:
--    docker-compose down -v && docker-compose up -d
-- ============================================================

-- PK design: VARCHAR(10/20) chosen over UUID/SERIAL throughout.
-- IDs are short, human-readable, and match the JSON mock data format
-- (e.g. RU001, NR01, MS_SCH01). Single-region system with no distributed
-- insert contention, so collision-resistant UUIDs are unnecessary overhead.

-- ============================================================
--  1. USERS
-- ============================================================

CREATE TABLE registered_users (
    -- PK: VARCHAR(10) over SERIAL/UUID — IDs must match JSON mock data keys (e.g. RU001);
    -- SERIAL would require remapping every seed reference; UUID adds no benefit at this scale.
    user_id          VARCHAR(10)   PRIMARY KEY,
    full_name        TEXT          NOT NULL,
    email            VARCHAR(200)  NOT NULL UNIQUE,
    -- password stores the full bcrypt hash string (salt embedded, no separate column needed)
    password         TEXT          NOT NULL,
    phone            VARCHAR(20),
    -- only year is collected (data minimisation — month/day not required by any feature)
    date_of_birth    DATE,
    secret_question  TEXT,
    secret_answer    TEXT,
    registered_at    TIMESTAMPTZ   DEFAULT NOW(),
    -- Soft delete: set is_active = FALSE instead of hard DELETE.
    -- Hard DELETE would cascade-break FK references in bookings and metro_travel_history,
    -- destroying historical records needed for auditing and tax compliance.
    -- In production a delete request would also anonymise PII columns (full_name, email, phone)
    -- while retaining booking records per statutory retention obligations.
    is_active        BOOLEAN       NOT NULL DEFAULT TRUE
);

-- ============================================================
--  2. STATIONS
--  lines 用 VARCHAR[] — 查詢用 @> 運算子
--  adjacent_stations 不存 SQL，交給 Neo4j
-- ============================================================

CREATE TABLE metro_stations (
    -- PK: VARCHAR(10) over SERIAL/UUID — station IDs are domain identifiers (e.g. MS01) used
    -- as FK targets across schedules, stops, and bookings; SERIAL would break all seed references.
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    -- Boolean flags mirror FK nullability; NOT NULL prevents ambiguous three-value logic
    is_interchange_metro         BOOLEAN       NOT NULL DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN       NOT NULL DEFAULT FALSE,
    -- nullable: not every metro station has a rail interchange
    interchange_nr_station_id    VARCHAR(10)
);

CREATE INDEX idx_metro_stations_lines ON metro_stations USING GIN (lines);

CREATE TABLE national_rail_stations (
    -- PK: VARCHAR(10) over SERIAL/UUID — same rationale as metro_stations; NR station IDs
    -- (e.g. NR01) are referenced by schedules, stops, and graph nodes in Neo4j.
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_national_rail BOOLEAN       NOT NULL DEFAULT FALSE,
    is_interchange_metro         BOOLEAN       NOT NULL DEFAULT FALSE,
    -- nullable: not every rail station has a metro interchange; SET NULL on metro station delete
    interchange_metro_station_id VARCHAR(10)   REFERENCES metro_stations(station_id) ON DELETE SET NULL
);

CREATE INDEX idx_national_rail_stations_lines ON national_rail_stations USING GIN (lines);

-- Deferred cross-reference: metro_stations → national_rail_stations
-- SET NULL: removing a rail station should not invalidate the metro station row
ALTER TABLE metro_stations
    ADD CONSTRAINT fk_interchange_nr
    FOREIGN KEY (interchange_nr_station_id)
    REFERENCES national_rail_stations(station_id)
    ON DELETE SET NULL;

-- ============================================================
--  3. SCHEDULES
--  travel_time_from_origin 用 JSONB — key-value map {"MS01": 0, ...}
--  stops 移至 junction tables (metro_schedule_stops / national_rail_schedule_stops)
--  以滿足 3NF：每個停靠站是獨立 row，位置由 stop_order 決定
-- ============================================================

CREATE TABLE metro_schedules (
    -- PK: VARCHAR(20) over SERIAL/UUID — schedule IDs (e.g. MS_SCH01) are mock data keys
    -- referenced by stops, bookings, and travel history; SERIAL would break all seed references.
    schedule_id              VARCHAR(20)   PRIMARY KEY,
    line                     VARCHAR(5)    NOT NULL,
    direction                VARCHAR(15)   NOT NULL,
    origin_station_id        VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id   VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    travel_time_from_origin  JSONB         NOT NULL,
    first_train_time         TIME          NOT NULL,
    last_train_time          TIME          NOT NULL,
    frequency_min            INT           NOT NULL,
    operates_on              VARCHAR(10)[] NOT NULL DEFAULT ARRAY['mon','tue','wed','thu','fri','sat','sun'],
    base_fare_usd            NUMERIC(6,2)  NOT NULL CHECK (base_fare_usd >= 0),
    per_stop_rate_usd        NUMERIC(6,2)  NOT NULL CHECK (per_stop_rate_usd >= 0)
);

CREATE TABLE national_rail_schedules (
    -- PK: VARCHAR(20) over SERIAL/UUID — same rationale as metro_schedules; NR schedule IDs
    -- (e.g. NR_SCH01) are mock data keys used across stops, seat_layouts, and bookings.
    schedule_id               VARCHAR(20)   PRIMARY KEY,
    line                      VARCHAR(10)   NOT NULL,
    service_type              VARCHAR(10)   NOT NULL CHECK (service_type IN ('normal', 'express')),
    direction                 VARCHAR(15)   NOT NULL,
    origin_station_id         VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id    VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    passed_through_stations   VARCHAR(10)[],
    travel_time_from_origin   JSONB         NOT NULL,
    first_train_time          TIME          NOT NULL,
    last_train_time           TIME          NOT NULL,
    frequency_min             INT           NOT NULL,
    operates_on               VARCHAR(10)[] NOT NULL DEFAULT ARRAY['mon','tue','wed','thu','fri','sat','sun'],
    std_base_fare_usd         NUMERIC(6,2)  NOT NULL CHECK (std_base_fare_usd >= 0),
    std_per_stop_rate_usd     NUMERIC(6,2)  NOT NULL CHECK (std_per_stop_rate_usd >= 0),
    first_base_fare_usd       NUMERIC(6,2)  NOT NULL CHECK (first_base_fare_usd >= 0),
    first_per_stop_rate_usd   NUMERIC(6,2)  NOT NULL CHECK (first_per_stop_rate_usd >= 0)
);

-- Junction tables for schedule stops (3NF: stop position is a proper FK row, not an array index)
-- CASCADE: stops belong to a schedule and are removed when the schedule is deleted.
CREATE TABLE metro_schedule_stops (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    stop_order   INT          NOT NULL,
    station_id   VARCHAR(10)  NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    PRIMARY KEY (schedule_id, stop_order)
);

CREATE TABLE national_rail_schedule_stops (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    stop_order   INT          NOT NULL,
    station_id   VARCHAR(10)  NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    PRIMARY KEY (schedule_id, stop_order)
);

-- ============================================================
--  4. SEAT LAYOUTS  (靜態配置，每班車固定)
--  可用性從 bookings 推導，不另開 inventory table
-- ============================================================

CREATE TABLE seat_layouts (
    -- Composite PK: (schedule_id, seat_id) is naturally unique; no surrogate key needed.
    -- CASCADE: seats belong to a schedule and should be removed when the schedule is deleted.
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    seat_id      VARCHAR(10)  NOT NULL,
    coach        VARCHAR(5)   NOT NULL,
    row_num      INT          NOT NULL,
    col_char     VARCHAR(5)   NOT NULL,
    fare_class   VARCHAR(10)  NOT NULL CHECK (fare_class IN ('standard', 'first')),
    PRIMARY KEY (schedule_id, seat_id)
);

-- ============================================================
--  5. BOOKINGS & TRAVEL HISTORY
-- ============================================================

CREATE TABLE bookings (
    -- PK: VARCHAR(20) over SERIAL/UUID — application-generated prefixed IDs (e.g. BK-A1B2C3)
    -- encode record type, aiding debugging without table lookups; UUID adds no benefit here.
    booking_id              VARCHAR(20)   PRIMARY KEY,
    user_id                 VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id) ON DELETE RESTRICT,
    schedule_id             VARCHAR(20)   NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id       VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id  VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    travel_date             DATE          NOT NULL,
    departure_time          TIME          NOT NULL,
    ticket_type             VARCHAR(10)   NOT NULL CHECK (ticket_type IN ('single', 'return')),
    fare_class              VARCHAR(10)   NOT NULL CHECK (fare_class IN ('standard', 'first')),
    coach                   VARCHAR(5)    NOT NULL,
    seat_id                 VARCHAR(10)   NOT NULL,
    stops_travelled         INT           NOT NULL,
    amount_usd              NUMERIC(8,2)  NOT NULL CHECK (amount_usd >= 0),
    status                  VARCHAR(15)   NOT NULL CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    booked_at               TIMESTAMPTZ   DEFAULT NOW(),
    travelled_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ
);

CREATE TABLE metro_travel_history (
    -- PK: VARCHAR(20) over SERIAL/UUID — same rationale as bookings; MT- prefix distinguishes
    -- metro trips from rail bookings (BK-) when both appear in payments and feedback tables.
    trip_id                 VARCHAR(20)   PRIMARY KEY,
    user_id                 VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id) ON DELETE RESTRICT,
    schedule_id             VARCHAR(20)   NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id       VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    destination_station_id  VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    travel_date             DATE          NOT NULL,
    ticket_type             VARCHAR(10)   NOT NULL CHECK (ticket_type IN ('single', 'return', 'day_pass')),
    day_pass_ref            VARCHAR(20),
    stops_travelled         INT           NOT NULL DEFAULT 0,
    amount_usd              NUMERIC(8,2)  NOT NULL CHECK (amount_usd >= 0),
    status                  VARCHAR(15)   NOT NULL CHECK (status IN ('confirmed', 'cancelled', 'completed')),
    purchased_at            TIMESTAMPTZ,
    travelled_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ
);

-- Partial unique index: prevents double-booking the same seat at DB level.
-- WHERE status != 'cancelled' allows re-booking a seat after cancellation.
CREATE UNIQUE INDEX uq_bookings_seat_per_date
    ON bookings(schedule_id, seat_id, travel_date)
    WHERE status != 'cancelled';

-- Composite index for availability checks (schedule + date + status filter)
CREATE INDEX idx_bookings_schedule_date ON bookings(schedule_id, travel_date, status);
-- Index for user booking history lookups
CREATE INDEX idx_bookings_user_id ON bookings(user_id);

-- ============================================================
--  6. PAYMENTS
--  booking_id 不加 FK — 同時參照 BK (bookings) 和 MT (metro_travel_history)
-- ============================================================

CREATE TABLE payments (
    -- PK: VARCHAR(20) over SERIAL/UUID — PM- prefix makes payment IDs immediately identifiable
    -- in logs and API responses without querying the table name.
    payment_id   VARCHAR(20)   PRIMARY KEY,
    booking_id   VARCHAR(20)   NOT NULL,
    -- amount_usd may be negative for refunds (money back to customer)
    amount_usd   NUMERIC(8,2)  NOT NULL,
    method       VARCHAR(20)   NOT NULL,
    status       VARCHAR(15)   NOT NULL CHECK (status IN ('paid', 'refunded', 'pending', 'failed')),
    paid_at      TIMESTAMPTZ   DEFAULT NOW(),
    refunded_at  TIMESTAMPTZ
);

-- Index for payment lookup by booking_id (query_payment_info)
CREATE INDEX idx_payments_booking_id ON payments(booking_id);

-- ============================================================
--  7. FEEDBACK
--  booking_id 不加 FK — 同時參照 BK (bookings) 和 MT (metro_travel_history)
-- ============================================================

CREATE TABLE feedback (
    -- PK: VARCHAR(20) over SERIAL/UUID — FB- prefix identifies feedback records across
    -- shared booking_id references (which span both bookings and metro_travel_history).
    feedback_id   VARCHAR(20)   PRIMARY KEY,
    booking_id    VARCHAR(20)   NOT NULL,
    -- SET NULL: feedback records are preserved anonymously if a user is deleted
    user_id       VARCHAR(10)   REFERENCES registered_users(user_id) ON DELETE SET NULL,
    rating        SMALLINT      NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    submitted_at  TIMESTAMPTZ   DEFAULT NOW()
);



-- ============================================================
--  TASK 6 EXTENSION: DELAY EVENT LOGGING
-- ============================================================
-- New table tracking real-time disruption events at stations.
-- station_id is a logical reference to either metro_stations or
-- national_rail_stations; PostgreSQL does not support a single FK
-- across two parent tables, so referential integrity is enforced
-- at the application layer.

CREATE TABLE delay_events (
    event_id      SERIAL        PRIMARY KEY,
    -- No FK: station_id may reference metro_stations or national_rail_stations;
    -- referential integrity is enforced at the application layer.
    station_id    VARCHAR(10)   NOT NULL,
    reported_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    severity      VARCHAR(10)   NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    description   TEXT          NOT NULL,
    -- NULL means the delay is still active; set by resolve_delay()
    resolved_at   TIMESTAMPTZ
);

-- Index for fast active-delay lookups (resolved_at IS NULL filter)
CREATE INDEX idx_delay_events_active ON delay_events(station_id) WHERE resolved_at IS NULL;


-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    -- 768-dim  → Ollama nomic-embed-text (default)
    -- 3072-dim → Gemini gemini-embedding-001
    -- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding ON policy_documents USING hnsw (embedding vector_cosine_ops);
