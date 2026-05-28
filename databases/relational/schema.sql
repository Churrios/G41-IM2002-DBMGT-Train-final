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

-- ============================================================
--  1. USERS
-- ============================================================

CREATE TABLE registered_users (
    user_id          VARCHAR(10)   PRIMARY KEY,
    full_name        TEXT          NOT NULL,
    email            VARCHAR(200)  NOT NULL UNIQUE,
    password         TEXT          NOT NULL,
    phone            VARCHAR(20),
    date_of_birth    DATE,
    secret_question  TEXT,
    secret_answer    TEXT,
    registered_at    TIMESTAMPTZ   DEFAULT NOW(),
    is_active        BOOLEAN       DEFAULT TRUE
);

-- ============================================================
--  2. STATIONS
--  lines 用 VARCHAR[] — 查詢用 @> 運算子
--  adjacent_stations 不存 SQL，交給 Neo4j
-- ============================================================

CREATE TABLE metro_stations (
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_metro         BOOLEAN       DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN       DEFAULT FALSE,
    interchange_nr_station_id    VARCHAR(10)
);

CREATE INDEX idx_metro_stations_lines ON metro_stations USING GIN (lines);

CREATE TABLE national_rail_stations (
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_national_rail BOOLEAN       DEFAULT FALSE,
    is_interchange_metro         BOOLEAN       DEFAULT FALSE,
    interchange_metro_station_id VARCHAR(10)   REFERENCES metro_stations(station_id)
);

CREATE INDEX idx_national_rail_stations_lines ON national_rail_stations USING GIN (lines);

ALTER TABLE metro_stations
    ADD CONSTRAINT fk_interchange_nr
    FOREIGN KEY (interchange_nr_station_id)
    REFERENCES national_rail_stations(station_id);

-- ============================================================
--  3. SCHEDULES
--  stops_in_order 用 VARCHAR[] — array_position() 查站序更簡潔
--  travel_time_from_origin 用 JSONB — key-value map {"MS01": 0, ...}
-- ============================================================

CREATE TABLE metro_schedules (
    schedule_id              VARCHAR(20)   PRIMARY KEY,
    line                     VARCHAR(5)    NOT NULL,
    direction                VARCHAR(15)   NOT NULL,
    origin_station_id        VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id   VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    stops_in_order           VARCHAR(10)[] NOT NULL,
    travel_time_from_origin  JSONB         NOT NULL,
    first_train_time         TIME          NOT NULL,
    last_train_time          TIME          NOT NULL,
    frequency_min            INT           NOT NULL,
    operates_on              VARCHAR(10)[] NOT NULL DEFAULT ARRAY['mon','tue','wed','thu','fri','sat','sun'],
    base_fare_usd            NUMERIC(6,2)  NOT NULL,
    per_stop_rate_usd        NUMERIC(6,2)  NOT NULL
);

CREATE INDEX idx_metro_schedules_stops ON metro_schedules USING GIN (stops_in_order);

CREATE TABLE national_rail_schedules (
    schedule_id               VARCHAR(20)   PRIMARY KEY,
    line                      VARCHAR(10)   NOT NULL,
    service_type              VARCHAR(10)   NOT NULL,
    direction                 VARCHAR(15)   NOT NULL,
    origin_station_id         VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id    VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    stops_in_order            VARCHAR(10)[] NOT NULL,
    passed_through_stations   VARCHAR(10)[],
    travel_time_from_origin   JSONB         NOT NULL,
    first_train_time          TIME          NOT NULL,
    last_train_time           TIME          NOT NULL,
    frequency_min             INT           NOT NULL,
    operates_on               VARCHAR(10)[] NOT NULL DEFAULT ARRAY['mon','tue','wed','thu','fri','sat','sun'],
    std_base_fare_usd         NUMERIC(6,2)  NOT NULL,
    std_per_stop_rate_usd     NUMERIC(6,2)  NOT NULL,
    first_base_fare_usd       NUMERIC(6,2)  NOT NULL,
    first_per_stop_rate_usd   NUMERIC(6,2)  NOT NULL
);

CREATE INDEX idx_nr_schedules_stops ON national_rail_schedules USING GIN (stops_in_order);

-- ============================================================
--  4. SEAT LAYOUTS  (靜態配置，每班車固定)
--  可用性從 bookings 推導，不另開 inventory table
-- ============================================================

CREATE TABLE seat_layouts (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    seat_id      VARCHAR(10)  NOT NULL,
    coach        VARCHAR(5)   NOT NULL,
    row_num      INT          NOT NULL,
    col_char     VARCHAR(5)   NOT NULL,
    fare_class   VARCHAR(10)  NOT NULL,
    PRIMARY KEY (schedule_id, seat_id)
);

-- ============================================================
--  5. BOOKINGS & TRAVEL HISTORY
-- ============================================================

CREATE TABLE bookings (
    booking_id              VARCHAR(20)   PRIMARY KEY,
    user_id                 VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    schedule_id             VARCHAR(20)   NOT NULL REFERENCES national_rail_schedules(schedule_id),
    origin_station_id       VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id  VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    travel_date             DATE          NOT NULL,
    departure_time          TIME          NOT NULL,
    ticket_type             VARCHAR(10)   NOT NULL,
    fare_class              VARCHAR(10)   NOT NULL,
    coach                   VARCHAR(5)    NOT NULL,
    seat_id                 VARCHAR(10)   NOT NULL,
    stops_travelled         INT           NOT NULL,
    amount_usd              NUMERIC(8,2)  NOT NULL,
    status                  VARCHAR(15)   NOT NULL,
    booked_at               TIMESTAMPTZ   DEFAULT NOW(),
    travelled_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ
);

CREATE TABLE metro_travel_history (
    trip_id                 VARCHAR(20)   PRIMARY KEY,
    user_id                 VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    schedule_id             VARCHAR(20)   NOT NULL REFERENCES metro_schedules(schedule_id),
    origin_station_id       VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id  VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    travel_date             DATE          NOT NULL,
    ticket_type             VARCHAR(10)   NOT NULL,
    day_pass_ref            VARCHAR(20),
    stops_travelled         INT,
    amount_usd              NUMERIC(8,2)  NOT NULL,
    status                  VARCHAR(15)   NOT NULL,
    purchased_at            TIMESTAMPTZ,
    travelled_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ
);

-- ============================================================
--  6. PAYMENTS
--  booking_id 不加 FK — 同時參照 BK (bookings) 和 MT (metro_travel_history)
-- ============================================================

CREATE TABLE payments (
    payment_id   VARCHAR(20)   PRIMARY KEY,
    booking_id   VARCHAR(20)   NOT NULL,
    amount_usd   NUMERIC(8,2)  NOT NULL,
    method       VARCHAR(20)   NOT NULL,
    status       VARCHAR(15)   NOT NULL,
    paid_at      TIMESTAMPTZ   DEFAULT NOW(),
    refunded_at  TIMESTAMPTZ
);

-- ============================================================
--  7. FEEDBACK
--  booking_id 不加 FK — 同時參照 BK (bookings) 和 MT (metro_travel_history)
-- ============================================================

CREATE TABLE feedback (
    feedback_id   VARCHAR(20)   PRIMARY KEY,
    booking_id    VARCHAR(20)   NOT NULL,
    user_id       VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    rating        SMALLINT      NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    submitted_at  TIMESTAMPTZ   DEFAULT NOW()
);



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
CREATE INDEX IF NOT EXISTS ON policy_documents USING hnsw (embedding vector_cosine_ops);
