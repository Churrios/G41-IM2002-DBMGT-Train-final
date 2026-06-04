# TransitFlow — 專案全面程式碼檢視 · 問題清單

> 檢視日期：2026-06-04
> 範圍：relational / vector / graph / skeleton 全專案
> 分工依據：[TEAM.md](../TEAM.md)
> 嚴重度：🔴 會導致功能崩潰或評分大量失分 ｜ 🟠 評分項目失分 ｜ 🟡 品質/一致性/加分

---

## 0. 摘要（先看這裡）

| # | 嚴重度 | 負責人 | 問題一句話 |
|---|--------|--------|-----------|
| A1 | ✅ | 蔡晟郁 | `seed_postgres.py` 座位 `fare_class` 讀錯層級 → 整個 seeding 交易 rollback，PG 沒資料 |
| A2 | ✅ | 蔡晟郁 | `login_user` 沒回傳 `first_name`/`surname`，但 UI 直接取用 → **登入直接崩潰** |
| A3 | ✅ | 蔡晟郁 | `schema.sql` 的 HNSW index 寫法少 index 名稱（`CREATE INDEX IF NOT EXISTS ON ...`）|
| A4 | ✅ | 蔡晟郁 | `query_user_profile` 回 `date_of_birth`，評分 B6 期望 `year_of_birth` |
| A5 | ✅ | 蔡晟郁 | schema 設計分：FK 無 `ON DELETE`、PK/刪除策略無 comment、stops 用陣列非 junction table |
| C1 | ✅ | 黃謙儒 | Graph schema 仍是 `Station`/`CONNECTS_TO`/`INTERCHANGE_WITH`，評分要 `MetroStation`/`NationalRailStation` + `METRO_LINK`/`RAIL_LINK`/`INTERCHANGE_TO` |
| C2 | ✅ | 黃謙儒 | `query_cheapest_route` 用 stops×係數估票價，非圖內邊屬性（Q5=A 已定案要寫入邊）|
| C3 | ✅ | 黃謙儒 | rewrite 後 `query_station_connections` 的 `r.network`、driver per-call/singleton 需一併對齊 |
| J1 | 🟠 | 蔣耀德 | `rag.search_with_rerank` 沒被 `agent.py` 接上，reranking 功能在 Live Testing 不會被觸發 |
| J2 | 🟡 | 蔣耀德 | embedding 維度（768/3072）與相似度門檻需依實際 provider 驗證 |
| S1 | 🟡 | 共用 | `config.py` 預設埠（5432/7687）與 docker（5433/7688）不一致，靠 `.env` 補救 |
| S2 | 🟡 | 共用 | 各檔「為什麼這樣設計」的 inline 註解偏少（Code Quality /1–2）|

---

## 1. 蔡晟郁（Relational DB Engineer）

> 檔案：`databases/relational/schema.sql`、`databases/relational/queries.py`、`skeleton/seed_postgres.py`

### ✅ A1 — 座位 seeding 讀錯欄位層級，會讓整個 PG seeding 失敗
**檔案**：[skeleton/seed_postgres.py:211-238](../skeleton/seed_postgres.py#L211-L238)（`seed_seat_layouts`）

`national_rail_seat_layouts.json` 的結構是 **`fare_class` 在 coach 層**，seat 只有 `seat_id / row / column`：
```json
{ "coach": "A", "fare_class": "first", "seats": [{"seat_id":"A01","row":1,"column":"A"}, ...] }
```
但目前程式碼是 `seat.get("fare_class")`：
```python
for seat in seats:
    rows.append((schedule_id, seat.get("seat_id"), coach_id,
                 seat.get("row"), seat.get("column"), seat.get("fare_class")))  # ← None
```
`seat_layouts.fare_class` 是 `NOT NULL`，插入 `None` → IntegrityError → 因為 `seed_postgres` 用單一交易最後才 commit，**整批 seeding 全部 rollback，PostgreSQL 一筆資料都沒有**。
（這也讓後續 `query_available_seats` / `execute_booking` 全部失效。）

**修法**：改從 coach 取 `fare_class`：
```python
for coach in coaches:
    coach_id   = coach.get("coach")
    fare_class = coach.get("fare_class")          # fare_class 在 coach 層
    for seat in coach.get("seats", []):
        rows.append((schedule_id, seat.get("seat_id"), coach_id,
                     seat.get("row"), seat.get("column"), fare_class))
```

### ✅ A2 — `login_user` 缺 `first_name`/`surname`，UI 登入會 KeyError 崩潰
**檔案**：[databases/relational/queries.py:624-642](../databases/relational/queries.py#L624-L642)

`registered_users` 只有 `full_name`（無 `first_name`/`surname`），`login_user` 回傳 `SELECT *` 的 dict，所以**沒有** `first_name`/`surname`。但：
- 它自己的 docstring 宣稱會回傳 `first_name, surname`；
- UI [skeleton/ui.py:123](../skeleton/ui.py#L123) 直接 `f"{user['first_name']} {user['surname']}"`。

→ 任何一次成功登入都會 `KeyError: 'first_name'`，**登入功能完全壞掉**（`ui.py` 標示「不需修改」，所以要在 relational 層補齊）。

**修法**：在 `login_user` 回傳前，由 `full_name` 拆出：
```python
user = dict(row)
user.pop("password", None)
parts = (user.get("full_name") or "").split(" ", 1)
user["first_name"] = parts[0]
user["surname"]    = parts[1] if len(parts) > 1 else ""
return user
```

### ✅ A3 — HNSW index 缺名稱（語法/索引建立風險）
**檔案**：[databases/relational/schema.sql:234](../databases/relational/schema.sql#L234)
```sql
CREATE INDEX IF NOT EXISTS ON policy_documents USING hnsw (embedding vector_cosine_ops);
```
PostgreSQL 規定 **使用 `IF NOT EXISTS` 時必須指定 index 名稱**，此寫法會 `syntax error at or near "ON"`。schema.sql 是掛在 `docker-entrypoint-initdb.d` 初始化的，這行在最後，最壞情況是索引沒建（向量搜尋退化成 seq scan 仍能跑，所以平常沒人察覺，但評分檢查索引/效能會失分）。

**修法**：
```sql
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding
    ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

### ✅ A4 — `query_user_profile` 回 `date_of_birth`，評分期望 `year_of_birth`
**檔案**：[databases/relational/queries.py:276-285](../databases/relational/queries.py#L276-L285)
評分細則 Live B6 標注：「⚠️ 回傳 `date_of_birth`，評分期望 `year_of_birth`」。

**修法**：回傳 dict 時補一個 `year_of_birth`：
```python
prof = dict(row)
if prof.get("date_of_birth"):
    prof["year_of_birth"] = prof["date_of_birth"].year
return prof
```

### ✅ A5 — schema 設計與註解（Task 4 文件 / Code Quality 失分點）
**檔案**：`databases/relational/schema.sql`
評分細則 STUDENT_GUIDE_CODE 標注的失分項：
- **FK cascade 未指定**：所有 `REFERENCES` 都沒寫 `ON DELETE CASCADE/RESTRICT/SET NULL`。建議對 `bookings`/`payments`/`feedback` 等明確指定。
- **PK 型別選擇無 comment**：在主鍵旁加一行說明為何用 `VARCHAR` 而非 `SERIAL/UUID`。
- **刪除策略無 comment**：目前用 `status='cancelled'` 軟刪除，但沒註解說明一致策略。
- **正規化**：`stops_in_order` 用 `VARCHAR[]` 而非獨立 junction table（`schedule_stops(schedule_id, stop_order, station_id)`）。屬設計取捨——若不改 schema，至少在 `AI_SESSION_CONTEXT.md` 寫明「為效能/簡潔選陣列」的理由來保住設計分。

---

## 2. 黃謙儒 / Chien（Graph DB Engineer）

> 檔案：`databases/graph/queries.py`、`skeleton/seed_neo4j.py`、`databases/graph/seed.cypher`
> 詳細實作步驟見 [Chien_graph_正式開發流程.md](Chien_graph_正式開發流程.md)（Q1=A 已鎖定）

### ✅ C1 — Graph schema 命名與評分標準相反（核心重寫）
**檔案**：[skeleton/seed_neo4j.py](../skeleton/seed_neo4j.py)、[databases/graph/queries.py](../databases/graph/queries.py)、[databases/graph/seed.cypher](../databases/graph/seed.cypher)

現況：單一 `Station` 標籤 + `CONNECTS_TO` + `INTERCHANGE_WITH`。
評分標準明文檢查（STUDENT_GUIDE_CODE Task 4 / STUDENT_GUIDE_LIVE Section A、C4）：
- 節點 `MetroStation` / `NationalRailStation`
- 關係 `METRO_LINK` / `RAIL_LINK`（含 `travel_time_min`）
- 換乘 `INTERCHANGE_TO`

→ Task 4（/8）與 Live A 直接失分。已定案 **Q1=A 全面改用評分標準模型**，需重寫三個檔案：
1. `seed_neo4j.py`：建 unique constraints、MERGE 兩種節點、MERGE `METRO_LINK`/`RAIL_LINK`（含票價屬性）、MERGE `INTERCHANGE_TO` 雙向（`transfer_time_min=5`）。
2. `queries.py`：6 個 `query_*` 函式改走新標籤/關係；`-[:INTERCHANGE_TO]-` 用無向比對。
3. `seed.cypher`：補可讀 schema/constraint，讓靜態評分 TA 直接看到三種關係。

### ✅ C2 — `query_cheapest_route` 票價來源（對齊 Q5=A）
**檔案**：[databases/graph/queries.py:182-208](../databases/graph/queries.py#L182-L208)
目前用 `1.0 + stops*0.5`（metro）/`2.0 + stops*1.2|2.0`（rail）在 Python 端估算，`fare_class` 對「路徑選擇」沒有實際影響。評分 C2 要求 fare_class「明顯影響邊權重」。

**修法（Q5=A 已定案）**：seeding 時把票價寫進邊屬性（metro `fare_usd`；rail `fare_standard_usd`/`fare_first_usd`），`query_cheapest_route` 直接用 `apoc.algo.dijkstra` 以該屬性為權重。

### ✅ C3 — rewrite 連帶要處理的小一致性
- [queries.py:433](../databases/graph/queries.py#L433) `query_station_connections` 回傳 `r.network`；新 schema 邊上沒有 `network`，改用關係型別或站別前綴判斷。
- **driver 模式不一致**：現有 `queries.py` 用 module-level singleton（[queries.py:35](../databases/graph/queries.py#L35)），但定案 Q10=維持 per-call。兩者皆可，但要**統一**並加註解說明 production 取捨（影響 Code Quality）。
- 6 個函式補 3–5 條「為什麼」的 inline 註解（APOC 為何、`hops` 為何要 `int()` 內嵌等）。

---

## 3. 蔣耀德（Vector DB & RAG Engineer）

> 檔案：`skeleton/seed_vectors.py`、`skeleton/llm_provider.py`、`skeleton/reranker.py`、`skeleton/rag.py`

### 🟠 J1 — reranker 沒被接進 pipeline，Live Testing 不會跑到
**檔案**：[skeleton/rag.py](../skeleton/rag.py)（`search_with_rerank`）vs [skeleton/agent.py:384-395](../skeleton/agent.py#L384-L395)

`agent.py` 的 `search_policy` 直接呼叫 `query_policy_vector_search`，**完全沒用到** `rag.search_with_rerank` / `reranker.rerank`。也就是 reranking（cross-encoder 重排）這個 RAG 加值功能在實際聊天/評分時不會被觸發 → 等於白寫。

**修法**（需與負責 `agent.py` 的人協調，因為 `agent.py` 標示「不需修改」）：把 `search_policy` 改成
```python
from skeleton.rag import search_with_rerank
embedding = llm.embed(params["query"])
docs = search_with_rerank(embedding, params["query"], top_k=VECTOR_TOP_K)
```
若團隊決定不動 `agent.py`，至少準備一支 `scratch/test_rerank.py` 在 Live Testing 時 demo 重排前後差異。

### 🟡 J2 — embedding 維度與相似度門檻需依實際 provider 驗證
- `schema.sql` 寫死 `vector(768)`（對應 Ollama nomic-embed-text）。若改用 Gemini（`GEMINI_EMBED_DIM=3072`）必須改 schema 並 reset DB——這牽動 `schema.sql`（蔡），需跨人協調。
- [config.py:45](../skeleton/config.py#L45) `VECTOR_SIMILARITY_THRESHOLD=0.5`：用 nomic-embed 的 cosine 相似度，0.5 門檻偏高，可能把相關文件全濾掉。實跑 `seed_vectors.py` 後用幾個範例 query 驗證 `query_policy_vector_search` 真的有回東西，必要時調低門檻。
- `seed_vectors.py` 邏輯本身 OK（chunk + lru_cache + 維度檢查），確認 seeding 真的有 `policy_documents` > 0 即可。

---

## 4. 共用 / 跨領域（建議三人協調）

### 🟡 S1 — `config.py` 預設埠與 docker 不符
**檔案**：[skeleton/config.py:31](../skeleton/config.py#L31)、[skeleton/config.py:39](../skeleton/config.py#L39)
預設 `PG_PORT=5432`、`NEO4J_URI=bolt://localhost:7687`，但 docker 對主機映射是 `5433` / `7688`。靠 `.env`（已正確設定）補救——只要每個人都有把 `.env.example` 複製成 `.env` 就沒事。建議：把 config 預設值直接改成 5433 / 7688，避免新成員忘記設 `.env` 時連不上。

### 🟡 S2 — Inline「為什麼」註解普遍偏少
評分 Code Quality（STUDENT_GUIDE_CODE）明列：「至少 3–5 個非顯然的 SQL/Cypher 函式要有解釋『為什麼』的註解」。三個 DB 層都建議各補幾條（例：為何用 `array_position` 判站序、為何 `INTERCHANGE_TO` 建雙向、為何 reranker 先撈 Top 20 再取 Top 5）。

---

## 5. 已確認「沒問題、不用動」的部分（讓大家放心）

- Relational 的 `execute_booking` / `execute_cancellation` 交易處理（commit/rollback/退款視窗計算）邏輯完整正確。
- `query_national_rail_availability`、`query_metro_schedules`、fare 計算、auth（bcrypt、secret question）皆正常。
- `llm_provider.py` 雙 provider 切換、Ollama native tool-calling 完整。
- Graph 6 個函式的**演算法與回傳格式**（APOC dijkstra、`hops=0` 特判、空結果回 `{}`/`[]` 不 raise）都正確，只差 schema 命名要換。
- `agent.py` 的 fallback routing、`_flatten_to_text` 通用攤平都健全。

---

### 建議修復順序
1. ✅ A1、A2（不修就跑不起來 / 登不進去）→ 蔡已處理。
2. 🔴 C1（Graph 重寫）→ Chien 依正式開發流程動工。
3. ✅ A3、A4 → 已修。🟠 J1 → 蔣待處理。
4. ✅ A5、🟡 S2 → 蔡已補 schema 細節與部分註解。
