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

# Section 3 — 圖形資料庫設計理由

> 負責人：黃謙儒

本系統的雙軌路網（城市捷運 M1–M4 + 國鐵 NR1–NR2）以 **Neo4j 圖形資料庫**建模，專責處理「路徑」類查詢：最短路徑、最便宜路徑、繞站替代路線、跨網換乘路徑、誤點漣漪分析。關聯式資料庫（PostgreSQL）負責交易性資料（訂位、付款、座位），兩者各取所長。實際拓撲：**30 個節點**（20 個 MetroStation + 10 個 NationalRailStation）、**66 條邊**（42 條 METRO_LINK + 18 條 RAIL_LINK + 6 條 INTERCHANGE_TO）。

## 3.1 Node / Relationship / Property 設計選擇

### 節點（Node）：車站

我們把**車站**設計成節點，理由不只是「車站是一個實體」，而是車站具備節點該有的特徵：(1) **被多條路線、多筆班次重複引用（多對多）**——MS01 同時屬於 M1、M2 並被多筆 schedule 引用，節點天然支援多對多；(2) **是 pattern matching（圖形遍歷）的對象**——所有路由查詢本質都是「從某站沿連線走到另一站」；(3) **需要穩定身分**，能跨班次、跨網路被一致參照（見 §3.4）。

**為何採分離標籤（split-label）而非單一 `Station`**：拆成 `MetroStation` 與 `NationalRailStation` 兩種標籤，而非單一 `Station` 加 `network` 屬性。理由：對齊評分 / 測試標準（Task 4、Live 以 label 名稱明文檢查）；查詢可用關係型別 `'METRO_LINK|RAIL_LINK'` 把遍歷限制在同網內，使「同網最短」與「跨網換乘」成為語意清楚的兩種查詢；兩網屬性集本就不同（捷運站有 `is_interchange_national_rail`，國鐵站有 `is_interchange_metro`、`interchange_metro_station_id`）。

### 關係（Relationship）：車站之間的連線

| 關係型別 | 連接 | 用途 |
|----------|------|------|
| `METRO_LINK` | `(MetroStation)→(MetroStation)` | 捷運區段 |
| `RAIL_LINK` | `(NationalRailStation)→(NationalRailStation)` | 國鐵區段 |
| `INTERCHANGE_TO` | `(MetroStation)↔(NationalRailStation)` | 跨網實體換乘 |

連線適合做關係而非另一張表，因為它具備關係的本質：(1) **有方向性**——班次有行進方向，以有向邊建模，Dijkstra 可沿方向遍歷（`INTERCHANGE_TO` 刻意建雙向兩條有向邊，使換乘可雙向通行）；(2) **承載屬性**——每條連線帶有「通過這段花多少時間、多少錢」的資訊，這是**邊的屬性**，不屬於任何單一車站。這正是圖形勝過關聯式 FK 之處：relational FK 只能表達「A 與 B 有關聯」，無法在關聯**上**自然掛載 `travel_time_min`、`fare_usd`；圖形的關係則可以。

### 屬性（Property）：放在節點還是邊上

屬性歸屬遵循「屬性描述的是誰」：**節點上**放 `station_id`、`name`、`lines`、`is_interchange_*`（描述車站本身）；**邊上**放 `METRO_LINK` 的 `line`/`travel_time_min`/`fare_usd`、`RAIL_LINK` 的 `line`/`travel_time_min`/`fare_standard_usd`/`fare_first_usd`、`INTERCHANGE_TO` 的 `transfer_time_min`（固定 5 分鐘；換乘不走實體軌道故無 `travel_time_min`）。把時間與票價放在**邊上**的原因：(1) 它們是「通過某區段」的成本，本質是邊的屬性；(2) 它們是最短路徑演算法的**權重來源**——`apoc.algo.dijkstra` 直接讀邊上的權重屬性計算。票價在 seeding 時即寫進邊，使「最便宜路徑」能直接以 `fare_*_usd` 當權重跑 Dijkstra，讓 fare_class 真正改變被選到的**路徑**而非只改總額。

## 3.2 Graph vs Relational 論證

路由查詢本質上是**加權圖上的圖遍歷問題**。我們主張圖形優於關聯式，理由是具體的演算法差異，而非籠統的「graph 比較快」。

**圖形作法**：Neo4j 以 **index-free adjacency** 儲存——每個節點直接持有指向鄰居關係的指標，「取得某站所有鄰站」是 **O(1)**（與全圖大小無關）、無需 join。在此之上，最短路徑用 `apoc.algo.dijkstra`（加權 Dijkstra，約 **O((V + E) log V)**）或 `shortestPath()`（無權 BFS，找到第一條即停），只觸碰實際可達的子圖。

**關聯式作法**：SQL 沒有原生圖遍歷，要表達「找最短路徑」須用 **recursive CTE**：(1) 每層遞迴都要對 edge 表做一次 join，結果集隨深度**組合爆炸**；(2) 必須在每條中間路徑攜帶「已訪節點」清單以**防環**，帶來額外儲存與比對成本；(3) **沒有「找到最短就停」的原生機制**，會展開**所有**符合路徑最後才 `MIN` 取最短，無法提早剪枝。節點稍多、路徑稍長時，中間結果指數膨脹而超時。

**本專案實證**：`query_interchange_path` 最初用 `-[...*1..20]-` 變長**全列舉**，在僅 30 節點的圖上對較遠站對就 **>30 秒超時**（正是「展開所有路徑」的組合爆炸）；改用 `shortestPath()`（BFS，找到第一條即回傳）後同樣查詢 **<1 秒**完成。同一個圖、同一個問題，演算法從「窮舉」換成「BFS 提早停止」就是數量級差距——這就是圖形模型適合路由查詢的根本原因。

## 3.3 查詢類型說明

**查詢一：同網最短路徑（`query_shortest_route`）**

```cypher
MATCH (o {station_id: $origin_id}), (d {station_id: $dest_id})
CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', 'travel_time_min')
YIELD path, weight
RETURN [n IN nodes(path) | {station_id: n.station_id, name: n.name}] AS stations,
       weight AS total_time_min
```

graph model 如何使其可表達：關係型別過濾 `'METRO_LINK|RAIL_LINK'` 讓遍歷只走同網軌道邊，**刻意排除** `INTERCHANGE_TO`，故同網不可達時自然回 `found=False`；`travel_time_min` 存在邊上直接當 Dijkstra 權重；把權重參數換成 `'fare_usd'`/`'fare_standard_usd'` 即變成最便宜路徑查詢（`query_cheapest_route`），複用同一套圖結構。

**查詢二：跨網換乘路徑（`query_interchange_path`）**

```cypher
MATCH p = shortestPath(
            (o {station_id: $origin_id})
            -[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..10]-
            (d {station_id: $dest_id}))
WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
```

graph model 如何使其可表達：關鍵在於**把三種關係型別混在同一個 pattern** 裡遍歷——軌道邊負責網內移動，`INTERCHANGE_TO` 負責跨越捷運↔國鐵邊界，一條路徑可「捷運走幾站 → 經 INTERCHANGE_TO 換到國鐵 → 國鐵再走幾站」全在單一查詢表達；`WHERE any(... INTERCHANGE_TO)` 保證確實有換乘。同樣需求在關聯式中須跨多張停靠表與換乘對應表做多重 UNION 再包進 recursive CTE 才能勉強表達。

> （第三種查詢 `query_delay_ripple` 用變長遍歷 `-[:METRO_LINK|RAIL_LINK*1..N]-` 配合 `min(length(path))`，找出誤點站 N 跳之內受影響的所有車站。）

## 3.4 Node Identity

我們以 **`station_id`** 作為節點唯一識別，並對每種標籤建立 unique constraint：

```cypher
CREATE CONSTRAINT FOR (s:MetroStation)        REQUIRE s.station_id IS UNIQUE;
CREATE CONSTRAINT FOR (s:NationalRailStation) REQUIRE s.station_id IS UNIQUE;
```

選擇 `station_id`（如 `MS01`、`NR01`）的理由：(1) **來自來源資料的穩定外部鍵**，直接取自 mock data JSON，不需另造代理鍵；(2) **跨兩網全域唯一**，捷運 `MS` 前綴、國鐵 `NR` 前綴命名空間不重疊，混在跨網查詢也不撞號；(3) **與 PostgreSQL 1:1 對應，跨庫查詢免轉換**——Neo4j 的 `station_id` 與關聯式 `station_id` 完全相同，應用層拿到圖形回傳的 `station_id` 可直接到 PostgreSQL 查明細，兩庫間不需任何 ID 對照；(4) **人類可讀**，便於除錯與在 Neo4j Browser 手動驗證。unique constraint 附帶建立索引，使 `MATCH (s {station_id: ...})` 的起點定位是索引查找而非掃描。

---

# Section 4 — Vector / RAG Design

> 負責人：蔣耀德

## 4.1 Embedding 對象與 Cosine Similarity

在本系統中，被轉換為 embedding 的對象是**政策文件 (Policy Documents)**，包含各類票務與退費規則。

在比對使用者查詢與政策文件時，**Cosine similarity** 非常適合用來評估語意相似度，因為它是 **magnitude-independent**（不受向量長度影響）。它不是去測量兩個點之間的絕對距離，而是**測量 embedding space 中的方向相似度**。這代表即使文本長度或詞彙頻率不同，只要兩個文件表達的語意方向一致，就能獲得很高的相似度分數。

## 4.2 RAG Pipeline

我們的 RAG pipeline 完整運作包含以下四個階段，確保系統能給出有憑有據的回答：
1. **Query Embedding**：當使用者輸入自然語言的問題（例如問退票規則）時，系統首先會透過設定好的 LLM embedding 模型（預設使用 Ollama 的 `nomic-embed-text`），將這段文字轉換成一個高維度（768維）的數學向量。
2. **Similarity Search (pgvector)**：接著，將這個向量化的 query 與 PostgreSQL 資料庫中 `policy_documents` 資料表內預先計算好的文件 embedding 進行比對。這裡會使用 `pgvector` 的 `<=>` 運算子來執行 cosine similarity 搜尋，找出在向量空間中最接近的 nearest neighbours，並設定適當的 threshold（例如 0.5）來過濾無關文件。
3. **Retrieved Documents**：資料庫會依據 similarity scores 降冪排序，回傳 top-K 個最相關的 document chunks（如退款政策段落）。這些 chunks 包含了回答使用者問題所需的實際事實、條文與知識。
4. **LLM Prompt and Answer**：最後，系統會將這些擷取出來的文本 chunks，連同使用者的原始問題，一併注入到 LLM (例如 `llama3.2:1b` 或 Gemini) 的 Prompt context window 內。LLM 的 System Prompt 會嚴格指示它「只能根據提供的 context 來生成最終回答」，從而確保回應是有實體文件根據的，有效防止 Hallucination（幻覺）。

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
