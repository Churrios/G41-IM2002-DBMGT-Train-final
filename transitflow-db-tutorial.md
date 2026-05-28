# TransitFlow — Database Design Tutorial

A practical guide to database design, grounded in the TransitFlow transit management system. Every concept here is demonstrated with real examples from the project code and data.

---

## Table of Contents

**Part 1 — Foundations**
1. [Introduction & Architecture Overview](#1-introduction--architecture-overview)
2. [Naming Conventions & Data Type Choices](#2-naming-conventions--data-type-choices)
3. [Relational Database Foundations](#3-relational-database-foundations)

**Part 2 — Schema Design**
4. [Choosing the Right Primary Key](#4-choosing-the-right-primary-key)
5. [Foreign Keys & Delete Propagation Design](#5-foreign-keys--delete-propagation-design)
6. [Indexes: What They Are and When to Add One](#6-indexes-what-they-are-and-when-to-add-one)
7. [JSONB for Semi-Structured Data](#7-jsonb-for-semi-structured-data)
8. [Polymorphic Associations](#8-polymorphic-associations)

**Part 3 — Security**
9. [Storing Passwords as Hashes](#9-storing-passwords-as-hashes)
10. [Prepared Statements & SQL Injection](#10-prepared-statements--sql-injection)

**Part 4 — Advanced Relational**
11. [Transactions](#11-transactions)
12. [Views](#12-views)
13. [Stored Procedures & Functions](#13-stored-procedures--functions)

**Part 5 — Graph Databases**
14. [Graph Databases & Neo4j](#14-graph-databases--neo4j)
15. [Cypher Query Language](#15-cypher-query-language)

**Part 6 — Vector Search**
16. [Vector Search with pgvector](#16-vector-search-with-pgvector)

**Part 7 — Practical Tips**
17. [Practical Tips & Pitfalls](#17-practical-tips--pitfalls)

---

## Part 1 — Foundations

---

### 1. Introduction & Architecture Overview

TransitFlow is a transit management system that handles two overlapping transport networks — a city metro and a national rail service — along with passenger booking, refunds, and an AI-powered help desk. It is a deliberately teaching-oriented project: every design decision you encounter is meant to be questioned, reasoned about, and improved.

#### 1.1 Three Databases, One Application

Most beginners assume one application means one database. TransitFlow uses three, each chosen for what it does best:

| Engine | Role | Why this engine? |
|---|---|---|
| **PostgreSQL 16** | Structured data: stations, schedules, users, bookings, payments | Strong ACID guarantees, rich SQL, JSON support, foreign keys |
| **pgvector** (PostgreSQL extension) | Semantic search over policy documents | Cosine similarity on high-dimensional vectors, co-located with Postgres |
| **Neo4j 5** | Route finding across the transit network | Graph traversals are natural; doing the same in SQL requires recursive CTEs that grow painful quickly |

This pattern — using multiple specialised database engines within one system — is called **polyglot persistence**. You pick the right tool for each job rather than forcing every problem through a single engine.

#### 1.2 How Data Flows

```
User request
     │
     ▼
  Agent (skeleton/agent.py)
     │
     ├──► PostgreSQL ─── stations, schedules, seats, bookings, users, payments
     │
     ├──► Neo4j ──────── route graph (shortest path, alternatives, interchange)
     │
     └──► pgvector ───── policy document similarity search (refund rules, etc.)
```

The agent layer decides which database to query. The databases themselves do not talk to each other — joins across engines happen in Python, not SQL.

---

### 2. Naming Conventions & Data Type Choices

Consistent naming is free documentation. A reader who understands your conventions can predict column names without looking them up. Inconsistent naming creates friction for every person who touches the code after you.

#### 2.1 Table Names

- **Plural, snake_case**: `metro_stations`, `national_rail_bookings`, `policy_documents`
- Do not mix styles: not `MetroStation`, not `metrostation`, not `metro_station` (singular)
- Use the full word: `payments`, not `pmts`; `schedules`, not `sched`

```sql
-- Good
CREATE TABLE metro_stations ( ... );
CREATE TABLE national_rail_bookings ( ... );

-- Avoid
CREATE TABLE MetroStation ( ... );
CREATE TABLE booking ( ... );        -- singular
CREATE TABLE nr_bkg ( ... );         -- abbreviations
```

#### 2.2 Column Names

| Pattern | Convention | Examples |
|---|---|---|
| Foreign key | `<referenced_table_singular>_id` | `user_id`, `schedule_id`, `station_id` |
| Timestamps | `<event>_at` | `booked_at`, `travelled_at`, `created_at` |
| Booleans | `is_<adjective>` | `is_active`, `is_interchange_metro` |
| Amounts | `<thing>_usd` or `<thing>_cents` | `amount_usd`, `base_fare_usd` |
| Ordered enums | plain noun | `status`, `direction`, `fare_class` |

From TransitFlow:
```sql
-- users table
registered_at   TIMESTAMPTZ    -- not: registration_time, created
is_active       BOOLEAN        -- not: active, user_active

-- national_rail_bookings
booked_at       TIMESTAMPTZ    -- when the booking was made
travelled_at    TIMESTAMPTZ    -- when the journey occurred (NULL if cancelled)
amount_usd      DECIMAL(8,2)   -- explicit currency in the column name
```

#### 2.3 Picking the Right Data Type

**Text**

| Type | Use when |
|---|---|
| `VARCHAR(n)` | You want a hard upper bound (e.g., `VARCHAR(200)` for a title) |
| `TEXT` | Unbounded text: comments, document content, free-form descriptions |

In PostgreSQL, `TEXT` and `VARCHAR` have identical storage performance. `VARCHAR(n)` is useful when you want the database to enforce a length constraint, not for performance.

**Numbers**

| Situation | Type | Why |
|---|---|---|
| Money / fares | `DECIMAL(10,2)` | Exact arithmetic; `FLOAT` introduces rounding errors |
| Counts, IDs | `INTEGER` / `BIGINT` | Use `BIGINT` if you expect > 2 billion rows |
| Averages, ratios | `NUMERIC` or `FLOAT` | Acceptable for approximate values |

```sql
-- Good: no rounding surprises
amount_usd      DECIMAL(8,2)
base_fare_usd   DECIMAL(6,2)

-- Dangerous for money
amount_usd      FLOAT   -- 1.10 + 2.20 = 3.3000000000000003
```

**Timestamps**

| Type | Use when |
|---|---|
| `TIMESTAMPTZ` | Almost always. Stores UTC, displays in session timezone. Use for `created_at`, `booked_at`, any event time |
| `TIMESTAMP` | Only when timezone is genuinely irrelevant (rare) |
| `DATE` | Calendar dates with no time component: `travel_date`, `date_of_birth` |
| `TIME` | Time of day with no date: `departure_time` |

```sql
-- From national_rail_bookings
travel_date     DATE           -- the day of travel, timezone-independent
departure_time  TIME           -- scheduled departure time
booked_at       TIMESTAMPTZ    -- when the booking was recorded (UTC)
```

**ENUM-like Patterns**

When a column has a small, stable set of allowed values you have three options:

```sql
-- Option 1: VARCHAR + CHECK constraint (simplest)
status  VARCHAR(20) CHECK (status IN ('confirmed', 'completed', 'cancelled'))

-- Option 2: PostgreSQL native ENUM (fast, enforced at type level)
CREATE TYPE booking_status AS ENUM ('confirmed', 'completed', 'cancelled');
status  booking_status

-- Option 3: Lookup table (most flexible, but requires a JOIN)
CREATE TABLE booking_statuses (code VARCHAR(20) PRIMARY KEY, label TEXT);
status  VARCHAR(20) REFERENCES booking_statuses(code)
```

TransitFlow uses Option 1 throughout (e.g., `status`, `ticket_type`, `fare_class`, `direction`). It is the easiest to work with and change. Use a native `ENUM` when you want the type system to catch invalid values at compile-time in a strongly-typed language; use a lookup table when the set of values is managed by business users (not developers).

---

### 3. Relational Database Foundations

#### 3.1 Tables, Columns, and Constraints

A relational table is a set of rows (records), each with the same columns (fields). Constraints are rules the database enforces automatically:

```sql
CREATE TABLE users (
    user_id       VARCHAR(10)   PRIMARY KEY,            -- uniqueness + not null
    email         VARCHAR(255)  NOT NULL UNIQUE,         -- no duplicates, required
    full_name     VARCHAR(200)  NOT NULL,
    date_of_birth DATE          NOT NULL,
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
    registered_at TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
```

Key constraints:
- `PRIMARY KEY` — uniquely identifies each row; implies `NOT NULL` and a unique index
- `NOT NULL` — the field must always have a value
- `UNIQUE` — no two rows may share this value (useful for natural identifiers like email)
- `DEFAULT` — value used when the column is omitted from an `INSERT`
- `CHECK` — arbitrary boolean expression the value must satisfy
- `REFERENCES` — foreign key; value must exist in another table

#### 3.2 Normal Forms — Rules for Reducing Redundancy

**First Normal Form (1NF):** Every column holds a single atomic value. No repeating groups, no arrays of values in a single column.

```
BEFORE — violates 1NF
┌─────────┬───────────────────┬──────────────────────┐
│ user_id │ email             │ phone_numbers        │
├─────────┼───────────────────┼──────────────────────┤
│ RU01    │ alice@example.com │ 555-1111, 555-2222   │  ← two values crammed into one cell
│ RU02    │ bob@example.com   │ 555-3333             │
└─────────┴───────────────────┴──────────────────────┘

AFTER — 1NF compliant (one value per cell)
┌─────────┬───────────────────┐     ┌─────────┬────────────┐
│ user_id │ email             │     │ user_id │ phone      │
├─────────┼───────────────────┤     ├─────────┼────────────┤
│ RU01    │ alice@example.com │     │ RU01    │ 555-1111   │
│ RU02    │ bob@example.com   │     │ RU01    │ 555-2222   │
└─────────┴───────────────────┘     │ RU02    │ 555-3333   │
                                     └─────────┴────────────┘
```

**Second Normal Form (2NF):** Every non-key column depends on the *whole* primary key, not just part of it. This only applies to composite keys.

```
BEFORE — violates 2NF  (composite PK = schedule_id + seat_id)
┌─────────────┬─────────┬──────────┬──────┐
│ schedule_id │ seat_id │ seat_row │ line │  ← 'line' depends only on schedule_id,
├─────────────┼─────────┼──────────┼──────┤     not on the full (schedule_id, seat_id) key
│ NR_SCH01   │ A01     │ 1        │ NR1  │
│ NR_SCH01   │ A02     │ 1        │ NR1  │  ← 'NR1' repeated for every seat
│ NR_SCH02   │ A01     │ 1        │ NR2  │
└─────────────┴─────────┴──────────┴──────┘

AFTER — 2NF compliant ('line' moved to its own table)
┌─────────────┬──────┐     ┌─────────────┬─────────┬──────────┐
│ schedule_id │ line │     │ schedule_id │ seat_id │ seat_row │
├─────────────┼──────┤     ├─────────────┼─────────┼──────────┤
│ NR_SCH01   │ NR1  │     │ NR_SCH01   │ A01     │ 1        │
│ NR_SCH02   │ NR2  │     │ NR_SCH01   │ A02     │ 1        │
└─────────────┴──────┘     │ NR_SCH02   │ A01     │ 1        │
                             └─────────────┴─────────┴──────────┘
```

**Third Normal Form (3NF):** Every non-key column depends directly on the primary key, not on another non-key column (no transitive dependencies).

```
BEFORE — violates 3NF
┌────────────┬────────────┬──────────────────┐
│ booking_id │ station_id │ station_name     │  ← station_name depends on station_id,
├────────────┼────────────┼──────────────────┤     not on booking_id  (transitive dependency)
│ BK-001     │ NR01       │ Central Station  │
│ BK-002     │ NR01       │ Central Station  │  ← name duplicated across rows
│ BK-003     │ NR03       │ Riverside Park   │
└────────────┴────────────┴──────────────────┘

AFTER — 3NF compliant (station_name lives in national_rail_stations)
┌────────────┬────────────┐     ┌────────────┬──────────────────┐
│ booking_id │ station_id │     │ station_id │ station_name     │
├────────────┼────────────┤     ├────────────┼──────────────────┤
│ BK-001     │ NR01       │ ──► │ NR01       │ Central Station  │
│ BK-002     │ NR01       │ ──► │ NR03       │ Riverside Park   │
│ BK-003     │ NR03       │ ──► └────────────┴──────────────────┘
└────────────┴────────────┘     (JOIN on station_id to get the name)
```

Fix: store `station_id` in the bookings table; look up the name by joining to `metro_stations`.

#### 3.3 When It Is Acceptable to Break the Rules

Normalisation is a tool, not a religion. You may intentionally break it for:

1. **Performance**: denormalise a frequently-joined column to avoid a JOIN on a hot query path
2. **Ordered data**: storing an array of stops as JSONB rather than a junction table (see section 7)
3. **Snapshot data**: a payment record should store `amount_usd` directly, not derive it — fares may change after the booking is made

The `national_rail_seats` table in TransitFlow is a deliberate denormalisation. The source data stores seat layouts as nested JSON:
```json
{
  "layout_id": "SL01",
  "schedule_id": "NR_SCH01",
  "coaches": [
    {
      "coach": "A",
      "fare_class": "first",
      "seats": [
        {"seat_id": "A01", "row": 1, "column": "A"},
        {"seat_id": "A02", "row": 1, "column": "B"}
      ]
    }
  ]
}
```

A fully normalised schema would require three tables (`layouts`, `coaches`, `seats`):

```
NORMALIZED — 3 tables, requires 2 JOINs for a seat query
┌──────────────┬─────────────┐
│   layouts    │             │
├──────────────┼─────────────┤
│ layout_id    │ SL01        │
│ schedule_id  │ NR_SCH01    │
└──────┬───────┴─────────────┘
       │ 1
       │ ∞
┌──────▼───────┬─────────────┬────────────┐
│   coaches    │             │            │
├──────────────┼─────────────┼────────────┤
│ coach_id     │ SL01-A      │ SL01-B     │
│ layout_id    │ SL01        │ SL01       │
│ coach        │ A           │ B          │
│ fare_class   │ first       │ standard   │
└──────┬───────┴──────┬──────┴────────────┘
       │              │ 1
       │              │ ∞
       │    ┌─────────▼─────────────────────┐
       │    │            seats              │
       │    ├───────────────────────────────┤
       │    │ seat_id   │ coach_id  │ row   │
       │    │ A01       │ SL01-A    │  1    │
       │    │ A02       │ SL01-A    │  1    │
       │    │ B01       │ SL01-B    │  1    │
       │    └───────────────────────────────┘

DENORMALIZED — 1 flat table, no JOINs needed
┌─────────────┬─────────┬───────┬────────────┬──────────┬────────────┐
│ schedule_id │ seat_id │ coach │ fare_class │ seat_row │ seat_column│
├─────────────┼─────────┼───────┼────────────┼──────────┼────────────┤
│ NR_SCH01   │ A01     │ A     │ first      │ 1        │ A          │
│ NR_SCH01   │ A02     │ A     │ first      │ 1        │ B          │
│ NR_SCH01   │ B01     │ B     │ standard   │ 1        │ A          │
└─────────────┴─────────┴───────┴────────────┴──────────┴────────────┘
```

Instead, TransitFlow flattens everything into one table:

```sql
CREATE TABLE national_rail_seats (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    seat_id      VARCHAR(10)  NOT NULL,
    coach        VARCHAR(5)   NOT NULL,
    fare_class   VARCHAR(20)  NOT NULL,
    seat_row     INTEGER      NOT NULL,
    seat_column  VARCHAR(5)   NOT NULL,
    PRIMARY KEY (schedule_id, seat_id)
);
```

Now a query for available seats on a given schedule is a simple `SELECT` on one table. The trade-off: if a coach's fare class changes, you update many rows instead of one. For a transit timetable that is essentially read-only after seeding, this is the right call.

---

## Part 2 — Schema Design

---

### 4. Choosing the Right Primary Key

The primary key uniquely identifies every row. Choosing the wrong strategy causes problems that are painful to fix later — you cannot easily change a PK after data is live.

#### 4.1 Auto-Increment (`SERIAL` / `BIGSERIAL`)

PostgreSQL generates a new integer each time a row is inserted.

```sql
CREATE TABLE policy_documents (
    id      SERIAL PRIMARY KEY,   -- 1, 2, 3, 4 …
    title   VARCHAR(200) NOT NULL
);
```

**Pros:**
- Simple, zero application code required
- Compact (4 or 8 bytes)
- Naturally ordered — newer rows have larger IDs
- Easy to read and remember in tests and logs

**Cons:**
- Sequential IDs leak information (a user can guess that booking ID 42 exists, and that there are at least 42 bookings)
- Problematic in distributed systems — multiple nodes generating IDs will collide without coordination
- Exposes your growth rate to anyone who creates two records and compares IDs

TransitFlow uses `SERIAL` only for the `policy_documents` table, which is internal and never shown to users.

#### 4.2 UUID (`gen_random_uuid()`)

A Universally Unique Identifier is a 128-bit random number formatted as `550e8400-e29b-41d4-a716-446655440000`.

```sql
CREATE TABLE sessions (
    session_id  UUID  PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     VARCHAR(10)
);
```

**Pros:**
- Globally unique — safe to generate on any node without coordination
- Does not reveal row counts or sequence
- Good for user-facing IDs (tokens, public API IDs)

**Cons:**
- 16 bytes vs 4 bytes — larger index, more storage
- Random UUIDs fragment the B-tree index (each insert lands at a random location), causing more disk writes and cache misses on large tables
- Hard to read and remember

**UUIDv7** solves the fragmentation problem by embedding a timestamp in the first 48 bits, making IDs time-ordered while still being globally unique. It is available in PostgreSQL 17+ via `gen_random_uuid()` variants, and in application libraries for earlier versions.

#### 4.3 Natural Keys

A natural key is a real-world identifier that is inherently unique — a station code, a passport number, a product SKU.

TransitFlow uses natural keys extensively:

```sql
-- Station codes are stable, human-readable, and used everywhere
CREATE TABLE metro_stations (
    station_id  VARCHAR(10) PRIMARY KEY   -- "MS01", "MS02", ... "MS20"
);

CREATE TABLE national_rail_stations (
    station_id  VARCHAR(10) PRIMARY KEY   -- "NR01", "NR02", ... "NR10"
);
```

**Pros:**
- Human-readable; you can write a query with `WHERE station_id = 'MS01'` and understand it
- Already present in source data — no ID mapping needed
- Saves a JOIN when you already have the natural key

**Cons:**
- Natural keys can change (a station is renamed; a product code is retired)
- They may not be truly unique across all time (recycled codes)
- They leak the classification system to external parties

For **reference data that is stable and owned by your system** (station codes, schedule codes), natural keys are a pragmatic choice. For **user-generated data** (bookings, payments), use a surrogate key.

#### 4.4 Application-Generated Random Strings

TransitFlow generates booking and payment IDs in Python before inserting them:

```python
# databases/relational/queries.py
def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"

def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"
```

This produces IDs like `BK-X7K2MQ` and `PM-3RV9TW`.

**Pros:**
- Human-scannable and short enough to read aloud (useful for customer support)
- Prefix encodes the type (`BK` = booking, `MT` = metro trip, `PM` = payment)
- Does not require a database round-trip to generate

**Cons:**
- Must handle collision — 36^6 ≈ 2 billion combinations sounds large, but at scale a `UNIQUE` constraint + retry loop is needed
- Not time-ordered

#### 4.5 Composite Keys

When no single column uniquely identifies a row, combine two:

```sql
CREATE TABLE national_rail_seats (
    schedule_id  VARCHAR(20)  NOT NULL,
    seat_id      VARCHAR(10)  NOT NULL,
    ...
    PRIMARY KEY (schedule_id, seat_id)   -- seat "A01" exists on every schedule
);
```

Seat `A01` is not unique on its own — every schedule has a seat `A01`. But the combination `(NR_SCH01, A01)` is globally unique.

**Use composite keys when:**
- The combination is the natural identity (seat + schedule, student + course)
- You want the database to enforce the no-duplicate constraint at the pair level

**Avoid composite keys as foreign keys** — referencing tables must carry both columns, which is verbose.

#### 4.6 Decision Matrix

| Situation | Recommended PK |
|---|---|
| Internal lookup table (rarely seen by users) | `SERIAL` |
| User-facing IDs where count must not leak | UUID or random string |
| Reference data with stable, human-readable codes | Natural key (`VARCHAR`) |
| Short IDs for customer support (booking ref) | Application-generated random string |
| Rows identified by two parent entities | Composite key |

---

### 5. Foreign Keys & Delete Propagation Design

A foreign key (FK) is a column whose value must exist as a primary key in another table. It enforces referential integrity — you cannot have a booking for a user that does not exist.

```sql
CREATE TABLE national_rail_bookings (
    booking_id  VARCHAR(15)  PRIMARY KEY,
    user_id     VARCHAR(10)  NOT NULL REFERENCES users(user_id),
    schedule_id VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    ...
);
```

#### 5.1 Delete Propagation Options

When you delete the parent row, what happens to children that reference it?

**`ON DELETE RESTRICT`** (default) — Block the deletion if any child row exists.
```sql
user_id  VARCHAR(10) REFERENCES users(user_id) ON DELETE RESTRICT
```
*Use when:* You never want orphaned records, and deleting the parent should be an error if children exist. Safest option for most business data.

**`ON DELETE CASCADE`** — Automatically delete all child rows when the parent is deleted.
```sql
user_id  VARCHAR(10) REFERENCES users(user_id) ON DELETE CASCADE
```
*Use when:* Child rows have no meaning without the parent (e.g., session tokens, log entries for a deleted entity).
*Danger:* A single `DELETE FROM users WHERE user_id = 'RU01'` silently wipes all bookings, payments, and feedback for that user. Always think twice before using `CASCADE` on business records.

**`ON DELETE SET NULL`** — Set the FK column to `NULL` when the parent is deleted.
```sql
day_pass_ref  VARCHAR(15) REFERENCES metro_trips(trip_id) ON DELETE SET NULL
```
*Use when:* The child row can meaningfully exist without the parent (e.g., a metro trip that referenced a day-pass can still exist as an orphaned record after the original day-pass record is removed). The FK column must be nullable.

**`ON DELETE NO ACTION`** — Same as `RESTRICT` but the check is deferred to the end of the transaction. Rarely needed; prefer `RESTRICT` for clarity.

#### 5.2 Worked Example: Deleting a User

Consider the three-level ownership chain in TransitFlow:

```
users                national_rail_bookings           payments
┌──────────────┐     ┌──────────────────────────┐     ┌──────────────────┐
│ user_id: RU01│────►│ booking_id: BK-X7K2MQ    │────►│ payment_id:      │
│ email: alice │     │ user_id: RU01             │     │   PM-3RV9TW      │
│ is_active: T │     │ amount_usd: 8.50          │     │ transaction_ref: │
└──────────────┘     │ status: confirmed         │     │   BK-X7K2MQ      │
                     └──────────────────────────┘     └──────────────────┘
```

What happens when you `DELETE FROM users WHERE user_id = 'RU01'`?

```
ON DELETE RESTRICT (default)
  DELETE users ──► ✗ BLOCKED
                     "violates foreign key constraint on national_rail_bookings"
                     Nothing is deleted.

ON DELETE CASCADE (on bookings)
  DELETE users ──► booking auto-deleted ──► payment ORPHANED
                                             (no FK on payments → booking)
                     ⚠ Payment record now points to a non-existent booking.

SOFT DELETE (recommended for business data)
  UPDATE users SET is_active = FALSE ──► booking intact ──► payment intact
                     Full history preserved. Account can be reactivated.
                     Regulators can still audit past transactions.
```

**For TransitFlow (and most business applications), the right answer is soft delete + restrict.** You almost never want to permanently destroy financial records.

#### 5.3 Cross-Network Foreign Keys

Metro stations and national rail stations can interchange with each other. TransitFlow models this bidirectionally:

```sql
CREATE TABLE metro_stations (
    station_id                          VARCHAR(10) PRIMARY KEY,
    interchange_national_rail_station_id VARCHAR(10) REFERENCES national_rail_stations(station_id)
    -- NULL if not an interchange
);

CREATE TABLE national_rail_stations (
    station_id                  VARCHAR(10) PRIMARY KEY,
    interchange_metro_station_id VARCHAR(10) REFERENCES metro_stations(station_id)
);
```

This is a **circular reference** — `metro_stations` references `national_rail_stations` and vice versa. You must create one table before the other, then `ALTER TABLE` to add the second FK, or use `DEFERRABLE INITIALLY DEFERRED` constraints.

#### 5.4 Self-Referencing FK

A metro day pass covers unlimited trips on one day. When a passenger uses a day pass for the second (or third) time, the new trip row links back to the original:

```sql
CREATE TABLE metro_trips (
    trip_id      VARCHAR(15) PRIMARY KEY,
    user_id      VARCHAR(10) NOT NULL REFERENCES users(user_id),
    day_pass_ref VARCHAR(15) REFERENCES metro_trips(trip_id) ON DELETE SET NULL,
    -- NULL for the original day-pass purchase; points to first trip for subsequent uses
    ...
);
```

The resulting rows form a singly-linked list within the same table:

```
metro_trips table
┌──────────┬─────────┬──────────────┬──────────────┬────────────┐
│ trip_id  │ user_id │ day_pass_ref │ ticket_type  │ amount_usd │
├──────────┼─────────┼──────────────┼──────────────┼────────────┤
│ MT-0041  │ RU01    │ NULL         │ day_pass     │ 5.00       │ ← original purchase
│ MT-0042  │ RU01    │ MT-0041      │ day_pass     │ 0.00       │ ← 2nd use, links back
│ MT-0043  │ RU01    │ MT-0041      │ day_pass     │ 0.00       │ ← 3rd use, links back
└──────────┴─────────┴──────────────┴──────────────┴────────────┘
                           │                │
                           └───────┬────────┘
                                   ▼
                               MT-0041  (the original day-pass row)
```

A column referencing its own table's primary key is a **self-referencing foreign key**. It is natural for hierarchical structures (parent category → child category, original post → reply, day pass → subsequent use).

#### 5.5 Soft Delete Pattern

Instead of physically deleting a user, you mark them inactive:

```sql
-- Schema
is_active  BOOLEAN NOT NULL DEFAULT TRUE

-- Application code
UPDATE users SET is_active = FALSE WHERE user_id = 'RU01';

-- All queries filter out inactive users
SELECT * FROM users WHERE user_id = %s AND is_active = TRUE;
```

**Advantages:**
- Full audit trail — you can see who existed and what they did
- Recoverable — you can reactivate an account
- No cascade complexity — bookings remain intact
- Regulators sometimes require you to keep data for years even after account closure

**Disadvantage:** Queries must always remember to filter `WHERE is_active = TRUE`. A view (see section 12) can hide this complexity.

---

### 6. Indexes: What They Are and When to Add One

An index is a separate data structure the database maintains alongside your table to speed up lookups. Without an index, the database reads every row to find matching records — called a **sequential scan**. With an index on the searched column, it jumps directly to the matching rows.

#### 6.1 B-Tree Index (The Default)

A B-tree is a balanced tree where each node points to a range of values. It supports `=`, `<`, `>`, `BETWEEN`, `LIKE 'prefix%'`, and `ORDER BY` efficiently.

```sql
-- Automatically created by PRIMARY KEY and UNIQUE constraints:
CREATE TABLE users (
    user_id  VARCHAR(10) PRIMARY KEY,       -- creates a B-tree index on user_id
    email    VARCHAR(255) NOT NULL UNIQUE   -- creates a B-tree index on email
);

-- Explicitly created for FK lookups:
CREATE INDEX ON national_rail_bookings (user_id);
CREATE INDEX ON payments (transaction_ref);
```

Every time you `SELECT ... WHERE user_id = 'RU01'`, the database uses the B-tree index to find that row in O(log n) steps instead of O(n).

#### 6.2 When to Add an Index

**Always index:**
- Columns declared as `PRIMARY KEY` or `UNIQUE` (automatic)
- Foreign key columns — PostgreSQL does not create these automatically, but they are needed for fast `JOIN` and `ON DELETE` enforcement
- Columns that appear in `WHERE`, `JOIN ON`, or `ORDER BY` on large, frequently-queried tables

**Do not index:**
- Every column — indexes slow down `INSERT`, `UPDATE`, and `DELETE` because the index must be updated alongside the table
- Columns with very low cardinality (e.g., a boolean column) — the index provides little benefit if half the rows match
- Small tables (a few hundred rows) — a sequential scan is faster than an index lookup for small tables

From TransitFlow:
```sql
-- Needed: user's booking history is a common query
CREATE INDEX ON national_rail_bookings (user_id);
CREATE INDEX ON metro_trips (user_id);

-- Needed: polymorphic lookup by transaction reference
CREATE INDEX ON payments (transaction_ref);
CREATE INDEX ON feedback (transaction_ref);

-- Not needed: schedule_id has very few values
-- (there are only a handful of schedules)
```

#### 6.3 GIN Index for JSONB

When querying inside a JSONB column — checking if an array contains a value — the standard B-tree index does not help. Use GIN (Generalised Inverted Index) instead:

```sql
-- Searching for schedules that operate on a given day
CREATE INDEX ON metro_schedules USING GIN (operates_on);

-- Query (GIN-accelerated)
SELECT * FROM metro_schedules WHERE operates_on @> '["mon"]';
```

#### 6.4 HNSW Index for Vectors

Approximate nearest-neighbour search on a `vector` column:

```sql
CREATE INDEX ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

`hnsw` (Hierarchical Navigable Small World) trades a small accuracy loss for vastly faster similarity search. Without it, every similarity query reads every row and computes the full distance — unusable at scale.

#### 6.5 Diagnosing with `EXPLAIN ANALYZE`

To see whether your index is being used:

```sql
EXPLAIN ANALYZE
SELECT * FROM national_rail_bookings WHERE user_id = 'RU01';
```

Look for `Index Scan` (good) vs `Seq Scan` (the database ignored your index — check if the table is small or the index is wrong).

---

### 7. JSONB for Semi-Structured Data

PostgreSQL's `JSONB` type stores JSON as a parsed binary — you can index it, query inside it, and update individual keys. It is useful for data that is semi-structured: mostly consistent, but with variations.

#### 7.1 Ordered Stop Sequences

A schedule's stops must be stored in order. Compare the two approaches side-by-side using a real metro schedule (line M1, northbound):

```
NORMALIZED APPROACH — junction table schedule_stops
┌─────────────┬────────────┬────────────┐
│ schedule_id │ station_id │ stop_order │
├─────────────┼────────────┼────────────┤
│ MS_SCH01   │ MS20       │ 1          │
│ MS_SCH01   │ MS05       │ 2          │
│ MS_SCH01   │ MS01       │ 3          │
│ MS_SCH01   │ MS02       │ 4          │
│ MS_SCH01   │ MS03       │ 5          │
│ MS_SCH01   │ MS04       │ 6          │
│ MS_SCH01   │ MS17       │ 7          │
└─────────────┴────────────┴────────────┘
  7 rows for one schedule's stop list

JSONB APPROACH — everything lives in the schedule row itself
┌─────────────┬───────────────────────────────────────────────────────┐
│ schedule_id │ stops_in_order                                        │
├─────────────┼───────────────────────────────────────────────────────┤
│ MS_SCH01   │ ["MS20","MS05","MS01","MS02","MS03","MS04","MS17"]    │
└─────────────┴───────────────────────────────────────────────────────┘
  1 row, no JOIN needed

JSONB APPROACH — travel time map in the same row
┌─────────────┬──────────────────────────────────────────────────────────────────┐
│ schedule_id │ travel_time_from_origin_min                                      │
├─────────────┼──────────────────────────────────────────────────────────────────┤
│ MS_SCH01   │ {"MS20":0,"MS05":2,"MS01":5,"MS02":8,"MS03":11,"MS04":14,...}   │
└─────────────┴──────────────────────────────────────────────────────────────────┘
```

Compare the queries to answer "does schedule MS_SCH01 stop at MS01?":

```sql
-- Normalized: requires a JOIN
SELECT 1
FROM metro_schedules s
JOIN schedule_stops ss ON s.schedule_id = ss.schedule_id
WHERE s.schedule_id = 'MS_SCH01'
  AND ss.station_id = 'MS01';

-- JSONB: single table, no JOIN
SELECT 1
FROM metro_schedules
WHERE schedule_id = 'MS_SCH01'
  AND stops_in_order @> '["MS01"]'::jsonb;
```

A normalized approach would use a junction table with a sequence column:

```sql
-- Normalized (more tables, more joins)
CREATE TABLE schedule_stops (
    schedule_id  VARCHAR(20),
    station_id   VARCHAR(10),
    stop_order   INTEGER,
    PRIMARY KEY (schedule_id, station_id)
);
```

TransitFlow uses JSONB arrays instead:

```sql
stops_in_order  JSONB NOT NULL
-- Example value: ["MS20", "MS05", "MS01", "MS02", "MS03", "MS04", "MS17"]
```

And a JSONB map for travel times:

```sql
travel_time_from_origin_min  JSONB NOT NULL
-- Example value: {"MS20": 0, "MS05": 2, "MS01": 5, "MS02": 8, "MS03": 11}
```

#### 7.2 Querying JSONB

```sql
-- Check if a station is in the stops array
SELECT schedule_id
FROM metro_schedules
WHERE stops_in_order @> '["MS01"]'::jsonb;

-- Extract all stops as rows
SELECT schedule_id, jsonb_array_elements_text(stops_in_order) AS station_id
FROM metro_schedules;

-- Get travel time for a specific station
SELECT travel_time_from_origin_min->>'MS05' AS minutes
FROM metro_schedules
WHERE schedule_id = 'MS_SCH01';
```

Key JSONB operators:
| Operator | Meaning | Example |
|---|---|---|
| `->` | Get value as JSON | `col->'key'` → `"value"` |
| `->>` | Get value as text | `col->>'key'` → `value` |
| `@>` | Contains (for arrays/objects) | `col @> '["MS01"]'` |
| `jsonb_array_elements_text()` | Expand array to rows | Useful in `FROM` or `WHERE` |

#### 7.3 When to Use JSONB vs a Normalized Table

| Use JSONB | Use a normalized table |
|---|---|
| The internal structure varies per row | All rows have the same shape |
| You mainly read the whole blob | You frequently filter/join on individual fields |
| The data is ordered and sequence matters | Order can be encoded in a sort column |
| You are wrapping external JSON APIs | You need foreign key constraints on elements |

#### 7.4 Flattening Nested JSON

Source data often arrives deeply nested. The seat layout JSON has three levels:
`layout → coaches → seats`. If you store it as-is, every seat availability query must unpack the nesting in application code.

The solution: **flatten on write, query flat data**.

```
SOURCE JSON (3 levels deep)                    FLAT DATABASE ROWS
─────────────────────────────────              ──────────────────────────────────────────────────────────────
{                                              schedule_id  seat_id  coach  fare_class  seat_row  seat_column
  "schedule_id": "NR_SCH01",                  ───────────  ───────  ─────  ──────────  ────────  ───────────
  "coaches": [                    flatten      NR_SCH01    A01      A      first       1         A
    {                            ─────────►    NR_SCH01    A02      A      first       1         B
      "coach": "A",                            NR_SCH01    A03      A      first       2         A
      "fare_class": "first",                   NR_SCH01    B01      B      standard    1         A
      "seats": [                               NR_SCH01    B02      B      standard    1         B
        {"seat_id":"A01","row":1,"col":"A"},    NR_SCH01    B03      B      standard    2         A
        {"seat_id":"A02","row":1,"col":"B"},    ...
        {"seat_id":"A03","row":2,"col":"A"}
      ]                          Before: 3 nested loops in application code to find any seat
    },                           After:  SELECT ... FROM national_rail_seats WHERE ...
    {
      "coach": "B",
      "fare_class": "standard",
      ...
    }
  ]
}
```

```python
# skeleton/seed_postgres.py — conceptual flatten
for layout in seat_layouts:
    for coach in layout["coaches"]:
        for seat in coach["seats"]:
            rows.append((
                layout["schedule_id"],
                seat["seat_id"],
                coach["coach"],
                coach["fare_class"],
                seat["row"],
                seat["column"],
            ))

insert_many(cur, "national_rail_seats",
            ["schedule_id", "seat_id", "coach", "fare_class", "seat_row", "seat_column"],
            rows)
```

Now seat availability is a single-table query with a `LEFT JOIN` to filter out booked seats — no JSON parsing required.

---

### 8. Polymorphic Associations

A **polymorphic association** is when one table's rows can belong to rows in any one of several other tables. In TransitFlow, a payment can be for a national rail booking *or* a metro trip.

#### 8.1 The Problem

A payment must belong to exactly one transaction, but that transaction can live in either of two tables:

```
national_rail_bookings          metro_trips
┌──────────────────┐            ┌──────────────┐
│ BK-X7K2MQ       │            │ MT-0041      │
│ user: RU01       │            │ user: RU02   │
│ amount: $8.50    │            │ amount: $2.00│
└──────────────────┘            └──────────────┘
         ▲                               ▲
         │  which table does this        │
         │  payment row belong to? ──────┘
         │
┌────────┴────────────────────────────┐
│            payments                 │
│  PM-001  │ BK-X7K2MQ  │  $8.50    │  ← rail booking
│  PM-002  │ MT-0041    │  $2.00    │  ← metro trip
└──────────────────────────────────────┘
```

A strict relational FK cannot say "this column must match a row in Table A *or* Table B." You must choose an approach.

#### 8.2 How TransitFlow Does It: String-Prefix Discriminator

The application uses the ID prefix to determine which table to query:

```python
# skeleton/agent.py (conceptual)
if transaction_id.startswith("BK"):
    booking = query_national_rail_booking(transaction_id)
elif transaction_id.startswith("MT"):
    trip = query_metro_trip(transaction_id)
```

```sql
-- No FK constraint — the database cannot enforce it
payments (
    payment_id      VARCHAR(15) PRIMARY KEY,
    transaction_ref VARCHAR(15) NOT NULL,  -- "BK-X7K2MQ" or "MT-0041"
    ...
);

CREATE INDEX ON payments (transaction_ref);  -- fast lookup in both directions
```

**Pros:** Simple. No schema change needed when you add a third transaction type.
**Cons:** No referential integrity at the DB level. Orphaned payments are possible. Requires application-level discipline.

#### 8.3 Alternative: Separate FK Columns

```sql
payments (
    payment_id      VARCHAR(15) PRIMARY KEY,
    booking_id      VARCHAR(15) REFERENCES national_rail_bookings(booking_id),
    trip_id         VARCHAR(15) REFERENCES metro_trips(trip_id),
    CHECK (
        (booking_id IS NOT NULL AND trip_id IS NULL) OR
        (booking_id IS NULL AND trip_id IS NOT NULL)
    )
);
```

**Pros:** Full referential integrity; the database enforces exactly one parent.
**Cons:** Every new transaction type adds a column. The `CHECK` constraint is verbose.

#### 8.4 Alternative: Abstract Base Table

```sql
CREATE TABLE transactions (
    transaction_id  VARCHAR(15) PRIMARY KEY,
    type            VARCHAR(20) NOT NULL  -- 'national_rail', 'metro'
);

-- Both tables use the shared primary key
CREATE TABLE national_rail_bookings (
    booking_id  VARCHAR(15) PRIMARY KEY REFERENCES transactions(transaction_id),
    ...
);

CREATE TABLE metro_trips (
    trip_id  VARCHAR(15) PRIMARY KEY REFERENCES transactions(transaction_id),
    ...
);

-- Payments always reference the abstract table
CREATE TABLE payments (
    payment_id      VARCHAR(15) PRIMARY KEY,
    transaction_id  VARCHAR(15) REFERENCES transactions(transaction_id),
    ...
);
```

**Pros:** Referential integrity preserved; clean abstraction.
**Cons:** Extra table and join for every lookup; more complex to insert (must insert to `transactions` first).

#### 8.5 Choosing an Approach

```
APPROACH 1: String-prefix discriminator (TransitFlow)
─────────────────────────────────────────────────────
national_rail_bookings    metro_trips          payments
┌──────────────┐          ┌──────────┐         ┌──────────────────────────────┐
│ BK-X7K2MQ   │          │ MT-0041  │         │ PM-001 │ BK-X7K2MQ │  8.50   │
└──────────────┘          └──────────┘         │ PM-002 │ MT-0041   │  2.00   │
       no FK ──────────────────────────────────► └──────────────────────────────┘
  app code reads prefix to know which table to look up
  ✗ no DB-level integrity   ✓ simple schema

APPROACH 2: Separate nullable FK columns
──────────────────────────────────────────────────────────────────────────
payments
┌──────────┬────────────┬─────────┬────────────┐
│ PM-001   │ BK-X7K2MQ │  NULL   │  8.50      │  ← booking_id set, trip_id NULL
│ PM-002   │   NULL    │ MT-0041 │  2.00      │  ← trip_id set, booking_id NULL
└──────────┴────────────┴─────────┴────────────┘
  CHECK constraint enforces: exactly one FK must be non-null
  ✓ full FK integrity   ✗ each new type adds a column

APPROACH 3: Abstract base table (transactions)
──────────────────────────────────────────────────────────────────────────
transactions (abstract)      national_rail_bookings    metro_trips
┌─────────────┬────────┐     ┌───────────────┐         ┌──────────┐
│ BK-X7K2MQ  │ rail   │◄────│ BK-X7K2MQ    │         │          │
│ MT-0041    │ metro  │◄────────────────────────────────│ MT-0041  │
└─────────────┴────────┘     └───────────────┘         └──────────┘
       ▲
       │  payments.transaction_id → transactions.transaction_id
┌──────┴──────────────┐
│ PM-001 │ BK-X7K2MQ │
│ PM-002 │ MT-0041   │
└────────────────────-┘
  ✓ full FK integrity   ✓ extensible   ✗ extra table + insert on every transaction
```

| Approach | Integrity | Complexity | Best for |
|---|---|---|---|
| String prefix | None at DB | Low | Teaching projects, small teams with discipline |
| Separate FK columns | Full | Medium | Few types, stable schema |
| Abstract base table | Full | Higher | Many types, or types added over time |

---

## Part 3 — Security

---

### 9. Storing Passwords as Hashes

TransitFlow includes this note in its authentication code:

```python
# databases/relational/queries.py, line 271–273
"""
NOTE: passwords are stored as plain text here intentionally for teaching
purposes. In production, replace with a salted hash (e.g. bcrypt).
"""
```

This section explains why that note is critical, and what you must do instead.

#### 9.1 Why Plain Text Is Dangerous

If your database is ever compromised — through SQL injection, a disgruntled employee, a misconfigured backup — every user's password is immediately exposed. Since most people reuse passwords, attackers can then access their email, bank, and other services.

TransitFlow's user file shows what a plain-text database looks like to an attacker:

```json
{
  "user_id": "RU01",
  "email": "alice.tan@email.com",
  "password": "Alice@123"
}
```

One database dump and every user is compromised instantly.

#### 9.2 How Password Hashing Works

A **cryptographic hash function** transforms a password into a fixed-length string in a way that is:
- **Deterministic**: the same input always produces the same output
- **One-way**: you cannot derive the original password from the hash
- **Avalanche**: a tiny change in input produces a completely different hash

```
REGISTRATION                                 DATABASE ROW
─────────────────────────────────────        ────────────────────────────────────────
User types: "Alice@123"
     │
     ▼
bcrypt.gensalt()  →  random salt             ┌──────────┬───────────────────────────────┐
     │                   │                   │ user_id  │ password                      │
     ▼                   ▼                   ├──────────┼───────────────────────────────┤
 "Alice@123"  +  "$2b$12$X9v..." ──hash──►  │ RU01     │ $2b$12$X9v...52chars...       │
                                             └──────────┴───────────────────────────────┘

LOGIN VERIFICATION
─────────────────────────────────────────────────────────
User types: "Alice@123"
     │
     ▼
bcrypt.checkpw("Alice@123", stored_hash)
     │  extracts salt from the stored hash, re-hashes, compares
     ▼
 True  → grant access
 False → deny (wrong password)

TWO USERS, SAME PASSWORD — still different hashes (salt is random each time)
─────────────────────────────────────────────────────────
User RU01 password "Alice@123" → $2b$12$X9v...aBcDeF...
User RU07 password "Alice@123" → $2b$12$Kqm...7GhIjK...
                                          ↑
                                   different salt = different hash
                                   attacker cannot tell two users share the same password
```

**Salting** adds a random string to the password before hashing. This prevents two users with the same password from having the same hash, and makes precomputed "rainbow table" attacks useless.

#### 9.3 bcrypt in Python

```python
import bcrypt

# Registration: hash the password
def register_user(email: str, password: str, ...):
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    # Store hashed.decode("utf-8") in the database — it includes the salt

# Login: verify the password
def login_user(email: str, password: str):
    row = db_get_user_by_email(email)
    if row and bcrypt.checkpw(password.encode("utf-8"), row["password"].encode("utf-8")):
        return row   # login success
    return None
```

The `rounds` parameter (work factor) controls how slow the hash is to compute. Higher = more secure (harder to brute-force) but also slower at login. `12` is a reasonable default in 2025; increase it as hardware improves.

Column definition:
```sql
-- Bcrypt output is always 60 characters
password  VARCHAR(60) NOT NULL   -- store the full bcrypt hash
```

#### 9.4 argon2id — The Modern Standard

`argon2id` won the Password Hashing Competition in 2015 and is the current recommendation. It is memory-hard (requires a lot of RAM to compute), which defeats GPU-based brute-force attacks better than bcrypt.

```python
from argon2 import PasswordHasher

ph = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=2)

# Hash
hashed = ph.hash(password)

# Verify
try:
    ph.verify(hashed, password)   # raises exception on failure
    return True
except:
    return False
```

#### 9.5 Secret Questions — A Weak Pattern

TransitFlow's password recovery uses a secret question and answer:

```json
{
  "secret_question": "What was the name of your first pet?",
  "secret_answer":   "Biscuit"
}
```

Problems:
- Answers are guessable or discoverable via social media
- Users forget their answers over time
- Answers are often stored plainly (and equally sensitive to exposure)

Production alternatives:
- **Email magic link**: generate a one-time token, email it, expire it in 15 minutes
- **TOTP** (Time-based One-Time Password): `Google Authenticator`, `Authy`
- **Phone SMS OTP**: convenient but susceptible to SIM-swapping attacks

If you must keep a secret answer, hash it the same way as a password.

#### 9.6 Migration Path: Plain Text → Hashed

You cannot batch-hash all existing passwords — you do not know the original values (that is the point). The safe approach:

1. Add a `password_hash` column alongside the existing `password` column
2. On each successful login, hash the supplied password and write it to `password_hash`, then clear `password`
3. After a migration window (or a forced reset email), remove the `password` column

```sql
ALTER TABLE users ADD COLUMN password_hash VARCHAR(128);
-- After migration is complete:
ALTER TABLE users DROP COLUMN password;
```

---

### 10. Prepared Statements & SQL Injection

#### 10.1 The Attack

SQL injection occurs when user-supplied input is concatenated directly into a SQL string:

```python
# DANGEROUS — never do this
email = input("Enter email: ")
sql = f"SELECT * FROM users WHERE email = '{email}'"
cur.execute(sql)
```

An attacker enters the email: `alice@example.com' OR '1'='1`

```
VULNERABLE CODE PATH
──────────────────────────────────────────────────────────────────────────
Python code:  f"SELECT * FROM users WHERE email = '{email}'"

User input:   alice@example.com' OR '1'='1

Final SQL:    SELECT * FROM users WHERE email = 'alice@example.com' OR '1'='1'
                                                                    ──────────
                                                          always TRUE — returns every row
Result:       entire users table exposed to attacker

DESTRUCTIVE VARIANT
User input:   x'; DROP TABLE users; --

Final SQL:    SELECT * FROM users WHERE email = 'x'; DROP TABLE users; --'
                                                     ─────────────────
                                                     second statement executes!
Result:       users table destroyed
```

The resulting SQL becomes:
```sql
SELECT * FROM users WHERE email = 'alice@example.com' OR '1'='1'
```

This returns every user in the table. More destructive payloads can `DROP TABLE` or exfiltrate data from other tables.

#### 10.2 The Fix: Parameterised Queries

Pass values as parameters — the database driver handles quoting and escaping:

```python
# SAFE — parameters are sent separately from the query
cur.execute(
    "SELECT * FROM users WHERE email = %s AND is_active = TRUE",
    (email,)   # tuple of parameters
)
```

```
UNSAFE: SQL + data mixed together in one string
─────────────────────────────────────────────────────────────────────
Python ──► f"SELECT ... WHERE email = '{email}'"  ──────────────► DB
            └─────── one string, data can break out ──────────────┘

SAFE: SQL and data sent as separate channels
─────────────────────────────────────────────────────────────────────
Python ──► SQL template  "SELECT ... WHERE email = %s"  ──────► DB parser
       ──► parameters    ("alice@example.com' OR '1'='1",)  ──► DB binder
                          └──── treated as a literal string, never executed ────┘
```

The SQL string and the data travel separately. The database server parses the SQL, then substitutes the parameter value safely — no injection possible.

**This is what `psycopg2` does whenever you use `%s` placeholders.** Never use f-strings or `+` concatenation to build SQL.

From TransitFlow's working query functions:
```python
# databases/relational/queries.py — the vector search function
cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
#                └──────────────── parameters, safely bound ──────────────────┘
```

#### 10.3 What a Prepared Statement Is

A prepared statement separates *parsing* from *execution*. The SQL is compiled once and stored in the database session; parameters are supplied separately on each execution.

```python
# Explicit prepared statement (psycopg2)
cur.execute("PREPARE find_user AS SELECT * FROM users WHERE email = $1")
cur.execute("EXECUTE find_user (%s)", (email,))
```

In practice, `psycopg2` automatically uses prepared statements internally when you use `%s` — you rarely need to write `PREPARE` explicitly. The benefit is clearest in loops where the same query runs thousands of times:

```python
# The SQL is parsed once; only the parameter value changes each iteration
for email in batch_emails:
    cur.execute("SELECT user_id FROM users WHERE email = %s", (email,))
```

#### 10.4 Named Parameters in Neo4j Cypher

Cypher uses `$param` notation:

```python
# databases/graph/queries.py — always use $param, never f-strings
result = session.run(
    """
    MATCH (s:MetroStation {station_id: $station_id})
    RETURN s.name AS name, s.lines AS lines
    """,
    station_id=station_id    # keyword argument maps to $station_id
)
```

The principle is identical to SQL: send the query and the data separately.

---

## Part 4 — Advanced Relational

---

### 11. Transactions

A transaction is a sequence of database operations that either all succeed or all fail together. It is the mechanism that turns "insert booking + insert payment" into a single atomic operation.

#### 11.1 ACID Properties

**Atomicity** — All steps succeed, or none of them take effect. If the payment insert fails, the booking insert is rolled back too.

**Consistency** — The database moves from one valid state to another. Constraints are never violated mid-transaction.

**Isolation** — Concurrent transactions do not see each other's intermediate state. A second user trying to book the same seat will not see a half-completed booking.

**Durability** — Once committed, changes survive crashes. The database writes to disk before confirming success.

#### 11.2 BEGIN / COMMIT / ROLLBACK

```sql
BEGIN;

  INSERT INTO national_rail_bookings (booking_id, user_id, ...) VALUES (...);
  INSERT INTO payments (payment_id, transaction_ref, ...) VALUES (...);

COMMIT;
```

If anything goes wrong between `BEGIN` and `COMMIT`, issue:
```sql
ROLLBACK;  -- undo everything since BEGIN
```

In Python with psycopg2:
```python
conn = psycopg2.connect(PG_DSN)
conn.autocommit = False   # explicit transaction control

try:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO national_rail_bookings ...", booking_values)
        cur.execute("INSERT INTO payments ...", payment_values)
    conn.commit()
    return True, booking_dict
except Exception as e:
    conn.rollback()
    return False, str(e)
finally:
    conn.close()
```

#### 11.3 autocommit: When to Use It

TransitFlow's `_connect()` function uses `autocommit = True`:

```python
def _connect():
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = True
    return conn
```

With `autocommit=True`, every statement is immediately committed. This is fine for **read-only queries** — there is nothing to roll back. For **write operations** like `execute_booking()`, you must disable autocommit and handle commit/rollback explicitly.

#### 11.4 The Double-Booking Race Condition

Without proper isolation, two users can simultaneously book the last available seat:

```
Time  User A                          User B
────  ──────────────────────          ──────────────────────
T1    SELECT seat "A01" → available
T2                                    SELECT seat "A01" → available
T3    INSERT booking for "A01"
T4                                    INSERT booking for "A01"
T5    Both succeed — seat double-booked!
```

The fix is `SELECT ... FOR UPDATE`, which locks the seat row until the transaction commits:

```sql
-- Inside a transaction
SELECT seat_id FROM national_rail_seats
WHERE schedule_id = 'NR_SCH01'
  AND seat_id = 'A01'
  AND seat_id NOT IN (
      SELECT seat_id FROM national_rail_bookings
      WHERE schedule_id = 'NR_SCH01' AND travel_date = '2026-06-01'
  )
FOR UPDATE;
-- Row is now locked. User B's identical query will wait until User A commits or rolls back.
```

#### 11.5 The Cancellation + Refund Flow

The cancellation process in TransitFlow requires multiple steps that must succeed or fail together:

```python
def execute_cancellation(booking_id: str, user_id: str):
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 1. Fetch booking and verify ownership
            cur.execute(
                "SELECT * FROM national_rail_bookings WHERE booking_id = %s FOR UPDATE",
                (booking_id,)
            )
            booking = cur.fetchone()
            if not booking or booking["user_id"] != user_id:
                conn.rollback()
                return False, "Booking not found or access denied"

            # 2. Calculate refund based on service type and cancellation window
            refund_amount = _calculate_refund(booking)

            # 3. Update booking status
            cur.execute(
                "UPDATE national_rail_bookings SET status = 'cancelled' WHERE booking_id = %s",
                (booking_id,)
            )

            # 4. Insert refund payment record
            cur.execute(
                "INSERT INTO payments (payment_id, transaction_ref, amount_usd, status) "
                "VALUES (%s, %s, %s, 'refunded')",
                (_gen_payment_id(), booking_id, refund_amount)
            )

        conn.commit()
        return True, {"refund_amount_usd": refund_amount}
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
```

If step 4 fails (e.g., `payment_id` collision), the `rollback()` undoes steps 3 and 4 — the booking remains active. The user can try again.

---

### 12. Views

A view is a named, saved `SELECT` query. To a user, it looks like a table — you can `SELECT` from it — but its data is computed on demand from the underlying tables.

#### 12.1 Why Use Views

- **Simplify complex queries**: wrap a long JOIN-heavy query behind a simple name
- **Enforce row-level security**: show users only their own rows
- **Hide schema complexity**: abstract away the `is_active` filter so queries never forget it
- **Stable API**: rename tables without changing application code if the view name stays the same

#### 12.2 Creating a View

```sql
-- A view that only surfaces active users
CREATE VIEW active_users AS
SELECT user_id, email, full_name, date_of_birth, registered_at
FROM users
WHERE is_active = TRUE;

-- Application code queries the view, not the table
SELECT * FROM active_users WHERE user_id = 'RU01';
```

A view for current confirmed bookings:
```sql
CREATE VIEW confirmed_bookings AS
SELECT
    b.booking_id,
    b.user_id,
    u.full_name,
    b.schedule_id,
    b.origin_station_id,
    b.destination_station_id,
    b.travel_date,
    b.fare_class,
    b.amount_usd
FROM national_rail_bookings b
JOIN users u ON b.user_id = u.user_id
WHERE b.status = 'confirmed';
```

#### 12.3 Materialized Views

A regular view recomputes its query every time you select from it. A **materialized view** stores the result on disk and refreshes on demand:

```sql
CREATE MATERIALIZED VIEW daily_revenue AS
SELECT
    travel_date,
    SUM(amount_usd) AS total_revenue,
    COUNT(*) AS booking_count
FROM national_rail_bookings
WHERE status = 'completed'
GROUP BY travel_date;

-- Refresh manually when needed
REFRESH MATERIALIZED VIEW daily_revenue;
```

Use materialized views for expensive aggregations that do not need real-time freshness — nightly reports, dashboards, analytics summaries.

#### 12.4 Updatable Views

If a view selects from a single table with no aggregation or `DISTINCT`, PostgreSQL allows `INSERT`, `UPDATE`, and `DELETE` through the view:

```sql
-- active_users is updatable because it selects from one table
UPDATE active_users SET full_name = 'Alice Tan-Lee' WHERE user_id = 'RU01';
-- This updates the users table directly
```

Views with JOINs, aggregations, or `DISTINCT` are read-only.

---

### 13. Stored Procedures & Functions

A stored procedure (or function) is SQL logic stored inside the database itself. You define it once, call it by name.

#### 13.1 When to Use Database-Side Logic

**Good reasons:**
- Centralise a calculation used by multiple applications or services
- Enforce a business rule that must be consistent regardless of which application calls it
- Reduce round-trips for complex multi-step operations

**Reasons to be cautious:**
- Database logic is harder to version-control and test than application code
- Tightly couples your business logic to a specific database engine
- Debugging stored procedures is harder than debugging Python

For TransitFlow, fare calculation is a good candidate — it is always the same formula, regardless of how a booking is created.

#### 13.2 CREATE FUNCTION Syntax (PostgreSQL PL/pgSQL)

```sql
CREATE OR REPLACE FUNCTION calculate_national_rail_fare(
    p_schedule_id  VARCHAR,
    p_fare_class   VARCHAR,
    p_stops        INTEGER
) RETURNS DECIMAL(8,2) AS $$
DECLARE
    v_base_fare     DECIMAL(8,2);
    v_per_stop_rate DECIMAL(8,2);
BEGIN
    -- Fetch rates from the fare_classes JSONB column
    SELECT
        (fare_classes->p_fare_class->>'base')::DECIMAL,
        (fare_classes->p_fare_class->>'per_stop')::DECIMAL
    INTO v_base_fare, v_per_stop_rate
    FROM national_rail_schedules
    WHERE schedule_id = p_schedule_id;

    IF v_base_fare IS NULL THEN
        RAISE EXCEPTION 'Schedule or fare class not found: % / %',
                        p_schedule_id, p_fare_class;
    END IF;

    RETURN v_base_fare + (v_per_stop_rate * p_stops);
END;
$$ LANGUAGE plpgsql;
```

Call it like any function:
```sql
SELECT calculate_national_rail_fare('NR_SCH01', 'standard', 4);
-- Returns: 8.50
```

#### 13.3 Anatomy of a PL/pgSQL Function

| Keyword | Purpose |
|---|---|
| `CREATE OR REPLACE FUNCTION` | Define (or redefine) the function |
| `RETURNS type` | The return type |
| `AS $$ ... $$` | Function body delimiters |
| `DECLARE` | Local variable declarations |
| `BEGIN / END` | The executable block |
| `INTO` | Capture query result into variables |
| `RAISE EXCEPTION` | Throw an error |
| `LANGUAGE plpgsql` | The procedural language to use |

#### 13.4 Procedures vs Functions

In PostgreSQL 11+, `CREATE PROCEDURE` allows transaction control (`COMMIT`/`ROLLBACK` inside the body). `CREATE FUNCTION` does not — it runs in the caller's transaction. For the booking flow, a procedure would let you atomically commit sub-steps; for a pure calculation, a function is cleaner.

---

## Part 5 — Graph Databases

---

### 14. Graph Databases & Neo4j

#### 14.1 When Relational Hits Its Limits

The metro network has 20 stations and 30+ links. Finding the shortest path between two stations in SQL requires a recursive Common Table Expression (CTE):

```sql
-- SQL path-finding — works but grows complex quickly
WITH RECURSIVE path AS (
    SELECT station_id AS origin, station_id AS current, 0 AS total_time,
           ARRAY[station_id] AS visited
    FROM metro_stations WHERE station_id = 'MS01'
    UNION ALL
    SELECT p.origin, l.to_station_id, p.total_time + l.travel_time_min,
           p.visited || l.to_station_id
    FROM path p
    JOIN metro_links l ON l.from_station_id = p.current
    WHERE l.to_station_id <> ALL(p.visited)
)
SELECT * FROM path WHERE current = 'MS09'
ORDER BY total_time LIMIT 1;
```

This is hard to write, hard to read, and does not scale to complex queries like "find all paths that avoid a specific station" or "find interchange paths between two networks."

A graph database models exactly this problem natively. Nodes are entities; edges are relationships. Path-finding is a first-class operation.

#### 14.2 TransitFlow's Graph Model

```
METRO NETWORK (city lines M1–M4)
────────────────────────────────────────────────────────────────────────────────
  (MS20:MetroStation)  ──[METRO_LINK line:M1, 2min]──►  (MS05:MetroStation)
   name: Westfield          │                              name: North Gate
   lines: [M1]              │                              lines: [M1]
                            │
                   [METRO_LINK line:M1, 3min]
                            │
                            ▼
                   (MS01:MetroStation)
                    name: Central Square
                    lines: [M1, M2]           ◄── interchange hub
                            │
               ┌────────────┴──────────────────────┐
               │  METRO_LINK M2, 3min              │  METRO_LINK M1, 3min
               ▼                                   ▼
      (MS06:MetroStation)                 (MS02:MetroStation)
       name: West Market                  name: East Gate

CROSS-NETWORK INTERCHANGE (metro ↔ national rail)
────────────────────────────────────────────────────────────────────────────────
(MS01:MetroStation)                         (NR01:NationalRailStation)
 name: Central Square  ──[INTERCHANGE_TO]──► name: Central Station
 lines: [M1, M2]       ◄─[INTERCHANGE_TO]──  lines: [NR1, NR2]
                         (bidirectional)

NATIONAL RAIL NETWORK
────────────────────────────────────────────────────────────────────────────────
(NR01:NationalRailStation) ──[RAIL_LINK line:NR1, 12min]──► (NR02:NationalRailStation)
 name: Central Station                                         name: Parklands
 lines: [NR1, NR2]
```

Properties on **nodes**: `station_id`, `name`, `lines`
Properties on **relationships**: `line` (which service), `travel_time_min` (edge weight for Dijkstra)
Relationships with **no properties**: `[:INTERCHANGE_TO]` — the existence of the edge is the fact.

**Node labels** classify entities: `:MetroStation`, `:NationalRailStation`
**Relationship types** classify connections: `:METRO_LINK`, `:RAIL_LINK`, `:INTERCHANGE_TO`
**Properties** live on both nodes and relationships: `station_id`, `travel_time_min`, `line`

#### 14.3 Why Adjacency Lists in SQL Get Painful

In SQL, you would store the network as:
```sql
CREATE TABLE metro_links (
    from_station_id  VARCHAR(10),
    to_station_id    VARCHAR(10),
    line             VARCHAR(5),
    travel_time_min  INTEGER
);
```

```
SQL: query grows with every additional hop you need to traverse
─────────────────────────────────────────────────────────────────────────────────
1 hop  "what's next to MS01?"
       SELECT to_station_id FROM metro_links WHERE from_station_id = 'MS01'

2 hops "what's reachable in 2 stops?"
       SELECT l2.to_station_id
       FROM metro_links l1
       JOIN metro_links l2 ON l1.to_station_id = l2.from_station_id
       WHERE l1.from_station_id = 'MS01'

N hops "any distance?" → recursive CTE (complex, limited in most engines)
       WITH RECURSIVE reachable AS (...)

"Shortest path avoiding MS03 across metro + rail?" → research project

─────────────────────────────────────────────────────────────────────────────────
Cypher: same answer, regardless of hop count or cross-network complexity
─────────────────────────────────────────────────────────────────────────────────
1 hop  MATCH (s {station_id:"MS01"})-[:METRO_LINK]->(n) RETURN n
2 hops MATCH (s {station_id:"MS01"})-[:METRO_LINK*2]->(n) RETURN n
N hops MATCH (s {station_id:"MS01"})-[:METRO_LINK*]->(n) RETURN n
APOC   CALL apoc.algo.dijkstra(start, end, "METRO_LINK|RAIL_LINK", "travel_time_min")
```

This is fine for one hop. For two hops you need a self-join. For N hops you need recursion. For "shortest path across two networks with interchanges and a station to avoid" — the SQL becomes a research project.

In Neo4j, the same question is expressed in one line (see section 15.4).

#### 14.4 Python Driver

```python
# databases/graph/queries.py
from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

def _driver():
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def example_count_nodes() -> int:
    with _driver() as driver:
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS total")
            return result.single()["total"]
```

Always use the driver as a context manager (`with _driver() as driver`) — it ensures the connection is closed even if an exception occurs.

---

### 15. Cypher Query Language

Cypher is Neo4j's query language. Its syntax is designed to look like the graph it describes — nodes appear as `(parentheses)`, relationships as `-[brackets]->`.

#### 15.1 Reading the Graph: MATCH / WHERE / RETURN

```cypher
-- Find a single station
MATCH (s:MetroStation {station_id: "MS01"})
RETURN s.name AS name, s.lines AS lines

-- Find all direct neighbours of a station
MATCH (s:MetroStation {station_id: "MS01"})-[r:METRO_LINK]->(neighbour)
RETURN neighbour.station_id AS id, neighbour.name AS name, r.travel_time_min AS mins

-- Filter with WHERE
MATCH (s:MetroStation)-[:METRO_LINK]->(n:MetroStation)
WHERE s.station_id = "MS01" AND r.line = "M1"
RETURN n
```

The arrow `->` indicates direction. For undirected traversal (follow links both ways), omit the arrow: `-[:METRO_LINK]-`.

#### 15.2 Writing the Graph: CREATE, MERGE, SET, DELETE

```cypher
-- Create a new station node
CREATE (:MetroStation {
    station_id: "MS21",
    name: "Airport Terminal",
    lines: ["M3"]
})

-- MERGE: create if not exists, match if it does (idempotent)
MERGE (s:MetroStation {station_id: "MS01"})
ON CREATE SET s.name = "Central Square", s.lines = ["M1", "M2"]
ON MATCH SET s.last_seen = timestamp()

-- Create a relationship between two existing nodes
MATCH (a:MetroStation {station_id: "MS01"})
MATCH (b:MetroStation {station_id: "MS05"})
MERGE (a)-[:METRO_LINK {line: "M1", travel_time_min: 3}]->(b)

-- Update a property
MATCH (s:MetroStation {station_id: "MS01"})
SET s.is_closed = true

-- Delete a node and all its relationships
MATCH (s:MetroStation {station_id: "MS21"})
DETACH DELETE s
-- Use DETACH DELETE to remove relationships first; plain DELETE fails if relationships exist
```

#### 15.3 Seeding the Graph

```python
# skeleton/seed_neo4j.py (conceptual)
with driver.session() as session:
    # Clear everything first
    session.run("MATCH (n) DETACH DELETE n")

    # Create metro station nodes
    for station in metro_stations:
        session.run(
            "MERGE (s:MetroStation {station_id: $id}) "
            "SET s.name = $name, s.lines = $lines",
            id=station["station_id"],
            name=station["name"],
            lines=station["lines"]
        )

    # Create metro links from adjacent_stations
    for station in metro_stations:
        for adj in station["adjacent_stations"]:
            session.run(
                "MATCH (a:MetroStation {station_id: $from_id}) "
                "MATCH (b:MetroStation {station_id: $to_id}) "
                "MERGE (a)-[:METRO_LINK {line: $line, travel_time_min: $time}]->(b)",
                from_id=station["station_id"],
                to_id=adj["station_id"],
                line=adj["line"],
                time=adj["travel_time_min"]
            )

    # Create interchange relationships
    for station in metro_stations:
        if station.get("interchange_national_rail_station_id"):
            session.run(
                "MATCH (m:MetroStation {station_id: $metro_id}) "
                "MATCH (r:NationalRailStation {station_id: $rail_id}) "
                "MERGE (m)-[:INTERCHANGE_TO]->(r) "
                "MERGE (r)-[:INTERCHANGE_TO]->(m)",
                metro_id=station["station_id"],
                rail_id=station["interchange_national_rail_station_id"]
            )
```

#### 15.4 Path Patterns

Variable-length path matching — follow up to N hops:

```cypher
-- All stations reachable within 3 hops from MS01
MATCH (start:MetroStation {station_id: "MS01"})-[:METRO_LINK*1..3]->(reached)
RETURN reached.station_id, reached.name

-- Shortest path (unweighted)
MATCH path = shortestPath(
    (start:MetroStation {station_id: "MS01"})-[:METRO_LINK*]->
    (end:MetroStation   {station_id: "MS09"})
)
RETURN path, length(path) AS hops
```

The `*` means "any number of hops." `*1..3` means "between 1 and 3 hops." `*` alone is unbounded — use with care on large graphs.

#### 15.5 Dijkstra's Algorithm via APOC

For weighted shortest path (minimising `travel_time_min`), use the APOC library's Dijkstra implementation:

```cypher
// Find fastest route: metro network
MATCH (start:MetroStation {station_id: $origin})
MATCH (end:MetroStation   {station_id: $destination})
CALL apoc.algo.dijkstra(start, end, "METRO_LINK", "travel_time_min")
YIELD path, weight
RETURN
    [node IN nodes(path) | node.station_id] AS station_ids,
    [node IN nodes(path) | node.name]       AS station_names,
    weight                                   AS total_time_min
```

In Python:
```python
def query_shortest_route(origin_id: str, destination_id: str) -> dict:
    with _driver() as driver:
        with driver.session() as session:
            result = session.run(
                """
                MATCH (start:MetroStation {station_id: $origin})
                MATCH (end:MetroStation   {station_id: $destination})
                CALL apoc.algo.dijkstra(start, end, 'METRO_LINK', 'travel_time_min')
                YIELD path, weight
                RETURN
                    [n IN nodes(path) | n.station_id] AS ids,
                    [n IN nodes(path) | n.name]       AS names,
                    weight AS total_time_min
                """,
                origin=origin_id,
                destination=destination_id
            )
            row = result.single()
            if not row:
                return {"found": False}
            return {
                "found": True,
                "total_time_min": row["total_time_min"],
                "path": [{"id": i, "name": n} for i, n in zip(row["ids"], row["names"])]
            }
```

#### 15.6 Filtering Paths: Avoiding a Closed Station

```cypher
// Alternative routes avoiding NR03 (e.g., station closed for maintenance)
MATCH path = (start:NationalRailStation {station_id: $origin})
             -[:RAIL_LINK*]->
             (end:NationalRailStation   {station_id: $destination})
WHERE NONE(node IN nodes(path) WHERE node.station_id = $avoid)
RETURN path
ORDER BY reduce(t = 0, r IN relationships(path) | t + r.travel_time_min)
LIMIT $max_routes
```

`NONE(... WHERE ...)` is true if no element in the collection satisfies the condition — exactly what you need to exclude a station from the path.

#### 15.7 Delay Ripple Analysis

Find all stations within N hops of a disrupted station:

```cypher
MATCH (disrupted {station_id: $station_id})
MATCH path = (disrupted)-[:METRO_LINK|RAIL_LINK*1..$hops]-(affected)
WHERE affected.station_id <> $station_id
RETURN
    affected.station_id AS id,
    affected.name       AS name,
    min(length(path))   AS hops_away
ORDER BY hops_away
```

This query uses an undirected match (`-[...]- ` without arrows) because delay impact radiates both upstream and downstream.

#### 15.8 Aggregation

```cypher
-- Count direct connections per station (degree centrality)
MATCH (s:MetroStation)-[:METRO_LINK]->(neighbour)
RETURN s.station_id AS station, count(neighbour) AS connections
ORDER BY connections DESC

-- Average travel time on line M1
MATCH ()-[r:METRO_LINK {line: "M1"}]->()
RETURN avg(r.travel_time_min) AS avg_segment_time

-- Sum of travel time along a path
MATCH path = (start:MetroStation {station_id: "MS01"})
             -[:METRO_LINK*]->
             (end:MetroStation   {station_id: "MS09"})
WITH path, reduce(total = 0, r IN relationships(path) | total + r.travel_time_min) AS route_time
RETURN [n IN nodes(path) | n.station_id] AS stops, route_time
ORDER BY route_time LIMIT 1
```

---

## Part 6 — Vector Search

---

### 16. Vector Search with pgvector

#### 16.1 What Embeddings Are

An embedding is a list of numbers (a vector) that captures the *meaning* of a piece of text. Words or sentences with similar meaning end up with similar vectors — numerically close in high-dimensional space.

```
"Can I get a refund?"        → [0.23, -0.41, 0.87, ..., 0.12]   (768 numbers)
"How do I cancel my ticket?" → [0.21, -0.39, 0.85, ..., 0.14]   (768 numbers)
                                 └──────── nearly identical ──────┘  ← close in vector space

"What time does the M1 run?" → [0.91,  0.13, -0.22, ..., 0.77]  ← far away in vector space
```

Visualised in 2D (actual vectors are 768D, but the clustering intuition is the same):

```
         ┌──────────────────────────────────────────────────────────┐
         │                    vector space                          │
         │                                                          │
         │  × "can I get a refund?"         REFUND                 │
         │  × "how do I cancel?"            CLUSTER   × "RF001"    │
         │  × "what is the refund policy?"            × "RF002"    │
         │                                            × "RF003"    │
         │                                                          │
         │                                                          │
         │  × "what time does M1 run?"   SCHEDULE                  │
         │  × "when is the next train?"  CLUSTER                   │
         │                                                          │
         └──────────────────────────────────────────────────────────┘
                                   ▲
               user query "how do I get a refund?"
               embeds near the REFUND CLUSTER
               → database returns RF001, RF002, RF003 documents
               (even though the exact word "refund" may not appear in user's question)
```

You embed the user's question and find the policy documents whose embeddings are closest — that is semantic search, and it finds relevant content even when the exact words do not match.

#### 16.2 Schema

The `policy_documents` table (pre-built; do not modify):

```sql
CREATE EXTENSION IF NOT EXISTS vector;   -- loads pgvector

CREATE TABLE policy_documents (
    id          SERIAL        PRIMARY KEY,
    title       VARCHAR(200)  NOT NULL,
    category    VARCHAR(50)   NOT NULL,   -- 'refund', 'booking', 'conduct'
    content     TEXT          NOT NULL,
    embedding   vector(768),              -- 768-dimensional vector
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ   DEFAULT NOW()
);

-- HNSW index for fast approximate cosine similarity search
CREATE INDEX ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

The `vector(768)` type stores 768 floating-point numbers in a compact binary format. The dimension must match the model that generates the embeddings — 768 for `nomic-embed-text`, 3072 for Gemini's embedding model.

#### 16.3 Inserting an Embedding

```python
# skeleton/seed_vectors.py
def store_policy_document(title, category, content, embedding, source_file=""):
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    # Convert Python list to the "[n1,n2,n3,...]" string pgvector expects
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            return cur.fetchone()[0]
```

#### 16.4 Querying by Similarity

The `<=>` operator computes cosine distance (0 = identical, 2 = opposite). Similarity = 1 − distance.

```python
# databases/relational/queries.py
def query_policy_vector_search(embedding: list[float], top_k: int = 3) -> list[dict]:
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s    -- threshold filter
        ORDER BY embedding <=> %s::vector             -- closest first
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]
```

At query time, the application:
1. Embeds the user's question using the same model used at index time
2. Calls `query_policy_vector_search(embedding)` to find the most relevant policy snippets
3. Passes those snippets to the language model as context (Retrieval-Augmented Generation — RAG)

#### 16.5 Why the HNSW Index Matters

Without an index, finding the nearest vector requires computing the distance to every row — O(n) per query. At 10,000 documents that is manageable; at 1 million it becomes unusable.

HNSW (Hierarchical Navigable Small World) builds a multilayer graph structure over the vectors. Searches traverse this graph in O(log n) steps, finding approximate nearest neighbours with ~95%+ accuracy at a fraction of the cost.

```sql
-- Exact (no index): always correct, slow at scale
SELECT ... ORDER BY embedding <=> $query LIMIT 5;

-- With HNSW index: slightly approximate, fast at any scale
-- PostgreSQL uses the index automatically when one exists
```

`vector_cosine_ops` tells pgvector to use cosine distance. Use `vector_l2_ops` for Euclidean distance or `vector_ip_ops` for inner product (dot product).

---

## Part 7 — Practical Tips

---

### 17. Practical Tips & Pitfalls

#### 17.1 Connection Management

Opening a new database connection for every query is expensive — each connection involves a TCP handshake, authentication, and session setup. For a simple script it is fine; for a web server handling hundreds of requests per second, it is a bottleneck.

**In a script (TransitFlow's approach):** Create one connection per logical operation, close it when done:

```python
def _connect():
    return psycopg2.connect(PG_DSN)

# Each function opens and closes its own connection
with _connect() as conn:
    with conn.cursor() as cur:
        cur.execute(...)
```

**In a web server:** Use a connection pool. The pool keeps N connections open and reuses them:

```python
from psycopg2 import pool

_pool = pool.ThreadedConnectionPool(minconn=2, maxconn=10, dsn=PG_DSN)

def get_conn():
    return _pool.getconn()

def release_conn(conn):
    _pool.putconn(conn)
```

For Neo4j, the `GraphDatabase.driver()` itself maintains an internal connection pool — re-use the same driver instance across your application rather than creating a new one per query.

#### 17.2 Bulk Inserts: `execute_values` + `ON CONFLICT DO NOTHING`

Inserting 1000 rows one at a time costs 1000 round-trips. `execute_values` batches them into a single statement:

```python
from psycopg2.extras import execute_values

def insert_many(cur, table, columns, rows):
    """Bulk insert; silently skip duplicates."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount
```

`ON CONFLICT DO NOTHING` makes the seed script **idempotent** — safe to run multiple times without failing on duplicates. This is essential for development: you can reset the database and re-seed without modifying the script.

For more control over conflict resolution (e.g., update if the row already exists):
```sql
INSERT INTO metro_stations (station_id, name, lines)
VALUES (%s, %s, %s)
ON CONFLICT (station_id) DO UPDATE
    SET name = EXCLUDED.name,
        lines = EXCLUDED.lines;
```

#### 17.3 Diagnosing Slow Queries with `EXPLAIN ANALYZE`

```sql
EXPLAIN ANALYZE
SELECT * FROM national_rail_bookings
WHERE user_id = 'RU01' AND status = 'confirmed';
```

Key output to look for:

| Term | Meaning |
|---|---|
| `Seq Scan` | Full table scan — consider adding an index |
| `Index Scan` | Index used — good |
| `Bitmap Index Scan` | Index used for multiple values — efficient |
| `cost=0.00..8.50` | Estimated cost (lower is better; for comparison, not absolute) |
| `actual time=0.02..0.03` | Real measured time in milliseconds |
| `rows=1` | Rows actually returned |
| `loops=1` | How many times this node was executed |

If `EXPLAIN ANALYZE` shows a `Seq Scan` on a large table and you have a WHERE clause on a column, that column likely needs an index.

#### 17.4 Migration Discipline

A migration is a versioned, ordered script that modifies the database schema. Good migration habits prevent data loss:

**Do:**
- Write every schema change as a new migration file, never edit old ones
- Test migrations on a copy of production data before applying to production
- Write a corresponding rollback (down) migration for every forward (up) migration
- Use `ADD COLUMN` with a default value to avoid locking large tables

**Do not:**
- Run `DROP TABLE` or `DROP COLUMN` without verifying no application code reads from it
- Rename columns in production during peak hours — take a maintenance window
- Put application logic inside migrations (keep them to DDL only)

TransitFlow re-initialises the schema from scratch on each `docker-compose down -v`:
```bash
# Development workflow
docker-compose down -v          # wipe volumes
docker-compose up -d            # recreate; schema.sql runs automatically
python skeleton/seed_postgres.py
```

In production, you would use a migration tool (Flyway, Alembic, Liquibase) that tracks which migrations have been applied and runs only the new ones.

#### 17.5 Seed Scripts: Idempotent by Design

A seed script that fails on re-run forces you to manually clean the database before every test run. Design seeds to be idempotent:

1. Use `ON CONFLICT DO NOTHING` for inserts
2. Use `MERGE` in Neo4j (not `CREATE`)
3. In seed scripts that clear data first, wrap in a transaction so a partial failure leaves the database in a known state:

```python
# skeleton/seed_postgres.py
conn.autocommit = False
try:
    seed_metro_stations(cur)
    seed_national_rail_stations(cur)
    # ... all other seeders
    conn.commit()
except Exception as e:
    conn.rollback()   # partial seed leaves nothing
    raise
```

#### 17.6 Naming Your Indexes and Constraints

PostgreSQL auto-generates names like `national_rail_bookings_pkey` and `national_rail_bookings_user_id_idx`. In most cases, auto-names are fine. When you have multiple constraints on one table and need to reference them in error messages or documentation, explicit names help:

```sql
ALTER TABLE national_rail_bookings
    ADD CONSTRAINT uq_booking_seat
    UNIQUE (schedule_id, seat_id, travel_date);

-- Error messages will say: "violates unique constraint uq_booking_seat"
-- instead of: "violates unique constraint national_rail_bookings_schedule_id_seat_id_travel_date_key"
```

#### 17.7 Quick Reference: Common Mistakes

| Mistake | Better Practice |
|---|---|
| `FLOAT` for money | `DECIMAL(10,2)` |
| `TIMESTAMP` without timezone | `TIMESTAMPTZ` |
| String concatenation in SQL | Parameterised queries (`%s`) |
| Opening a new DB connection per query | Reuse connections or use a pool |
| Plain-text passwords | bcrypt or argon2id |
| `ON DELETE CASCADE` on business records | `ON DELETE RESTRICT` + soft delete |
| Forgetting `ON CONFLICT DO NOTHING` in seed scripts | Always write idempotent seeds |
| No index on FK columns | `CREATE INDEX ON child_table (fk_column)` |
| Storing derived values (e.g., full name from first + last) | Store atomic parts, compute derivations in queries |
| Hard-coding connection strings | Environment variables + `.env` files |

---

*This tutorial is grounded in the TransitFlow codebase. Cross-reference with the source files in `databases/`, `skeleton/`, and `train-mock-data/` as you read.*
