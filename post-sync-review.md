# Post-Sync Review — TransitFlow 整合檢查

> 更新：2026-06-05 | 範圍：所有個人代辦完成後，三人共同下一步

---

## 本次工作紀錄（蔡晟郁，2026-06-05）

> 本節說明今天蔡完成了哪些事、發現了什麼問題，讓黃和蔣同步狀況。

### 修正的 bug（蔡的檔案）

| 檔案 | 問題 | 影響 |
|------|------|------|
| `seed_postgres.py` | `seed_seat_layouts`：`fare_class` 從 `seat` 層讀，應從 `coach` 層讀，導致值為 `None` → 整個 PG seeding rollback，資料庫一筆資料都沒有 | 所有 B 系列 live testing 全部失敗 |
| `seed_postgres.py` | `seed_metro_travels`：mock data 的 `stops_travelled` 有 null，schema 設 `NOT NULL`，改為 `or 0` | seeding 過程中 IntegrityError |
| `queries.py` | `login_user`：未拆分 `full_name` → `first_name` / `surname`，但 `ui.py` 直接使用這兩個 key，登入成功後立刻 `KeyError` crash | 登入功能完全壞掉 |
| `queries.py` | `query_user_profile`：未回傳 `year_of_birth`，改為 `date_of_birth.year`，評分 B6 要求此欄位 | B6 評分失分 |
| `schema.sql` | HNSW index 語法：`CREATE INDEX IF NOT EXISTS ON ...` 缺少 index 名稱，PostgreSQL 會 syntax error，index 根本沒建 | 向量搜尋退化成 seq scan |

### 環境建立過程

- 從無到有完整建立本機環境（venv、.env、Docker、Ollama）
- Ollama 需使用官方安裝，Homebrew 版缺少 `llama-server` binary 無法跑模型
- 跑通三個 seed scripts：PG（修正後）、vectors（101 chunks）、Neo4j（20站、66條邊）

### 全量 Python 測試結果

B1–B10 全部函式正確。C 系列發現三個問題（**黃謙儒的檔案**）：

| 函式 | 嚴重度 | 問題 |
|------|--------|------|
| C4 `query_interchange_path` | ✅ | 已修（PR #30）：`shortestPath(*1..10)` 取代 `*1..20` 全列舉 |
| C5 `query_delay_ripple` | ✅ | 已修（PR #27）：`MATCH path =` + `min(length(path))` |
| C3 `query_alternative_routes` | ✅ | 已修（PR #30）：`WITH` + `RETURN DISTINCT` 去重 |

修法已詳細寫在下方各問題區塊，黃可以直接複製 Cypher 修改。

### UI 測試觀察（llama3.2:1b 行為）

- 模型頻繁選錯 tool（例如問 user profile 卻叫 get_bookings、問 station connections 卻傳 schema 作為參數）
- 模型會在呼叫 tool 前先「猜」答案，有時直接幻覺，不看資料庫
- **所有 tool 的回傳資料本身都正確**，問題出在 LLM 選 tool 的邏輯
- TA 若直接呼叫 Python function 測試，所有正確的函式都會通過

詳細測試紀錄見：[live-testing-notes.md](live-testing-notes.md)

---

## 零、立即下一步（三人共同討論）

### ✅ Step A — 環境跑通（蔡晟郁已完成，2026-06-05）

- [x] seed_postgres 無 traceback（修正 stops_travelled null → 0）
- [x] seed_vectors 無 traceback（101 chunks 存入）
- [x] seed_neo4j 無 traceback（20 MetroStation, 10 NationalRailStation, 42 METRO_LINK, 18 RAIL_LINK, 6 INTERCHANGE_TO）
- [x] ui.py 可正常開啟並登入

> ⚠️ Ollama 需使用**官方安裝腳本**（`curl -fsSL https://ollama.com/install.sh | sh`），Homebrew 版缺少 `llama-server` binary 會導致 embed 呼叫失敗。

---

### 🔴 Step B — `stops_in_order` 改 junction table（三人協作）

**修改理由**：`stops_in_order VARCHAR(10)[]` 使用 array 欄位儲存停靠站順序，違反 3NF——站的位置由 array index 決定，而非獨立的 primary key。評分標準明確點名「schedule stops must be in a separate junction table (not an array column)」，是 Task 1 Normalisation 扣分項。

**執行順序**：蔡先做（schema + queries）→ PR merge → 黃和蔣才能開始

**分工（各自負責自己的檔案）：**

#### 🔵 蔡晟郁（先做，其他人等此 PR merge）

**`databases/relational/schema.sql`：**

移除：
- `metro_schedules` 的 `stops_in_order VARCHAR(10)[] NOT NULL` 欄位
- `national_rail_schedules` 的 `stops_in_order VARCHAR(10)[] NOT NULL` 欄位
- `CREATE INDEX idx_metro_schedules_stops ... USING GIN (stops_in_order)`
- `CREATE INDEX idx_nr_schedules_stops ... USING GIN (stops_in_order)`

新增（放在 seat_layouts 之前）：
```sql
CREATE TABLE metro_schedule_stops (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    stop_order   INT          NOT NULL,
    station_id   VARCHAR(10)  NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    PRIMARY KEY (schedule_id, stop_order)
);

CREATE TABLE national_rail_schedule_stops (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    stop_order   INT          NOT NULL,
    station_id   VARCHAR(10)  NOT NULL REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    PRIMARY KEY (schedule_id, stop_order)
);
```

**`databases/relational/queries.py`（3 個地方）：**

1. `query_national_rail_availability`（line ~106–108）：
   - 舊：`WHERE s.stops_in_order @> ARRAY[...]` + `HAVING array_position(...) < array_position(...)`
   - 新：JOIN `national_rail_schedule_stops` 兩次（origin / dest），HAVING `o_stop.stop_order < d_stop.stop_order`

2. `query_metro_schedules`（line ~175–185）：
   - 舊：`WHERE stops_in_order @> ARRAY[...]` + Python `.index()` 過濾方向
   - 新：JOIN `metro_schedule_stops` 兩次，SQL 直接比較 stop_order；並用 subquery 回傳 `stops_in_order` array，讓 agent.py 不需改：
   ```sql
   ARRAY(SELECT station_id FROM metro_schedule_stops
         WHERE schedule_id = s.schedule_id ORDER BY stop_order) AS stops_in_order
   ```

3. `execute_booking`（line ~397–416）：
   - 舊：SELECT `stops_in_order` → Python `.index()` 算 stops_count
   - 新：JOIN `national_rail_schedule_stops` 取 o_stop.stop_order 和 d_stop.stop_order，`stops_count = d_stop_order - o_stop_order`

#### 🟢 黃謙儒（等蔡的 PR merge 後再做）

**`skeleton/seed_postgres.py`：**

`seed_metro_schedules`：
1. columns list 移除 `"stops_in_order"`，rows 對應值也移除
2. insert 完 metro_schedules 後，接著 insert junction table：
```python
stop_rows = []
for s in data:
    for i, station_id in enumerate(s.get("stops_in_order", [])):
        stop_rows.append((s["schedule_id"], i, station_id))
insert_many(cur, "metro_schedule_stops",
            ["schedule_id", "stop_order", "station_id"], stop_rows)
print(f"Seeded {len(stop_rows)} metro schedule stops.")
```

`seed_national_rail_schedules`：同上邏輯，改用 `national_rail_schedule_stops`：
```python
stop_rows = []
for s in data:
    for i, station_id in enumerate(s.get("stops_in_order", [])):
        stop_rows.append((s["schedule_id"], i, station_id))
insert_many(cur, "national_rail_schedule_stops",
            ["schedule_id", "stop_order", "station_id"], stop_rows)
print(f"Seeded {len(stop_rows)} national rail schedule stops.")
```

#### 🟣 蔣耀德（等蔡的 PR merge 後確認）

**`skeleton/agent.py`：**

改動極小。蔡的 `query_metro_schedules` 會繼續回傳 `stops_in_order` key（用 subquery），所以 line 328 的 `sched.get("stops_in_order") or []` **不需要改**。

但可以移除已無必要的 isinstance 檢查（line 329–331）：
```python
# 可刪除（蔡改完後 stops 永遠是 list，不會是 string）
if isinstance(stops, str):
    import json as _json
    stops = _json.loads(stops)
```

---

## 一、行動清單

### 🔵 蔡晟郁（Relational DB）

| 優先 | 項目 |
|------|------|
| ✅ | `schema.sql`：所有 FK 加 `ON DELETE`（16 條，RESTRICT / SET NULL / CASCADE） |
| ✅ | `schema.sql`：PK 設計說明 comment（header + 每個表格 PK 欄位） |
| ✅ | `schema.sql`：soft delete 策略 comment（`is_active` 欄位） |
| ✅ | `schema.sql`：HNSW index 補上名稱（語法修正） |
| ✅ | `queries.py`：5 個函式加 inline WHY comment |
| ✅ | `queries.py`：`login_user` 補 `first_name` / `surname` 拆分 |
| ✅ | `queries.py`：`query_user_profile` 補 `year_of_birth` |
| ✅ | `seed_postgres.py`：`seed_seat_layouts` fare_class 讀 coach 層 |
| ✅ | `seed_postgres.py`：`seed_metro_travels` stops_travelled null → 0 |
| ✅ | `schema.sql`：新增 `metro_schedule_stops` / `national_rail_schedule_stops`，移除 `stops_in_order VARCHAR[]` 及其 GIN index |
| ✅ | `queries.py`：`query_national_rail_availability`、`query_metro_schedules`、`execute_booking` 三處改 JOIN junction table |
| ✅ | **Design Document Section 1**：ER Diagram DSL 已修正（payments 移除錯誤 FK，commit 766b1ef） |
| 🟡 | **`design-document/er-diagram.png`**：重新從 dbdiagram.io 匯出圖片（DSL 已修，舊圖有多餘的 payments→bookings 關係線） |
| ✅ | **Design Document Section 2**：Normalisation Justification（commit 852e2d6） |
| ✅ | **Work Allocation Report**：蔡晟郁部分已填（commit d8d384c），黃蔣需補 Student ID / GitHub / 簽名 |
| 🔴 | **Peer Review**：填寫 `PEER_REVIEW_TEMPLATE.md`（保密，各自填） |
| ✅ | `AI_SESSION_CONTEXT.md`：同步更新中英兩版（graph schema 已改，已確認兩版皆已是最新） |
| ✅ | Policy JSON 擴充：評分標準明確標示 policy_documents 為 scaffold，不需新增條目 |
| ✅ | `databases/graph/seed.cypher`：已確認同步新 schema（MetroStation/NationalRailStation/METRO_LINK/RAIL_LINK/INTERCHANGE_TO） |
| ⭐ BONUS | `schema.sql`：新增 `delay_records` 表（記錄運營方回報的誤點） |
| ⭐ BONUS | `schema.sql`：新增 `season_tickets` 表（捷運週/月/年票） |
| ⭐ BONUS | `schema.sql`：新增 `platform_assignments` 表（各服務月台號） |
| ⭐ BONUS | `schema.sql`：`registered_users` 加 `loyalty_points` 欄位 |
| ⭐ BONUS | `schema.sql`：新增 `disruptions` 表（計劃性停駛工程） |

### 🟢 黃謙儒（Graph DB）

| 優先 | 項目 |
|------|------|
| ✅ | `seed_neo4j.py`：`Station` → `MetroStation` / `NationalRailStation` |
| ✅ | `seed_neo4j.py`：`CONNECTS_TO` → `METRO_LINK`（捷運）/ `RAIL_LINK`（國鐵） |
| ✅ | `seed_neo4j.py`：`INTERCHANGE_WITH` → `INTERCHANGE_TO`；加上 `transfer_time_min=5` 屬性 |
| ✅ | `graph/queries.py`：所有 Cypher 同步更新至新 label / relationship 名稱 |
| ✅ | `query_cheapest_route`：fare_usd / fare_standard_usd / fare_first_usd 寫入邊屬性，Dijkstra 直接使用 |
| ✅ | `query_station_connections`：移除 `r.network`，改用關係型別判斷 |
| ✅ | `query_delay_ripple` — C5 已由 PR #27 修正（`MATCH path =` + `min(length(path))`；文件舊標 🔴 是過時的，**請勿改回 `min(length(shortestPath(...)))`**） |
| ✅ | `query_interchange_path` — C4 已修（`shortestPath(*1..10)` 取代 `*1..20` 全列舉，PR #30） |
| ✅ | `query_alternative_routes` — C3 已修（`WITH` + `RETURN DISTINCT` 去重，PR #30） |
| ✅ | `graph/queries.py`：Driver 模式已定案 **維持 per-call**（Q10 決議） |
| ✅ | `seed_neo4j.py`：`CREATE CONSTRAINT FOR (s:MetroStation) REQUIRE s.station_id IS UNIQUE` 已確認存在 |
| 🔴 | **`skeleton/seed_postgres.py`**：`seed_metro_schedules` / `seed_national_rail_schedules` 移除 `stops_in_order`，改為 insert 到 `metro_schedule_stops` / `national_rail_schedule_stops` — 詳見 Step B（等蔡 PR merge 後才做） |
| 🔴 | **Design Document Section 3**：Graph Database Design Rationale（nodes/relationships/properties 設計理由、Dijkstra vs SQL 論證） |
| 🔴 | **Work Allocation Report**：填寫 `WORK_ALLOCATION_TEMPLATE.md` |
| 🔴 | **Peer Review**：填寫 `PEER_REVIEW_TEMPLATE.md`（保密，各自填） |
| ⭐ BONUS | `graph/queries.py`：新增 `BUS_LINK` 關係類型（公車接駁站點） |
| ⭐ BONUS | `seed_neo4j.py`：節點加 `zone` 屬性（分區票價計算） |
| ⭐ BONUS | GDS 演算法：PageRank 找最重要樞紐站、Louvain 社群偵測找路線集群（需在 docker-compose.yml 啟用 GDS plugin） |

#### 🔴 `query_delay_ripple` 問題詳述

**症狀**：呼叫 `query_delay_ripple('MS07', hops=2)` 回傳空陣列，應有 8 站。

**根因**：Cypher 中 `shortestPath()` 不能放在聚合函式 `min()` 內部：
```cypher
-- 目前（有 bug）
min(length(shortestPath(
    (s)-[:METRO_LINK|RAIL_LINK*]-(affected)
))) AS hops_away
```
Neo4j 在某些 `affected` 等於 `s`（起終點相同）時拋出 `Neo.DatabaseError`，函式的 `except` 靜默吞掉錯誤並回傳 `[]`。

**修法**：在 MATCH 裡命名 path 變數，改用 `min(length(path))`：
```cypher
-- 修正後
MATCH path = (s {station_id: $station_id})
      -[:METRO_LINK|RAIL_LINK*1..{safe_hops}]-
      (affected)
RETURN DISTINCT
    affected.station_id AS station_id,
    affected.name       AS name,
    min(length(path))   AS hops_away,
    affected.lines      AS lines_affected
ORDER BY hops_away
```

---

#### 🔴 `query_interchange_path` 問題詳述

**症狀**：呼叫 `query_interchange_path('MS01', 'NR05')` 超時（>60 秒），直接呼叫 Python function 也無回應。

**根因**：`*1..20` 變長路徑要在全圖搜尋所有長度 ≤ 20 的路徑再過濾，組合數量爆炸（30 個站 × 20 跳）：
```cypher
-- 目前（效能問題）
MATCH p = (o {station_id: $origin_id})
          -[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-
          (d {station_id: $dest_id})
WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
```

**修法**：改用 `shortestPath()` 讓 Neo4j 使用內建最短路徑演算法，上限降為 10：
```cypher
-- 修正後
MATCH p = shortestPath((o {station_id: $origin_id})
          -[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..10]-
          (d {station_id: $dest_id}))
WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
LIMIT 1
```

---

#### 🟡 `query_alternative_routes` 問題詳述

**症狀**：`query_alternative_routes('MS01','MS09', avoid='MS07', max_routes=3)` 回傳 3 條路線但內容完全相同。

**根因**：變長路徑比對會產生多條「節點相同但邊走法不同」的重複路徑，RETURN 時未去重。

**修法**：先用 `WITH` 計算 route 和 total_time_min，再 `RETURN DISTINCT`：
```cypher
-- 修正後
WITH [n IN nodes(p) | {station_id: n.station_id, name: n.name}] AS route,
     reduce(t = 0, r IN relationships(p) | t + r.travel_time_min) AS total_time_min
RETURN DISTINCT route, total_time_min
ORDER BY total_time_min
LIMIT $max_routes
```

### 🟣 蔣耀德（Vector / LLM）

| 優先 | 項目 |
|------|------|
| ✅ | `agent.py`：`search_policy` 接入 `rag.search_with_rerank`，reranker 正式進入 pipeline |
| ✅ | `rag.py` / `reranker.py`：邏輯完整 |
| — | `llm_provider.py`：老師標示不需修改，embed cache 略過 |
| 🟡 | `databases/relational/queries.py`：`query_policy_vector_search` 加入 metadata filtering |
| 🟡 | `config.py` `VECTOR_SIMILARITY_THRESHOLD=0.5` 可能過高，必要時調低至 0.3 |
| 🟡 | **embedding 維度驗證（J2）**：seed 後實際跑 `query_policy_vector_search` 確認有回結果；若切換至 Gemini provider（dim=3072）需同步改 `schema.sql` 的 `vector(768)` 並重新 seed |
| 🔴 | **`skeleton/agent.py` line 329–331**：移除 isinstance string check（蔡改完後 stops 永遠是 list）— 詳見 Step B（等蔡 PR merge 後確認） |
| 🔴 | **Design Document Section 4**：Vector / RAG Design（cosine similarity、RAG pipeline、embedding dimension） |
| 🔴 | **Work Allocation Report**：填寫 `WORK_ALLOCATION_TEMPLATE.md` |
| 🔴 | **Peer Review**：填寫 `PEER_REVIEW_TEMPLATE.md`（保密，各自填） |
| ⭐ BONUS | Policy JSON 新增條目：失物招領政策、團體訂票折扣（10人以上）、無障礙服務、計劃性停駛通知、逃票罰款（補充後重跑 `seed_vectors.py`） |

### 👥 三人共同

| 優先 | 項目 |
|------|------|
| ✅ | **本機環境設定**（Steps 2–12）：蔡已跑通全套，seed 全數成功 |
| 🟡 | **Design Document**：蔡 Sec1+2+5+6 ✅；黃 Sec3 🔴；蔣 Sec4 🔴 |
| 🟡 | **Work Allocation Report**：蔡已填（`WORK_ALLOCATION.md`），黃蔣需補 Student ID / GitHub / 簽名 |
| 🔴 | **Peer Review**：每人各自填 `PEER_REVIEW_TEMPLATE.md`（保密） |
| ✅ | 確認評分 repo（`IM2002-grading-students/`）已在本地，已完整閱讀三份評分細則 |
| ✅ | **C4 `query_interchange_path` 超時 — 已修（PR #30，黃謙儒）** |
| ✅ | **Task 1 Normalisation**：`stops_in_order VARCHAR[]` 已改 junction table（PR #34） |
| ✅ | **STUDENT_GUIDE_CODE / LIVE 狀態欄位**：已於各節更新 |
| ⭐ BONUS | **Task 6 Bonus（+15 × 3 = +45）**：要拿 bonus 必須建立 `TASK6.md`（列所有改動）＋每個改動檔案頭加 `# TASK 6 EXTENSION:` comment ＋ Design Document 加 Section 7，缺 `TASK6.md` 則 bonus 不計分 |
| ⭐ BONUS | `agent.py`：新增額外 tool（如 `get_platform`、`query_disruptions`）並接入 pipeline |
| ⭐ BONUS | `ui.py`：客製化介面（調整 EXAMPLES 列表、版面、顏色主題） |
| ⭐ BONUS | **Unit Test（pytest）**：為三個 DB 層各撰寫測試（蔡：`tests/test_relational.py`、黃：`tests/test_graph.py`、蔣：`tests/test_rag.py`）——程式碼完成後再做 |
| 🟡 | **模組層級 docstring**：程式碼收尾後確認 `databases/relational/queries.py`、`databases/graph/queries.py`、`skeleton/seed_postgres.py`、`skeleton/seed_neo4j.py` 等檔案頭部是否有模組說明 docstring |
| 🟡 | **`config.py` 預設埠**：`PG_PORT=5432`、`NEO4J_URI=bolt://localhost:7687` 與 Docker 映射（5433/7688）不符 → 靠 `.env` 補救，但建議改預設值或加 README 警語，避免新成員忘設 `.env` 時連線失敗 |
| ✅ | **`README.md` 最末行 `hahahahah`**：已刪除（PR #32） |

---

## 二、繳交項目狀態

| 項目 | 方式 | 狀態 |
|------|------|------|
| Code Repository | GitHub repo link → EEClass | ✅ |
| Design Document | Markdown/PDF → EEClass | ❌ 未開始 |
| Work Allocation Report | `WORK_ALLOCATION_TEMPLATE.md` → EEClass | ❌ 未填 |
| Peer Review Report | 每人個別填 → EEClass（保密） | ❌ 未填 |

---

## 三、評分風險（依評分細則更新，2026-06-05）

### 靜態程式碼（/100）

| 項目 | 滿分 | 狀態 | 風險 |
|------|------|------|------|
| Task 1 Table completeness | — | ✅ | ✅ |
| Task 1 PK/FK correctness | — | ✅ | ✅ |
| Task 1 Data types | — | ✅ | ✅ |
| Task 1 Password (bcrypt) | — | ✅ | ✅ |
| Task 1 FK cascade ON DELETE | — | ✅ 已補 | ✅ |
| Task 1 PK design comment | — | ✅ 已補 | ✅ |
| Task 1 Delete strategy comment | — | ✅ 已補 | ✅ |
| **Task 1 Normalisation（junction table）** | — | ✅ 已改（commit 99d206b） | ✅ |
| Task 2 Query functions /30 | 30 | ✅ 15/15 | ✅ |
| Task 3 Seeding /10 | 10 | ✅ | ✅ |
| Task 4 Graph Design /8 | 8 | ✅ 黃已完成 | ✅ |
| Task 5 C1/C2/C3/C5/C6 | 9 | ✅ | ✅ |
| Task 5 C4 interchange path | 1 | ✅ 已修 (PR #30, shortestPath) | ✅ |
| Code Quality /2 | 2 | ✅ WHY comments | ✅ |

### Live Testing（/100）

| 項目 | 滿分 | 狀態 | 風險 |
|------|------|------|------|
| Section A Seeding /15 | 15 | ✅ | ✅ |
| Section B B1–B10 /50 | 50 | ✅ 全過 | ✅ |
| Section C C1/C2/C5/C6 | 20 | ✅ | ✅ |
| Section C C3 duplicate routes | 7 | ✅ 已修 (PR #30, RETURN DISTINCT) | ✅ |
| Section C C4 interchange path | 8 | ✅ 已修 (PR #30) | ✅ |

### Task 6 Bonus 條件（+15 × 3 = +45）

要拿任一 bonus 分，**全部四項**必須齊備：
1. 改動 database code（schema / queries / seed）
2. 每個新函式 / 新表格有詳細 inline comment
3. Design Document 加 **Section 7**
4. repo root 建立 **`TASK6.md`**，且每個改動檔案頭有 `# TASK 6 EXTENSION:` comment

> 缺少 `TASK6.md` 或 per-file comment → bonus 不計分

---

## 四、已修正記錄

| 問題 | 說明 |
|------|------|
| `execute_cancellation` open() 在 try 外 | 移入 try ✅ |
| `register_user` / `update_password` 異常處理 | 改回傳值而非 raise ✅ |
| `execute_booking` 無 seat 可用性驗證 | 加入 NOT IN 子查詢 ✅ |
| `execute_cancellation` 回傳 key `refund_amount_usd` | 改為 `refund_amount` ✅ |
| `query_user_profile` 未含 `year_of_birth` | 補 `date_of_birth.year` ✅ |
| `query_national_rail_availability` 只回傳 `booked_seats` | 補 `available_seats` 子查詢 ✅ |

**已知但不修（學校專題可接受）：**
- `execute_booking` race condition（無 `SELECT FOR UPDATE`）
- 連線風格不統一（read-only 用 `_connect()`，write 用手動連線）

---

## 五、Design Document 寫作參考

### Section 1 — ER Diagram /25
- 關係線上**必須有基數標記**（1:N / M:N），缺少 → 0 分
- 需使用工具繪製（dbdiagram.io、draw.io、Lucidchart）

### Section 2 — Normalisation /20

**bcrypt 必寫三點：**
1. 不需獨立 salt 欄：bcrypt 以 CSPRNG 生成 salt 並嵌入 hash 字串（`$2b$12$<salt><hash>`），`checkpw()` 自動解析
2. salt 每次隨機：確保相同密碼 → 不同 hash，使彩虹表（預算好的密碼↔hash 對照表）無效
3. bcrypt 優於 MD5/SHA-1：前者有 cost factor（可調計算成本），後者設計目標是「快速」，暴力破解成本低

**其他設計決策（各選一個說明 functional dependency）：**
- soft delete 選擇：`is_active` 保留 `bookings`/`payments` FK 完整性；hard delete 會破壞歷史訂單
- available seats 動態計算：不建 occupancy table，避免與 bookings 不同步的一致性問題；RAG table 同理不嚴格正規化（寫少讀多，整批 chunk 更新）
- 年份資料最小化：只存 `year_of_birth`，避免收集系統不需要的月日個資

### Section 3 — Graph Rationale /25
- 說明 nodes / relationships / properties 各自的選型理由（不能只說「站是物件所以是 node」）
- **具體演算法論證**：Dijkstra on graph vs SQL recursive CTE（必寫，泛泛說「graph 比較快」只得 20% 分數）
- 說明兩種 query 類型（如 shortest path + delay ripple）及 graph model 如何讓它們可表達
- node identity：用什麼 property 做唯一識別（`station_id`）及為何
- interchange `travel_time_min = 5` 是自訂合理值（規格未指定，教授確認可自訂）

### Section 4 — Vector / RAG /15
- cosine similarity 為何適合：magnitude-independent，度量向量方向相似性
- 完整 RAG pipeline 四階段：query embedding → similarity search → retrieved docs → LLM prompt → answer
- embedding dimension：768（Ollama nomic-embed-text）/ 3072（Gemini）；換 provider 後果：dimension mismatch → index 失效，必須重新 seed
- 兩層正規化：DB 層（chunk + embedding）+ pipeline 層（`_normalise_result()` 將 JSON 轉結構文字給 1b 模型）

### Section 5 — AI Tool Usage /10
- 需 3–5 例，每例必須有 **Context + Prompt + Outcome** 三欄（缺任一欄扣分）
- **至少一例描述 AI 輸出錯誤** + 如何識別 + 如何修正（可用 Old Town station 語意歧義 → 呼叫錯誤 tool → 改題目描述解決）

### Section 6 — Reflection /5
**設計決策（列兩個）：**
- soft delete vs hard delete（理由：FK 完整性 + 法規保留義務）
- 只存 year_of_birth（理由：資料最小化，系統無使用月日的功能）
- 不建 occupancy table（理由：一致性優先於效能，未來可加 index 或 Redis）

**生產環境差異（列一個）：**
- 個資刪除請求應採兩階段：PII 欄位去識別化（null/匿名），但 `bookings`/`payments` 依稅務/會計法規保留

---

## 六、Live Testing 注意事項

**TA 有額外測試題，範例題只是基礎**（教授明確說明）。

**範例題 Q4 陷阱**：`If Old Town station (NR03) is closed...` → llama3.2:1b 把 "Old Town" 對應 MS07 而非 NR03，呼叫 `query_interchange_path` 而非 `query_alternative_routes`。
- 自測時改成：`If Old Town junction (NR03) is closed...` 可正確觸發
- 教授立場：**不建議針對範例題調 agent.py prompt**（不計分 + 影響泛化能力）
- 應對方式：自訂內部測試題組，覆蓋各 query function

---

## 七、本機環境設定步驟

| # | 步驟 | 狀態 |
|---|------|------|
| 1 | Clone repo | ✅ |
| 2 | `python3 -m venv .venv` | ✅ |
| 3 | `source .venv/bin/activate` | ✅ |
| 4 | `pip install -r requirements.txt` | ✅ |
| 5 | 複製 `.env.example` → `.env`；port 衝突時**只改 `.env`，不動 `config.py`** | ✅ |
| 6 | `docker compose up -d` | ✅ |
| 7 | `docker compose ps`（確認 healthy） | ✅ |
| 8 | `python3 skeleton/seed_postgres.py` | ✅ |
| 9 | `ollama serve`（先確認 server 跑起來）→ `ollama pull llama3.2:1b` + `nomic-embed-text` | ✅ 需用官方安裝（非 Homebrew） |
| 10 | `python3 skeleton/seed_vectors.py` | ✅ 101 chunks |
| 11 | `python3 skeleton/seed_neo4j.py` | ✅ 20站、66條邊 |
| 12 | `python3 skeleton/ui.py` | ✅ |
