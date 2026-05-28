# IM2002 — Student Guide: Static Code Evaluation · /100

This guide explains how your submitted code files will be evaluated for static correctness.
TAs read your code directly — no running required for this component. Runtime correctness
is assessed separately during live testing (see `STUDENT_GUIDE_LIVE.md`).

---

## Mark Summary

| Task | Max |
|------|-----|
| Task 1 — Relational Schema Design | 40 |
| Task 2 — PostgreSQL Query Functions | 30 |
| Task 3 — Data Seeding (static check) | 10 |
| Task 4 — Neo4j Graph Design | 8 |
| Task 5 — Neo4j Query Functions | 10 |
| Code Quality | 2 |
| **Total** | **100** |
| Task 6 Bonus (optional) | +15 |

---

## Task 1 — Relational Schema Design · `databases/relational/schema.sql` · /40

| Criterion | What earns full marks |
|-----------|-----------------------|
| **Table completeness** — all required tables present | Every table needed to model the system's entities and relationships is present |
| **Primary & foreign key correctness** — every table has a PK; FKs link correctly | Every table has a clearly defined PK; every FK references a valid column in the parent table |
| **Data types** — NUMERIC/DECIMAL for fares, TIMESTAMPTZ for datetimes, BOOLEAN for flags | Correct types used consistently; e.g. no `TEXT` for numeric fare values |
| **Password storage** — hashed with bcrypt / argon2 / scrypt / PBKDF2 | A strong adaptive hashing algorithm is used; plain-text or weak hashing fails the project. |
| **Normalisation** — schedule stops in a separate junction table (not an array column) | Stop sequences live in their own table with a stop_order column |
| **PK design decision** — UUID vs SERIAL chosen and justified in a comment | A comment near the PK column explains *why* that type was chosen |
| **Delete strategy** — soft or hard delete applied consistently; strategy commented | One strategy used throughout; a comment explains the choice |
| **FK cascade behaviour** — ON DELETE CASCADE / RESTRICT / SET NULL specified | Each FK explicitly states cascade behaviour |
| **Task 1 Total** | |

> Do not implement the `policy_documents` table or its HNSW index — these are provided as scaffold.

**Password hashing scoring:** plain-text = 0 · MD5/SHA = 0 · bcrypt/argon2/scrypt/PBKDF2 = 5 if correctly implemented.

> **Tip:** Plain-text passwords score 0 regardless of other schema quality. Use bcrypt, argon2, scrypt, or PBKDF2, and make sure `register_user()` actually *calls* the hash function — importing it without calling it also scores 0.

---

## Task 2 — PostgreSQL Query Functions · `databases/relational/queries.py` · /30

A function scores **0** if it still raises `NotImplementedError` or contains only `pass`.
Partial SQL that attempts the correct logic earns partial credit.

Do not implement `auto_select_adjacent_seats`, `query_policy_vector_search`,
`store_policy_document`, or `example_query` — these are scaffold.

**Scoring guide per function:**
- Full marks: correct SQL, correct return type and shape, handles edge cases
- Half marks: SQL present but missing a key join, filter, or return field
- 0: `raise NotImplementedError`, `pass`, or clearly wrong logic

### Core availability & fare queries — /14

| Function | What earns full marks |
|----------|-----------------------|
| `query_national_rail_availability(origin_id, destination_id, travel_date)` | Returns a list of schedules with available seat counts; both stations on the route; filtered by date |
| `query_metro_schedules(origin_id, destination_id)` | Returns metro lines serving both stations in correct stop order |
| `query_national_rail_fare(schedule_id, fare_class, stops_travelled)` | Returns dict with `base_fare_usd`, `per_stop_rate_usd`, `total_fare_usd`; arithmetic correct |
| `query_metro_fare(schedule_id, stops_travelled)` | Same dict structure; arithmetic correct |

### Seat & user queries — /9

| Function | What earns full marks |
|----------|-----------------------|
| `query_available_seats(schedule_id, travel_date, fare_class)` | Excludes already-booked seats; filtered by fare class; correct return type |
| `query_user_profile(user_email)` | Returns a single user dict or `None`; never raises an exception for unknown email |
| `query_user_bookings(user_email)` | Returns `{"national_rail": [...], "metro": [...]}` — both keys always present |
| `query_payment_info(booking_id)` | Returns payment record dict or `None` for unknown booking ID |

### Write operations — /5

| Function | What earns full marks |
|----------|-----------------------|
| `execute_booking(...)` | Atomic transaction wrapping both booking insert and payment insert; returns `(True, booking_dict)` on success, `(False, message)` on failure |
| `execute_cancellation(booking_id, user_id)` | Updates booking status; calculates refund per policy; returns `(True, result_dict)` or `(False, msg)` |

> **Tip — `execute_booking` atomicity:** Both the booking insert and the payment insert must be wrapped in a single `conn.commit()`. If only the booking is committed before the payment is inserted, the function scores at most 1.5/3. Think of it as a single all-or-nothing operation.

### Authentication queries — /2

| Function | What earns full marks |
|----------|-----------------------|
| `login_user(email, password)` | Verifies hash using the same algorithm used during registration; returns user dict or `None` |
| `register_user(...)` | Hashes password before storing; rejects duplicate emails gracefully |
| `get_user_secret_question(email)` | Returns question string or `None` |
| `verify_secret_answer(email, answer)` | Case-insensitive comparison; returns bool |
| `update_password(email, new_password)` | Stores new hash; returns bool |

---

## Task 3 — Data Seeding (Static Check) · /10

This section checks whether the seed functions are implemented and whether idempotency
is handled in code. Whether the scripts run without errors is assessed during live testing.

| Criterion | What earns full marks |
|-----------|-----------------------|
| All PostgreSQL seed functions implemented (not `pass`) | All 10 implemented = full marks · 5–9 implemented = 50% · Fewer than 5 = 0 |
| PostgreSQL seeding is idempotent (`ON CONFLICT DO NOTHING` / upsert used) | Every seed function uses conflict handling so re-running does not fail or duplicate data |
| Neo4j seeding implemented (node + relationship statements present) | MERGE or CREATE statements for all 3 relationship types present |
| Neo4j seeding is idempotent (`MERGE` used instead of `CREATE`) | `MERGE` used throughout so re-seeding is safe |
| **Task 3 Total** | |

**PG idempotency scoring:** All seed functions use conflict handling = full marks · Most do = 50% marks · None = 0

> **Tip:** Seeding that is not idempotent loses marks even if the data loads correctly the first time. Use `INSERT ... ON CONFLICT DO NOTHING` for PostgreSQL and `MERGE` instead of `CREATE` for Neo4j. In Cypher, `CREATE` unconditionally inserts a new node or relationship every time it runs — re-seeding produces duplicates. `MERGE` first checks whether a matching node or relationship already exists; if it does, it leaves it alone, making the script safe to run multiple times.

---

## Task 4 — Neo4j Graph Design · `skeleton/seed_neo4j.py` or `databases/graph/seed.cypher` · /8

| Criterion | What earns full marks |
|-----------|-----------------------|
| `MetroStation` and `NationalRailStation` node labels with correct properties | Both node types present with all required properties |
| `METRO_LINK` and `RAIL_LINK` relationships with `travel_time_min` property | Both relationship types present; travel_time_min is a numeric property on each relationship |
| `INTERCHANGE_TO` relationships at cross-network stations (metro↔rail) | Interchange relationships connect the appropriate metro and rail stations |
| **Task 4 Total** | |

---

## Task 5 — Neo4j Query Functions · `databases/graph/queries.py` · /10

A function scores **0** if it still raises `NotImplementedError`.

**Scoring guide:** Full marks = correct Cypher, correct return shape (dict with `path` list + metric).
Half marks = Cypher present but algorithm choice wrong or return shape incorrect.

| Function | What earns full marks |
|----------|-----------------------|
| `query_shortest_route(origin_id, destination_id, network)` | APOC Dijkstra or equivalent; returns dict with `path` (list) and `total_time_min` (numeric) |
| `query_cheapest_route(origin_id, destination_id, network, fare_class)` | Edges weighted by cost; `fare_class` visibly affects edge weights; correct return shape |
| `query_alternative_routes(origin_id, destination_id, avoid_station_id, network, max_routes)` | Returned paths exclude the avoided station; `max_routes` limit respected |
| `query_interchange_path(origin_id, destination_id)` | Cross-network path traverses `INTERCHANGE_TO` edges; result includes nodes from both networks |
| `query_delay_ripple(delayed_station_id, hops)` | Returns all stations within N hops; each result includes `hops_away` count |
| `query_station_connections(station_id)` | Returns direct neighbours with `travel_time_min` per neighbour |
| **Task 5 Total** | |

---

## Code Quality · /2

| Criterion | Max | What earns full marks |
|-----------|-----|-----------------------|
| Non-obvious SQL/Cypher logic has inline comments explaining *why* (not just what) | 1 | At least 3–5 non-trivial functions have comments explaining design choices, not just restating the code |
| No dead stubs: every function either works or is explicitly marked as not attempted | 1 | No silent empty functions; `NotImplementedError` or a clear comment used where not implemented |

---

## Task 6 — Optional Extension Bonus · up to +15

To be eligible, all of the following must be present:

1. The extension touches database code — new schema, queries, or seed data. UI-only changes do not qualify.
2. Every new database operation has detailed inline comments explaining what it does and why.
3. A **Section 7** in your design document covers motivation, schema changes, example queries, and testing evidence.
4. A **`TASK6.md`** file at the repo root lists every file modified or added, with specific function and table names. Each modified file must also have a `# TASK 6 EXTENSION:` comment near the top.

> **Tip:** Without `TASK6.md` and the per-file comment markers, the bonus section will not be graded. TAs use these to locate all extension code unambiguously.

| Criterion | Max | What earns full marks |
|-----------|-----|-----------------------|
| Extension touches database code (new schema, queries, or seed data) — UI-only = 0 | 2 | New tables, relationships, or query functions demonstrably present in the database layer |
| Feature is functional end-to-end (demonstrable via direct DB query or chat UI) | 5 | The feature produces correct database output when tested |
| Quality of database implementation (correct types, transactions, indexes, query design) | 5 | Implementation matches production-quality standards: appropriate types, no missing indexes, correct transaction scope |
| Code comments clearly explain every new database operation | 3 | Every new function and schema object has a comment explaining the *why*, not just the *what* |
| **Task 6 Code Bonus Total** | **+15** | |
