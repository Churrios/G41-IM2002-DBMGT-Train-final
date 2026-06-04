# ✅ AI Session Context — TransitFlow

**How to use this file:**
At the start of every AI coding session, paste the full contents of this file as your first message to your AI assistant. This gives the AI the context it needs to produce code that fits your codebase and is consistent with your teammates' work.

**Who maintains this file:**
Whoever makes a schema change or architectural decision updates this file in the same commit. Treat it like a team contract.

---

## Project Overview

TransitFlow is a Python-based AI chat assistant for a fictional transit operator. It queries three databases — PostgreSQL (relational + vector), Neo4j (graph) — and uses an LLM to answer user questions. Our task as students is to design the database schema and implement the query functions in `databases/relational/queries.py` and `databases/graph/queries.py`.

## Tech Stack

- Language: Python 3.11+
- Relational DB: PostgreSQL via `psycopg2` with `RealDictCursor`
- Graph DB: Neo4j via the `neo4j` Python driver
- Vector search: `pgvector` extension (already implemented — do not modify)
- Web UI: Gradio
- LLM: Google Gemini or local Ollama (configured via `.env`)

## Coding Conventions

- **Naming:** `snake_case` for all Python names and SQL identifiers
- **Docstrings:** All functions must have a docstring with `Args:` and `Returns:` sections
- **Return types:** Use type hints. Read-only functions return `list[dict]` or `Optional[dict]`
- **Empty results:** Return `[]` or `None` (as documented), never raise an exception for "not found"
- **SQL:** Use `%s` placeholders for all user inputs — never string-format into SQL
- **Relational pattern:** Use `_connect()` helper + `psycopg2.extras.RealDictCursor`:
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Graph pattern:** Use `_driver()` helper + session:
  ```python
  with _driver() as driver:
      with driver.session() as session:
          result = session.run("MATCH ...", station_id=station_id)
          return [dict(record) for record in result]
  ```

## Agreed Relational Schema

> Source of truth: `databases/relational/schema.sql` — last reviewed 2026-05-28.

```sql
-- 1. USERS
CREATE TABLE registered_users (
    user_id          VARCHAR(10)   PRIMARY KEY,
    full_name        TEXT          NOT NULL,
    email            VARCHAR(200)  NOT NULL UNIQUE,
    password         TEXT          NOT NULL,   -- bcrypt hash, NEVER plaintext
    phone            VARCHAR(20),
    date_of_birth    DATE,
    secret_question  TEXT,
    secret_answer    TEXT,
    registered_at    TIMESTAMPTZ   DEFAULT NOW(),
    is_active        BOOLEAN       DEFAULT TRUE
);

-- 2. STATIONS
--    lines: VARCHAR[] queried with @> operator
--    adjacent_stations: NOT stored here — delegated to Neo4j
CREATE TABLE metro_stations (
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_metro         BOOLEAN       DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN       DEFAULT FALSE,
    interchange_nr_station_id    VARCHAR(10)   -- FK added after national_rail_stations is created
);

CREATE TABLE national_rail_stations (
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_national_rail BOOLEAN       DEFAULT FALSE,
    is_interchange_metro         BOOLEAN       DEFAULT FALSE,
    interchange_metro_station_id VARCHAR(10)   REFERENCES metro_stations(station_id)
);

ALTER TABLE metro_stations
    ADD CONSTRAINT fk_interchange_nr
    FOREIGN KEY (interchange_nr_station_id)
    REFERENCES national_rail_stations(station_id);

-- 3. SCHEDULES
--    stops_in_order: VARCHAR[] — use array_position() for stop ordering
--    travel_time_from_origin: JSONB map {"MS01": 0, "MS02": 3, ...}
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

-- 4. SEAT LAYOUTS (static config per schedule; availability derived from bookings)
CREATE TABLE seat_layouts (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    seat_id      VARCHAR(10)  NOT NULL,
    coach        VARCHAR(5)   NOT NULL,
    row_num      INT          NOT NULL,
    col_char     VARCHAR(5)   NOT NULL,
    fare_class   VARCHAR(10)  NOT NULL,
    PRIMARY KEY (schedule_id, seat_id)
);

-- 5. BOOKINGS & TRAVEL HISTORY
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

-- 6. PAYMENTS
--    booking_id has NO FK — it references both BK_ (bookings) and MT_ (metro_travel_history)
--    Identify table by prefix: BK_ = national rail, MT_ = metro
CREATE TABLE payments (
    payment_id   VARCHAR(20)   PRIMARY KEY,
    booking_id   VARCHAR(20)   NOT NULL,
    amount_usd   NUMERIC(8,2)  NOT NULL,
    method       VARCHAR(20)   NOT NULL,
    status       VARCHAR(15)   NOT NULL,
    paid_at      TIMESTAMPTZ   DEFAULT NOW(),
    refunded_at  TIMESTAMPTZ
);

-- 7. FEEDBACK
--    booking_id has NO FK — same polymorphic pattern as payments
CREATE TABLE feedback (
    feedback_id   VARCHAR(20)   PRIMARY KEY,
    booking_id    VARCHAR(20)   NOT NULL,
    user_id       VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    rating        SMALLINT      NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    submitted_at  TIMESTAMPTZ   DEFAULT NOW()
);
```

### Critical seeding order (FK dependency chain)

```
registered_users
→ metro_stations (insert WITHOUT interchange_nr_station_id)
→ national_rail_stations
→ UPDATE metro_stations SET interchange_nr_station_id (fill circular FK)
→ metro_schedules
→ national_rail_schedules
→ seat_layouts
→ bookings
→ metro_travel_history
→ payments
→ feedback
```

### JSON → column mapping gotchas

| JSON key | Schema column |
|---|---|
| `travel_time_from_origin_min` | `travel_time_from_origin` (JSONB) |
| `fare_classes.standard.base_fare` | `std_base_fare_usd` |
| `fare_classes.standard.per_stop_rate` | `std_per_stop_rate_usd` |
| `fare_classes.first.base_fare` | `first_base_fare_usd` |
| `fare_classes.first.per_stop_rate` | `first_per_stop_rate_usd` |
| coaches → seats (nested) | flatten to one row per seat in `seat_layouts` |

## Agreed Graph Schema

> **Status: CONFIRMED 2026-06-04 — Q1=A adopted (split-label model, aligned with grading standard).**
> Q1 split labels MetroStation / NationalRailStation ✓ | Q2 METRO_LINK / RAIL_LINK ✓ | Q3 INTERCHANGE_TO (bidirectional) ✓ | Q5 fare stored on edges ✓

```
Node labels:
  MetroStation
    Properties:
      station_id                    String   (e.g. "MS01")        -- node identity / unique constraint
      name                          String   (e.g. "Central Square")
      lines                         List<String>  (e.g. ["M1", "M2"])
      is_interchange_national_rail  Boolean  (true if it transfers to a rail station)

  NationalRailStation
    Properties:
      station_id                    String   (e.g. "NR01")        -- node identity / unique constraint
      name                          String   (e.g. "Central Station")
      lines                         List<String>  (e.g. ["NR1", "NR2"])
      is_interchange_metro          Boolean
      interchange_metro_station_id  String   (the MetroStation it transfers to, or null)

  (Split into MetroStation / NationalRailStation rather than one Station label,
   to match the grading standard which checks for both labels explicitly.)

Relationship types:
  METRO_LINK   (MetroStation)-[:METRO_LINK]->(MetroStation)
    Properties:
      line              String
      travel_time_min   Integer
      fare_usd          Float    -- round(1.0 + 0.5 * travel_time_min, 2); metro is single-tier (no fare_class)

  RAIL_LINK    (NationalRailStation)-[:RAIL_LINK]->(NationalRailStation)
    Properties:
      line                String
      travel_time_min     Integer
      fare_standard_usd   Float  -- round(2.0 + 1.2 * travel_time_min, 2)
      fare_first_usd      Float  -- round(2.0 + 2.0 * travel_time_min, 2)

  INTERCHANGE_TO  (MetroStation)-[:INTERCHANGE_TO]-(NationalRailStation)
    Properties:
      transfer_time_min   Integer  -- fixed 5 (spec does not mandate; professor confirmed a sensible custom value is OK)
    Note: seeded as TWO directed edges (metro->rail and rail->metro) so Dijkstra
          can traverse either direction; queries match it undirected: -[:INTERCHANGE_TO]-.
```

### Design rationale

| Decision | Choice | Reason |
|---|---|---|
| Split `MetroStation` / `NationalRailStation` | ✓ | Matches grading standard (Task 4 / Live A check both labels by name) |
| `METRO_LINK` / `RAIL_LINK` separate types | ✓ | Lets each network carry its own fare model on the edge; route queries can restrict to `'METRO_LINK\|RAIL_LINK'` and stay same-network |
| Fare stored on edges at seed time (Q5=A) | ✓ | `apoc.algo.dijkstra` can use a fare property directly as weight, so fare_class genuinely changes the chosen path (Live C2), not just the final total |
| `INTERCHANGE_TO` bidirectional, `transfer_time_min=5` | ✓ | Only `query_interchange_path` follows it (cross-network); excluded from shortest/cheapest so same-network routing returns found=False when unreachable |
| `station_id` as node identity | ✓ | Unique constraint per label; stable external key from the source JSON |

Topology: 30 nodes (20 MetroStation + 10 NationalRailStation),
66 edges (42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO).

## Function Signatures We Are Implementing

These are fixed contracts. AI-generated code must match these signatures exactly.

### Relational (`databases/relational/queries.py`)

```python
# Read-only
def query_national_rail_availability(origin_id: str, destination_id: str, travel_date: Optional[str] = None) -> list[dict]: ...
def query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]: ...
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]: ...
def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]: ...
def query_available_seats(schedule_id: str, travel_date: str, fare_class: str) -> list[dict]: ...
def query_user_profile(user_email: str) -> Optional[dict]: ...
def query_user_bookings(user_email: str) -> dict: ...  # returns {"national_rail": [...], "metro": [...]}
def query_payment_info(booking_id: str) -> Optional[dict]: ...

# Write operations
def execute_booking(user_id, schedule_id, origin_station_id, destination_station_id, travel_date, fare_class, seat_id, ticket_type="single") -> tuple[bool, dict | str]: ...
def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]: ...

# Auth
def register_user(email, first_name, surname, year_of_birth, password, secret_question, secret_answer) -> tuple[bool, str]: ...
def login_user(email: str, password: str) -> Optional[dict]: ...
def get_user_secret_question(email: str) -> Optional[str]: ...
def verify_secret_answer(email: str, answer: str) -> bool: ...
def update_password(email: str, new_password: str) -> bool: ...
```

### Graph (`databases/graph/queries.py`)

```python
def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict: ...
def query_cheapest_route(origin_id: str, destination_id: str, network: str = "auto", fare_class: str = "standard") -> dict: ...
def query_alternative_routes(origin_id, destination_id, avoid_station_id, network="auto", max_routes=3) -> list[list[dict]]: ...
def query_interchange_path(origin_id: str, destination_id: str) -> dict: ...
def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]: ...
def query_station_connections(station_id: str) -> list[dict]: ...
```

## Team Decisions Log

<!-- Add entries as you make decisions. Format: "Decision: X. Why: Y." -->

- [x] **2026-05-28** Polymorphic FK: `payments.booking_id` and `feedback.booking_id` have NO FK constraint. Why: they reference two tables (`bookings` BK_ prefix, `metro_travel_history` MT_ prefix). Identify by ID prefix at application layer.
- [x] **2026-05-28** Circular station FK: `metro_stations.interchange_nr_station_id` → `national_rail_stations`. Resolved by inserting metro rows first (NULL interchange), then NR rows, then UPDATE to fill the FK.
- [x] **2026-05-28** Password storage: `registered_users.password` stores **bcrypt hash only**. Never seed plaintext. Use `bcrypt.hashpw()` in `seed_postgres.py`.
- [x] **2026-05-28** `travel_time_from_origin` stored as **JSONB map** `{"station_id": minutes}` — not a separate table. Rationale: read-only lookup, no joins needed, JSON key is station_id.
- [x] **2026-05-28** `stops_in_order` and `lines` stored as **`VARCHAR(10)[]`** — queried with `@>` (contains) and `array_position()`. Avoids a junction table for ordered stop lists.
- [x] **2026-06-04** Graph schema migrated to split-label model (Q1=A): `MetroStation` / `NationalRailStation`, `METRO_LINK {line, travel_time_min, fare_usd}` / `RAIL_LINK {line, travel_time_min, fare_standard_usd, fare_first_usd}`, `INTERCHANGE_TO {transfer_time_min:5}` (bidirectional). Stats: 30 nodes (20 metro + 10 NR), 66 edges (42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO). Supersedes the 2026-05-28 single-Station design.

## Prompts That Worked

<!-- Share prompts that produced good output so teammates can reuse them. -->

### Schema design prompt that worked:
```
TODO — add a prompt here after your schema design workshop
```

### Query implementation prompt that worked:
```
TODO — add after implementing your first function
```
