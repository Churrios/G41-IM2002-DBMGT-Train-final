# IM2002 — Student Guide: Live Testing Evaluation · /100

This guide explains how your running application will be evaluated during a live test session.
TAs start your Docker stack, seed the databases, and interact with the Gradio UI. This
component assesses runtime correctness — whether your functions return the right data in the
right shape without crashing.

Static code quality (schema design, function implementation) is assessed separately in
`STUDENT_GUIDE_CODE.md`.

> **Note:** The scenarios described below are illustrative examples. TAs will test additional
> scenarios beyond these. Design your functions to handle the full range of valid inputs
> described in the project specification, not just the examples shown here.

---

## Mark Summary

| Section | Max |
|---------|-----|
| A — Seeding & Setup | 15 |
| B — PostgreSQL Queries | 50 |
| C — Neo4j Routing Queries | 35 |
| **Total** | **100** |
| Task 6 Bonus (optional) | +15 |

---

## Section A — Seeding & Setup · /15

Your seeding scripts must complete without tracebacks and populate all required tables with
plausible data. Fare columns must store numeric values; foreign keys must reference valid rows.

| Criterion | Max | What earns full marks |
|-----------|-----|-----------------------|
| PG seeding: script completes without traceback | 3 | `seed_postgres.py` runs to completion with no Python exception |
| PG seeding: all required tables contain data | 3 | At least `metro_stations`, `national_rail_stations`, `metro_schedules`, `users`, and `seat_layouts` are populated |
| PG data integrity: fare columns are numeric; FK references valid | 2 | Fare values stored as numbers (not strings); every FK points to an existing row |
| Neo4j seeding: script completes without traceback | 3 | `seed_neo4j.py` runs to completion with no exception |
| Neo4j: station nodes and link relationships present | 2 | Station nodes of both types exist; `METRO_LINK` and `RAIL_LINK` relationships are present |
| pgvector: `policy_documents` table populated | 2 | `SELECT COUNT(*) FROM policy_documents` returns a value greater than 0 |
| **Section A Total** | **15** | |

---

## Section B — PostgreSQL Queries · /50

---

### B1 — `query_national_rail_availability` · /10

Return a list of national rail schedules between an origin and destination for a given date.
Each item must include the schedule ID, departure time, and available seat count.

**When services exist on the requested date (5 marks):**
- Returns the schedules that stop at both the origin and destination
- Each result is a dict containing at least `schedule_id` and `available_seats`
- Schedules where the destination appears before the origin in stop order are excluded
- No exception raised

**When no services run on the requested date (5 marks):**
- Returns an empty list `[]` — not `None`, not an exception

---

### B2 — `query_metro_schedules` · /6

Return metro lines that serve both the origin and destination, in correct stop order.

**When both stations share a metro line (4 marks):**
- Returns the lines serving both stations
- Each result includes the line name or ID and the stop sequence
- No exception raised

**When no shared metro line exists (2 marks):**
- Returns an empty list — not an exception

---

### B3 — `query_national_rail_fare` · /6

Return a fare breakdown dict with keys `base_fare_usd`, `per_stop_rate_usd`, and
`total_fare_usd`. The total must equal `base + (per_stop_rate × stops_travelled)`.

**Standard fare class (4 marks):**
- All three keys present; arithmetic is correct
- Values are numeric, not strings
- No exception raised

**Different fare class, e.g. first class (2 marks):**
- `per_stop_rate_usd` differs from the standard class rate
- Total recalculates correctly for the new rate

---

### B4 — `query_metro_fare` · /4

Return the same three-key fare dict as `query_national_rail_fare`, calculated for a metro schedule.

**To earn full marks:**
- All three keys present; `total = base + (rate × stops)`
- Values are numeric, not strings
- No exception raised

---

### B5 — `query_available_seats` · /4

Return a list of seats in the specified fare class that have not already been booked for the
given schedule and date.

**To earn full marks:**
- Returns only seats in the requested fare class
- Each item includes a seat identifier
- Seats from other fare classes are excluded
- No exception raised

---

### B6 — `query_user_profile` · /3

Return a single user dict for a known email, or `None` for an unknown email — never an exception.

**Known email (2 marks):**
- Returns a dict containing at least email, name, and `year_of_birth`

**Unknown email (1 mark):**
- Returns `None` — not an exception

---

### B7 — `query_user_bookings` · /4

Return `{"national_rail": [...], "metro": [...]}`. Both keys must always be present, even when
one or both lists are empty.

**User with at least one booking (3 marks):**
- Correct bookings appear under the right key
- Both `"national_rail"` and `"metro"` keys are always present in the result

**User with no bookings (1 mark):**
- Returns `{"national_rail": [], "metro": []}` — not `None`, not an exception

---

### B8 — `query_payment_info` · /3

Return a payment record dict for a known booking ID, or `None` for an unknown ID.

**Known booking ID (2 marks):**
- Returns a dict containing at least amount, status, and payment method

**Unknown booking ID (1 mark):**
- Returns `None` — not an exception

---

### B9 — `execute_booking` · /5

Create a booking and a payment record atomically, then return `(True, booking_dict)`. If the
seat is already taken, return `(False, message)` — not an exception.

**To earn full marks:**
- Returns `(True, booking_dict)` on success; booking is present in the database
- `booking_dict` includes `booking_id`, `user_id`, `schedule_id`, and `seat_id`
- Both the booking record **and** the payment record exist in the database after the call
- Attempting to book an already-taken seat returns `(False, message)`, not an exception

> **Tip:** Both records must be created in a single atomic operation. If the booking is
> inserted and committed before the payment insert, and the payment then fails, you are
> left with a booking that has no corresponding payment — partial marks apply.

---

### B10 — `execute_cancellation` · /5

Update the booking status to cancelled, calculate a refund per the cancellation policy, and
return `(True, result_dict)`. If the booking is already cancelled, return `(False, message)`.

**To earn full marks:**
- Returns `(True, result_dict)`; booking status changes to cancelled in the database
- `result_dict` includes a `refund_amount`
- Refund calculation matches the cancellation policy window
- Cancelling an already-cancelled booking returns `(False, message)`, not an exception

---

## Section C — Neo4j Routing Queries · /35

---

### C1 — `query_shortest_route` · /8

Return the path with the minimum total travel time between two stations, using Dijkstra or an
equivalent weighted shortest-path algorithm. Result must include a `path` list and a
`total_time_min` value.

**Metro network (4 marks):**
- Returns the optimal path by travel time; path is connected and valid
- Result is a dict with a `"path"` list and a numeric `"total_time_min"`
- No exception raised

**National rail network (4 marks):**
- Returns a valid path for the rail network with the same structure
- Handles an unconnected station pair gracefully — no exception, returns an empty result

---

### C2 — `query_cheapest_route` · /7

Return the path with the lowest estimated cost, where edge weights reflect the fare class.
Result must include a path and a cost value.

**Standard fare class (4 marks):**
- Returns the lowest-cost path; cost metric present in result
- No exception raised

**Different fare class (3 marks):**
- Cost changes with the fare class
- The `fare_class` parameter visibly affects the result

---

### C3 — `query_alternative_routes` · /7

Return a list of routes that avoid a specified station. The `max_routes` parameter must be
respected.

**Station avoidance (4 marks):**
- No returned path passes through the avoided station
- Returns a list of paths (not just one)
- No exception raised

**Route limit (3 marks):**
- `max_routes=1` returns at most 1 route
- The `max_routes` limit is respected

---

### C4 — `query_interchange_path` · /8

Return a cross-network path from a metro origin to a national rail destination (or vice versa),
traversing `INTERCHANGE_TO` edges. The result must include nodes from both networks.

**Cross-network journey (5 marks):**
- An `INTERCHANGE_TO` edge is used; path crosses the metro↔rail boundary
- Result includes nodes from both networks
- No exception raised

**Same-network input (3 marks):**
- Returns a direct path or an appropriate empty result without crashing

---

### C5 — `query_delay_ripple` · /3

Return all stations within N hops of a delayed station. Each result must include a `hops_away`
count.

**To earn full marks:**
- Returns the correct set of stations within the specified hop count
- `hops=0` returns only the delayed station itself — not its neighbours

---

### C6 — `query_station_connections` · /2

Return a list of stations directly connected to the given station, each with a `travel_time_min`
value.

**To earn full marks:**
- Returns the direct neighbours of the given station
- Each neighbour includes `travel_time_min`

---

## Task 6 — Optional Extension Bonus · up to +15

To be eligible for the live bonus, all four of the following must be present:

1. The extension touches database code — new schema, queries, or seed data. UI-only changes do not qualify.
2. Detailed inline comments explain every new database operation.
3. A **Section 7** in your design document covers motivation, schema changes, example queries, and testing evidence.
4. A **`TASK6.md`** file at the repo root lists every file modified or added, with specific function and table names. Each modified file must also have a `# TASK 6 EXTENSION:` comment near the top.

If you attempt the optional extension, ensure `TASK6.md` is complete — the live bonus is only graded if the extension feature is demonstrable in the running application.

| Criterion | Max | What earns full marks |
|-----------|-----|-----------------------|
| Extension feature is demonstrable live in the Gradio UI or via a direct DB query | 6 | The feature produces visible, correct output when triggered during the live session |
| Database correctness — extension data is accurate | 5 | Querying the extension data directly confirms it is correct, not just that it loads without errors |
| Extension integrates cleanly with the existing system (no regressions in B1–C6 tests) | 4 | All original functions continue to pass their scenarios after the extension is added |
| **Task 6 Live Bonus Total** | **+15** | |
