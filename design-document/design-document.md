# TransitFlow — Database Design Document

> IM2002 Final Project | Group 41
> 蔡晟郁 · 黃謙儒 · 蔣耀德

---

# Section 1 — Entity-Relationship Diagram

> 負責人：蔡晟郁

## 1.1 ER Diagram

![ER Diagram](er-diagram.png)

[ER Diagram (PDF)](er-diagram.pdf)

## 1.2 Entity Overview

| Entity | PK | Key FKs | Representative Fields |
|--------|----|---------|-----------------------|
| `registered_users` | `user_id` | — | `email`, `password`, `is_active` |
| `metro_stations` | `station_id` | `interchange_nr_station_id → national_rail_stations` | `name`, `lines`, `zone` |
| `national_rail_stations` | `station_id` | `interchange_metro_station_id → metro_stations` | `name`, `managed_by` |
| `metro_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → metro_stations` | `line`, `frequency_min`, `base_fare_usd` |
| `metro_schedule_stops` | `(schedule_id, stop_order)` | `schedule_id → metro_schedules`, `station_id → metro_stations` | `stop_order` |
| `national_rail_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → national_rail_stations` | `line`, `service_type`, `std_base_fare_usd` |
| `national_rail_schedule_stops` | `(schedule_id, stop_order)` | `schedule_id → national_rail_schedules`, `station_id → national_rail_stations` | `stop_order` |
| `seat_layouts` | `(schedule_id, seat_id)` | `schedule_id → national_rail_schedules` | `coach`, `row`, `column`, `fare_class` |
| `bookings` | `booking_id` | `user_id → registered_users`, `schedule_id → national_rail_schedules` | `travel_date`, `seat_id`, `status` |
| `metro_travel_history` | `trip_id` | `user_id → registered_users`, `schedule_id → metro_schedules` | `travel_date`, `amount_usd`, `status` |
| `payments` | `payment_id` | `booking_id`（無 FK：雙參照 BK.../MT...） | `amount_usd`, `method`, `status` |
| `feedback` | `feedback_id` | `user_id → registered_users` | `rating`, `comment`, `submitted_at` |
| `policy_documents` | `id` | — | `title`, `category`, `content`, `embedding` |

---

# Section 2 — Normalisation Justification

> 負責人：蔡晟郁

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

| Term | Usage in this schema |
|------|---------------------|
| **Functional dependency** | `(schedule_id, stop_order) → station_id` in the junction table |
| **Candidate key** | `(schedule_id, stop_order)` is the only candidate key in `metro_schedule_stops` |
| **Transitive dependency** | Storing `available_seats` as a column would introduce a transitive dependency via `bookings`; dynamic derivation avoids this |
| **3NF** | A relation is in 3NF when every non-key attribute depends on the key, the whole key, and nothing but the key |
| **1NF** | Storing sets (stop arrays) in a single column violates 1NF's requirement for atomic values; the junction table restores atomicity |

---

# Section 3 — Graph Database Design Rationale

> 負責人：黃謙儒

## 3.1 Node / Relationship / Property 設計選擇

<!-- 說明什麼資料存成 node、relationship、property，各自說明設計理由 -->

## 3.2 Graph vs Relational 論證

<!-- 具體演算法論證：Dijkstra on graph vs SQL recursive CTE -->

## 3.3 查詢類型說明

<!-- 描述 shortest path + interchange path 兩種查詢，說明 graph model 如何使其得以表達 -->

## 3.4 Node Identity

<!-- station_id 作為 node identity 的理由 -->

---

# Section 4 — Vector / RAG Design

> 負責人：蔣耀德

## 4.1 Embedding 對象與 Cosine Similarity

<!-- 說明 policy documents embed 的內容，解釋 cosine similarity 的 magnitude-independent 特性 -->

## 4.2 RAG Pipeline

<!-- 完整描述：query embedding → similarity search → retrieved documents → LLM prompt → answer -->

## 4.3 Embedding Dimension 與 Provider 切換

<!-- 說明 Ollama: 768 / Gemini: 3072；切換 provider 後的 dimension mismatch 問題 -->

---

# Section 5 — AI Tool Usage Evidence

> 負責人：三人共同

> 要求：3–5 個範例，每個須包含 Context、Prompt、Outcome 三欄；至少一個描述 AI 給出錯誤輸出的案例

## Example 1 — Interchange Station Schema Design

**Context:**
During relational schema design, we needed to model physical interchange stations where the metro and national rail networks meet. The question was whether to use a separate mapping table or FK references within the station tables themselves.

**Prompt:**
"We have `metro_stations` and `national_rail_stations` as separate tables because the two networks are operated differently. Some physical stations serve both networks. How should we model the interchange relationship in PostgreSQL — a separate junction table, or nullable FK columns within each station table?"

**Outcome:**
AI recommended bidirectional nullable FK columns: `metro_stations.interchange_nr_station_id → national_rail_stations` and `national_rail_stations.interchange_metro_station_id → metro_stations`, both with `ON DELETE SET NULL`. It argued that a junction table adds a join for a 1-to-at-most-1 relationship that is better expressed as a nullable FK. We adopted this verbatim.

---

## Example 2 — C3 Alternative Routes Deduplication

**Context:**
`query_alternative_routes` was returning duplicate route arrays — different Cypher path objects representing the same station sequence. `DISTINCT p` did not help because it compares object identity, not content.

**Prompt:**
"My Cypher query uses `MATCH p = (o)-[...]->(d)` and returns multiple paths. Many results have the same station sequence but different object identities, so `DISTINCT p` does not remove them. How can I deduplicate by actual station ID sequence?"

**Outcome:**
AI suggested extracting `[n IN nodes(p) | n.station_id]` into a named variable (`WITH [...] AS route`), then applying `RETURN DISTINCT route, total_time_min`. Because `route` is a plain list of strings, `DISTINCT` compares by value and correctly collapses duplicates. Fix committed in PR #30 and verified by `query_alternative_routes("MS01", "MS09", avoid_station_id="MS07", max_routes=3)` returning 3 distinct routes.

---

## Example 3 — C4 Interchange Path Timeout Fix

**Context:**
`query_interchange_path` timed out (>30 s) for distant station pairs. The original query used `*1..20` variable-length traversal, which enumerates all paths exhaustively — exponential in the worst case.

**Prompt:**
"My Neo4j Cypher query `MATCH p = (o)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-(d)` times out on distant station pairs. How can I make it return a result in under a second?"

**Outcome:**
AI recommended replacing the exhaustive traversal with Neo4j's built-in `shortestPath()` function and reducing depth to `*1..10`. `shortestPath()` uses BFS and returns the first path found rather than enumerating all paths. After the fix, `query_interchange_path("MS01", "NR05")` returned in <1 s with `found=True`, `total_time_min=42`. Fix committed in PR #30.

---

## Example 4 — AI Output Was Wrong: Vector Similarity Threshold

**Context:**
The RAG pipeline was returning weakly-related policy documents for some queries. We asked AI for a cosine similarity threshold to filter pgvector results.

**Prompt:**
"Our policy search using pgvector cosine similarity returns irrelevant documents. What threshold should we set so only semantically close documents are returned?"

**Outcome:**
AI recommended 0.3, claiming it was "a common starting point for semantic search." We set `VECTOR_SIMILARITY_THRESHOLD = 0.3` and tested. At 0.3, the pipeline still retrieved tangentially related documents because nomic-embed-text produces high-magnitude embeddings where even unrelated texts can score above 0.3. After empirical testing we raised the threshold to 0.5, which eliminated false positives. The lesson: AI threshold suggestions are heuristics that must be validated against the actual model and data. The threshold is now configurable via environment variable.

---

## Example 5 — Policy Document Chunking Strategy

**Context:**
Policy documents range from ~250 words (short rule summaries) to 2 000+ words (full refund policy). We needed to decide whether to embed each document as a single vector or split it into smaller chunks before embedding.

**Prompt:**
"Our policy documents vary from 250 to 2 000 words. For a RAG system where users ask specific policy questions, should we embed whole documents or chunk them? What are the trade-offs given that we are using nomic-embed-text (768-dimensional embeddings)?"

**Outcome:**
AI recommended embedding whole documents: (1) policy documents are self-contained units — chunking would separate conditions from their definitions; (2) nomic-embed-text handles paragraph-length inputs well. We adopted this: `seed_vectors.py` embeds `title + "\n\n" + content` as a single string per document. Confirmed correct during live testing (C1, C2 both ✅).

---

# Section 6 — Reflection & Trade-offs

> 負責人：三人共同

## 6.1 Design Decisions

### Decision 1：Schedule Stops as VARCHAR[] vs. Junction Table

We chose to store schedule stop sequences as `stops_in_order VARCHAR(10)[]` rather than normalised junction tables. The trade-off is between development speed and strict 3NF compliance.

The array column allowed seeding and querying with a single table scan and matched our JSON seed data format directly. However, it violates 3NF: stop position is determined by array index rather than an independent key. A junction table (`schedule_id`, `stop_order`, `station_id`) would satisfy 3NF and support row-level upserts, but required rewriting seed scripts and all queries using `array_position()` or `@>`.

Given that schedule data is read-only in this system (seeded once, never incrementally updated), the array approach is acceptable for the project scope. In a production transit system where operators add or reorder stops dynamically, a junction table is the correct design.

### Decision 2：Local LLM (llama3.2:1b) vs. Cloud LLM (Gemini)

We designed the agent to support both a local Ollama model and Gemini via a provider abstraction in `skeleton/llm_provider.py`. The default is `llama3.2:1b`, which runs on-device with no API key or cost.

The trade-off: local inference preserves user privacy and eliminates API cost, but `llama3.2:1b` (1 billion parameters) lacks the instruction-following capacity to reliably select from 16 tool functions. In live testing, the local model frequently called the wrong tool. Gemini 1.5 Flash resolved tool selection correctly but requires internet and API credentials.

We kept the local model as default because the grading guide evaluates functions by direct Python calls, not through the LLM pipeline. The provider switch is a single `.env` change (`LLM_PROVIDER=gemini`).

## 6.2 Production Considerations

The current implementation creates a new database connection per query function call (psycopg2) and uses a module-level Neo4j driver. Under concurrent load, this would exhaust PostgreSQL's default connection limit (100).

A production deployment would use `psycopg2.pool.ThreadedConnectionPool` (or PgBouncer) for PostgreSQL and configure the Neo4j driver pool size. Two other areas also need attention:

1. **Embedding provider lock-in**: The pgvector index is built for a fixed dimension (768 for Ollama, 3072 for Gemini). Switching providers after seeding breaks similarity searches due to dimension mismatch. A migration script to re-embed all documents would be required, and the index would need rebuilding.

2. **Secret management**: Credentials and API keys are currently read from `.env`. In production, these should be stored in a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault) with rotation policies and never committed to version control.
