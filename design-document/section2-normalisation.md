# Section 2 — Normalisation Justification

> 負責人：蔡晟郁 | 配分：/20

## 2.1 Normalisation Decisions (3NF)

### Schedule Stops — from VARCHAR[] to Junction Table

The original schema stored schedule stop sequences as a PostgreSQL array column (`stops_in_order VARCHAR(10)[]`). This design violates **Third Normal Form (3NF)**.

In a relation, 3NF requires that every non-key attribute is determined only by the primary key — no transitive dependencies. For a schedule stop, the relevant functional dependency is:

```
(schedule_id, stop_order) → station_id
```

When stops are stored as an array, `stop_order` is not a declared attribute — it is the implicit array index. This means the position of a station within a schedule is encoded in the storage structure rather than in a proper relational attribute. The table has no candidate key that determines stop position, which violates 3NF and prevents row-level updates to individual stops without rewriting the entire array.

The corrected design introduces two junction tables:

```sql
metro_schedule_stops          (schedule_id, stop_order, station_id)
national_rail_schedule_stops  (schedule_id, stop_order, station_id)
```

With composite primary key `(schedule_id, stop_order)`, the functional dependency is properly expressed: `stop_order` is now a first-class attribute, and `station_id` is fully determined by the full primary key with no transitive dependency. This satisfies 3NF.

## 2.2 De-normalisation Trade-offs

### available_seats — Dynamic Derivation over Stored Count

A naive schema might include an `available_seats` counter column on `national_rail_schedules`. We chose not to do this — `available_seats` is derived dynamically in `query_national_rail_availability`:

```sql
(SELECT COUNT(*) FROM seat_layouts sl
 WHERE sl.schedule_id = s.schedule_id) - COUNT(b.booking_id) AS available_seats
```

This is a deliberate trade-off: storing a counter would introduce a transitive dependency (`schedule_id → available_seats`, but `available_seats` is also determined by the current state of `bookings`) and would require a write to `national_rail_schedules` on every booking or cancellation. Maintaining two sources of truth for seat availability risks inconsistency under concurrent writes. By deriving the value at query time, we guarantee consistency at the cost of a subquery on each read — acceptable for a system where booking reads are infrequent.

### policy_documents — Embedding Stored Alongside Content

`policy_documents` stores both the raw text content and its vector embedding in the same table. Strictly, the embedding is a derived value (it is functionally dependent on `content` and the embedding model). A fully normalised design would separate embeddings into a child table. We chose co-location because the embedding is always read together with the content in the RAG pipeline, and splitting the table would add a join on every similarity search with no benefit — the embedding is not updated independently of the content.

## 2.3 Password Hashing

TransitFlow hashes user passwords with **bcrypt** (cost factor 12), implemented via the `bcrypt` Python library.

### Why bcrypt over MD5 or SHA-1

MD5 and SHA-1 are general-purpose cryptographic hash functions designed to be computationally fast. A modern GPU can compute billions of MD5 hashes per second, making brute-force or dictionary attacks against stolen hashes practical. bcrypt is specifically designed for password hashing: it incorporates a **work factor** (cost factor 12 in this implementation) that makes each hash computation deliberately slow (~250 ms on typical hardware). As hardware improves, the cost factor can be increased without changing the algorithm, ensuring future-resistance.

### How Salt Prevents Rainbow Table Attacks

A rainbow table is a precomputed lookup of `hash → password` pairs built for common passwords. If two users have the same password and no salt, their hashes are identical — cracking one cracks both.

bcrypt automatically generates a **128-bit cryptographically random salt** for each password hash. The salt is embedded directly in the 60-character output string:

```
$2b$12$<22-char-salt><31-char-hash>
```

Because every hash has a unique random salt, an attacker cannot precompute a rainbow table — they would need to build a separate table for every possible salt value, which is computationally infeasible. Python's `bcrypt.checkpw()` automatically extracts the salt from the stored hash string, so no separate salt column is needed in `registered_users`.

## 2.4 Database Terminology Reference

The following terms are used precisely in this section:

| Term | Usage in this schema |
|------|---------------------|
| **Functional dependency** | `(schedule_id, stop_order) → station_id` in the junction table |
| **Candidate key** | `(schedule_id, stop_order)` is the only candidate key in `metro_schedule_stops` |
| **Transitive dependency** | Storing `available_seats` as a column would introduce a transitive dependency via `bookings`; dynamic derivation avoids this |
| **3NF** | A relation is in 3NF when every non-key attribute depends on the key, the whole key, and nothing but the key |
| **1NF** | Storing sets (stop arrays) in a single column violates 1NF's requirement for atomic values; the junction table restores atomicity |
