# Work Allocation Report — Group 41

> **Instructions:** Complete this document as a team before or alongside your final submission.
> Submit one copy per team via EEClass. This document is shared with all markers.
> Be specific — vague entries ("we all helped") will prevent individual contribution adjustments from being applied in your favour.

---

## 1. Team Members

| Full Name | Student ID | GitHub Username | Email |
|-----------|-----------|----------------|-------|
| 蔡晟郁 | 113409526 | leotsai940914 | qqq113579@gmail.com |
| 黃謙儒 | | Churrios (repo owner) | |
| 蔣耀德 | | | |

---

## 2. Task Ownership

### Code Repository

| Task | Primary Owner | Supporting Member(s) | Notes |
|------|--------------|---------------------|-------|
| **Task 1** — Relational schema design (`schema.sql`) | 蔡晟郁 | — | Includes FK ON DELETE clauses, PK design comments, soft delete strategy, HNSW index fix, junction tables for stops (3NF refactor in PR #34) |
| **Task 2a** — Core availability & fare queries (`query_national_rail_availability`, `query_metro_schedules`, `query_national_rail_fare`, `query_metro_fare`) | 蔡晟郁 | — | Includes junction table migration of array-based stop queries |
| **Task 2b** — Seat & user queries (`query_available_seats`, `query_user_profile`, `query_user_bookings`, `query_payment_info`) | 蔡晟郁 | — | `query_user_profile` patched to include `year_of_birth` |
| **Task 2c** — Write operations (`execute_booking`, `execute_cancellation`) | 蔡晟郁 | — | Seat availability validation added to `execute_booking`; refund key corrected in `execute_cancellation` |
| **Task 2d** — Authentication queries (`login_user`, `register_user`, `get_user_secret_question`, `verify_secret_answer`, `update_password`) | 蔡晟郁 | — | `login_user` patched to return `first_name`/`surname` split required by `ui.py` |
| **Task 3** — PostgreSQL seeding (`seed_postgres.py`) | 黃謙儒 | 蔡晟郁 | 蔡 fixed two bugs post-sync: `seed_seat_layouts` reading `fare_class` from wrong JSON level; `seed_metro_travels` failing on null `stops_travelled` |
| **Task 4** — Neo4j graph design & seeding (`seed_neo4j.py`, `seed.cypher`) | 黃謙儒 | — | Includes node label redesign (MetroStation/NationalRailStation), relationship type redesign (METRO_LINK/RAIL_LINK/INTERCHANGE_TO), fare attributes on edges |
| **Task 5** — Neo4j query functions (`graph/queries.py`) | 黃謙儒 | — | Includes C3 duplicate-routes fix (RETURN DISTINCT), C4 interchange-path timeout fix (shortestPath), C5 delay-ripple fix (min(length(path))), C6 origin-envelope return shape, per-leg `line`/`travel_time_min` in alternative routes (PR #59) |
| **Task 6** — Delay Event Logging (optional extension) | 蔡晟郁, 黃謙儒 | 蔣耀德 | 蔡晟郁: `delay_events` table + `log_delay_event`/`get_active_delays`/`resolve_delay` queries + seed data (PR #49) + per-file `# TASK 6 EXTENSION:` markers (PR #58). 黃謙儒: wired `report_delay`/`get_active_delays` tools into `agent.py` + made `seed_delay_events` idempotent (PR #55) + severity normalisation guard for LLM-supplied values (PR #59). 蔣耀德: `TASK6.md` + Design Document Section 7 (PR #56) |

### Design Document

| Section | Primary Author | Supporting Member(s) | Notes |
|---------|--------------|---------------------|-------|
| Section 1 — ER Diagram | 蔡晟郁 | — | |
| Section 2 — Normalisation Justification | 蔡晟郁 | — | |
| Section 3 — Graph Database Design Rationale | 黃謙儒 | — | |
| Section 4 — Vector / RAG Design | 蔣耀德 | — | |
| Section 5 — AI Tool Usage Evidence | 蔡晟郁 | 黃謙儒, 蔣耀德 | All three contributed examples drawn from actual development events |
| Section 6 — Reflection & Trade-offs | 蔡晟郁 | 黃謙儒, 蔣耀德 | All three contributed |
| Section 7 — Optional Extension (Delay Event Logging) | 蔣耀德 | 黃謙儒 | Documents the Task 6 delay-event extension (motivation, schema snippet, example queries) — PR #56. §7.4 testing evidence (chatbot screenshots with debug panel) contributed by 黃謙儒 |

---

## 3. Estimated Contribution Percentages

| Member | Estimated % | Brief justification |
|--------|-----------|---------------------|
| 蔡晟郁 | 33% | Task 1 relational schema, all Task 2 query functions, Design Document Sec 1/2/5/6 |
| 黃謙儒 | 33% | Task 3 PG seeding (junction tables), Task 4 Neo4j graph design & seeding, Task 5 all graph query functions, Design Document Sec 3 |
| 蔣耀德 | 33% | Vector/RAG pipeline (seed_vectors, rag.py, reranker.py), agent.py integration, Design Document Sec 4 |
| **Total** | **99%** | |

---

## 4. Mid-Project Changes

| Change | Original plan | Revised plan | Reason |
|--------|--------------|-------------|--------|
| `stops_in_order` storage | VARCHAR[] array column in schedule tables | Junction tables `metro_schedule_stops` / `national_rail_schedule_stops` | Grading guide explicitly requires junction table for 3NF compliance; refactored in PR #34 |
| Neo4j node/relationship labels | Generic `Station` node, `CONNECTS_TO` relationship | `MetroStation` / `NationalRailStation` nodes; `METRO_LINK` / `RAIL_LINK` / `INTERCHANGE_TO` relationships | Required for correct type-based traversal in Cypher queries |
| C4 interchange path query | `*1..20` variable-length traversal | `shortestPath(*1..10)` | Original caused >60s timeout; BFS-based shortestPath resolves in <1s |

---

## 5. Team Declaration

We confirm that this work allocation accurately reflects how responsibilities were divided within our team.

| Name | Signature / Typed name | Date |
|------|----------------------|------|
| 蔡晟郁 | 蔡晟郁 | 2026-06-06 |
| 黃謙儒 | | |
| 蔣耀德 | | |
