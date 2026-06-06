# Work Allocation Report — Group 41

> **Instructions:** Complete this document as a team before or alongside your final submission.
> Submit one copy per team via EEClass. This document is shared with all markers.
> Be specific — vague entries ("we all helped") will prevent individual contribution adjustments from being applied in your favour.

---

## 1. Team Members

| Full Name | Student ID | GitHub Username | Email |
|-----------|-----------|----------------|-------|
| 蔡晟郁 | | | |
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
| **Task 5** — Neo4j query functions (`graph/queries.py`) | 黃謙儒 | — | Includes C3 duplicate-routes fix (RETURN DISTINCT), C4 interchange-path timeout fix (shortestPath), C5 delay-ripple fix (min(length(path))) |
| **Task 6** *(if attempted)* — Optional extension | — | — | Not attempted |

### Design Document

| Section | Primary Author | Supporting Member(s) | Notes |
|---------|--------------|---------------------|-------|
| Section 1 — ER Diagram | 蔡晟郁 | — | |
| Section 2 — Normalisation Justification | 蔡晟郁 | — | |
| Section 3 — Graph Database Design Rationale | 黃謙儒 | — | |
| Section 4 — Vector / RAG Design | 蔣耀德 | — | |
| Section 5 — AI Tool Usage Evidence | 蔡晟郁 | 黃謙儒, 蔣耀德 | All three contributed examples drawn from actual development events |
| Section 6 — Reflection & Trade-offs | 蔡晟郁 | 黃謙儒, 蔣耀德 | All three contributed |
| Section 7 — Optional Extension *(if applicable)* | — | — | Not applicable |

---

## 3. Estimated Contribution Percentages

| Member | Estimated % | Brief justification |
|--------|-----------|---------------------|
| 蔡晟郁 | 40% | Full relational schema (Task 1) + all 15 relational query functions (Task 2) + schema/query bug fixes + Design Document Sec 1, 2, 5, 6 |
| 黃謙儒 | 35% | Full Neo4j graph design + seeding (Task 4) + all 6 graph query functions including 3 bug fixes (Task 5) + PostgreSQL seeding lead (Task 3) |
| 蔣耀德 | 25% | Full RAG/vector pipeline (`rag.py`, `reranker.py`, `llm_provider.py`, `seed_vectors.py`) + agent.py LLM pipeline integration + Design Document Sec 4 |
| **Total** | **100%** | |

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
