# TransitFlow — Database Design Document

> IM2002 Final Project | Group 41
> 蔡晟郁 · 黃謙儒 · 蔣耀德

---

# Section 1 — Entity-Relationship Diagram

> 負責人：蔡晟郁

## 1.1 ER Diagram

<!-- 插入 dbdiagram.io / draw.io 匯出的圖片 -->

## 1.2 Entity Overview

| Entity | PK | Key FKs | Representative Fields |
|--------|----|---------|-----------------------|
| `registered_users` | `user_id` | — | `email`, `password`, `is_active` |
| `metro_stations` | `station_id` | `interchange_nr_station_id → national_rail_stations` | `name`, `lines`, `zone` |
| `national_rail_stations` | `station_id` | `interchange_metro_station_id → metro_stations` | `name`, `managed_by` |
| `metro_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → metro_stations` | `line`, `stops_in_order`, `frequency_min` |
| `national_rail_schedules` | `schedule_id` | `origin_station_id`, `destination_station_id → national_rail_stations` | `line`, `service_type`, `std_base_fare_usd` |
| `seat_layouts` | `(schedule_id, seat_id)` | `schedule_id → national_rail_schedules` | `coach`, `row`, `column`, `fare_class` |
| `bookings` | `booking_id` | `user_id → registered_users`, `schedule_id → national_rail_schedules` | `travel_date`, `seat_id`, `status` |
| `metro_travel_history` | `trip_id` | `user_id → registered_users`, `schedule_id → metro_schedules` | `travel_date`, `amount_usd`, `status` |
| `payments` | `payment_id` | `booking_id → bookings` | `amount_usd`, `method`, `status` |
| `feedback` | `feedback_id` | `user_id → registered_users` | `rating`, `comment`, `submitted_at` |
| `policy_documents` | `id` | — | `title`, `category`, `content`, `embedding` |

---

# Section 2 — Normalisation Justification

> 負責人：蔡晟郁

## 2.1 Normalisation Decisions (3NF)

<!-- 說明 stops_in_order VARCHAR[] 的設計決策 -->
<!-- 說明是哪個 normal form、哪個 functional dependency 驅動了這個決定 -->

## 2.2 De-normalisation Trade-offs

<!-- 說明 available_seats 動態計算（不存欄位）的設計決策 -->
<!-- 或說明 stops_in_order 陣列取代 junction table 的理由 -->

## 2.3 Password Hashing

<!-- 說明 bcrypt 演算法、為何優於 MD5/SHA-1、cost factor、salt 如何防 rainbow table -->

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

在本系統中，被轉換為 embedding 的對象是**政策文件 (Policy Documents)**，包含各類票務與退費規則。

在比對使用者查詢與政策文件時，**Cosine similarity** 非常適合用來評估語意相似度，因為它是 **magnitude-independent**（不受向量長度影響）。它不是去測量兩個點之間的絕對距離，而是**測量 embedding space 中的方向相似度**。這代表即使文本長度或詞彙頻率不同，只要兩個文件表達的語意方向一致，就能獲得很高的相似度分數。

## 4.2 RAG Pipeline

我們的 RAG pipeline 完整運作包含以下四個階段：
1. **Query Embedding**：當使用者輸入自然語言的問題時，系統首先會透過設定好的 LLM embedding 模型，將這段文字 query 轉換成一個高維度的數學向量。
2. **Similarity Search (pgvector)**：接著，將這個向量化的 query 與 PostgreSQL 資料庫中預先 embedding 好的政策文件 chunk 進行比對。這裡會使用 `pgvector` 擴充功能執行 cosine similarity 搜尋，找出在向量空間中最接近的 nearest neighbours。
3. **Retrieved Documents**：資料庫會回傳 top-K 個語意最相關的 document chunks 以及它們的 similarity scores。這些 chunks 包含了回答使用者問題所需的實際事實與知識。
4. **LLM Prompt and Answer**：最後，系統會將這些擷取出來的文本 chunks 注入到 LLM prompt 的 context window 內。LLM 會被指示只能根據這些提供的 context 來生成最終的回答，從而確保回應是有根據的，並有效防止 hallucination（幻覺）。

## 4.3 Embedding Dimension 與 Provider 切換

不同的 LLM 供應商所產生的 embeddings 會有不同的維度大小：
- **Ollama**：使用 **768 維 (dimensions)**。
- **Gemini**：使用 **3072 維 (dimensions)**。

因為資料庫中的 vector index 在初始 seeding 過程建立時，就會嚴格綁定該 dimension 大小。所以如果在 **seeding 後切換 provider，會造成 dimension mismatch，導致 index 失效**。因此，如果改變了 LLM provider，就**必須重新 seed** vector database，以確保所有 document embeddings 的維度大小符合新的設定。

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
