# Post-Sync Review — TransitFlow 整合檢查

> 更新：2026-06-07 | 範圍：PR #35 #36 #38 #39 全部合併完畢

---

## 本次工作紀錄（蔡晟郁，2026-06-05–06）

### 修正的 bug（蔡的檔案）

| 檔案 | 問題 | 影響 |
|------|------|------|
| `seed_postgres.py` | `seed_seat_layouts`：`fare_class` 從 `seat` 層讀，應從 `coach` 層讀 → PG seeding rollback | 所有 B 系列 live testing 全部失敗 |
| `seed_postgres.py` | `seed_metro_travels`：`stops_travelled` 有 null，schema 設 `NOT NULL` | seeding IntegrityError |
| `queries.py` | `login_user`：未拆分 `full_name` → `first_name` / `surname` | 登入功能 KeyError crash |
| `queries.py` | `query_user_profile`：未回傳 `year_of_birth` | B6 評分失分 |
| `schema.sql` | HNSW index 缺少名稱，PostgreSQL syntax error | 向量搜尋退化成 seq scan |

### UI 測試觀察（llama3.2:1b 行為）

- 模型頻繁選錯 tool，有時直接幻覺，不看資料庫
- **所有 tool 的回傳資料本身都正確**，問題出在 LLM 選 tool 的邏輯
- TA 若直接呼叫 Python function 測試，所有正確的函式都會通過

---

## 一、行動清單

### 🔵 蔡晟郁（Relational DB）— 全部完成

| 狀態 | 項目 |
|------|------|
| ✅ | `schema.sql`：所有 FK 加 `ON DELETE`（RESTRICT / SET NULL / CASCADE） |
| ✅ | `schema.sql`：PK 設計說明 comment + soft delete comment |
| ✅ | `schema.sql`：HNSW index 補上名稱（語法修正） |
| ✅ | `schema.sql`：新增 `metro_schedule_stops` / `national_rail_schedule_stops`，移除 `stops_in_order VARCHAR[]` |
| ✅ | `queries.py`：5 個函式加 inline WHY comment |
| ✅ | `queries.py`：`login_user` 補 `first_name` / `surname` 拆分 |
| ✅ | `queries.py`：`query_user_profile` 補 `year_of_birth` |
| ✅ | `queries.py`：`query_national_rail_availability`、`query_metro_schedules`、`execute_booking` 改 JOIN junction table |
| ✅ | `seed_postgres.py`：`seed_seat_layouts` fare_class 讀 coach 層 |
| ✅ | `seed_postgres.py`：`seed_metro_travels` stops_travelled null → 0 |
| ✅ | Design Document Section 1：ER Diagram DSL 修正（payments 移除錯誤 FK）+ PNG/PDF 嵌入 |
| ✅ | Design Document Section 1.2：Entity 表格修正（junction table 補入，payments FK 說明） |
| ✅ | Design Document Section 2：Normalisation Justification 完整撰寫 |
| ✅ | Design Document Section 5+6：AI Usage + Reflection 完整 |
| ✅ | `WORK_ALLOCATION.md`：蔡晟郁部分已填（Student ID / GitHub / email / 簽名） |
| 🔴 | **Peer Review**：填寫 `PEER_REVIEW_TEMPLATE.md`（保密，各自填） |

---

### 🟢 黃謙儒（Graph DB）

| 狀態 | 項目 |
|------|------|
| ✅ | `seed_neo4j.py`：MetroStation / NationalRailStation / METRO_LINK / RAIL_LINK / INTERCHANGE_TO（雙向）完成 |
| ✅ | `graph/queries.py`：所有 Cypher 同步新 label / relationship 名稱 |
| ✅ | `query_cheapest_route`：fare_standard_usd / fare_first_usd / fare_usd 三分支，Dijkstra 直接使用 |
| ✅ | `query_delay_ripple`：C5 已修（`MATCH path =` + `min(length(path))`） |
| ✅ | `query_interchange_path`：C4 已修（`shortestPath(*1..10)`，PR #30） |
| ✅ | `query_alternative_routes`：C3 已修（`WITH` + `RETURN DISTINCT` 去重，PR #30） |
| 🟡 | **`query_delay_ripple` hops 無上限**：`safe_hops = max(0, int(hops))` → 改為 `max(1, min(int(hops), 10))` |
| ✅ | **`skeleton/seed_postgres.py`**：junction table insert 完成（PR #38） |
| ✅ | **Design Document Section 3**：完整撰寫，含 Dijkstra 論證 + 兩種查詢 + node identity（PR #39） |
| 🔴 | **`WORK_ALLOCATION.md`**：補上 Student ID、email、簽名（GitHub Churrios 已填） |
| 🔴 | **Peer Review**：填寫 `PEER_REVIEW_TEMPLATE.md`（保密，各自填） |

---

### 🟣 蔣耀德（Vector / LLM）

| 狀態 | 項目 |
|------|------|
| ✅ | `agent.py`：`search_policy` 接入 `rag.search_with_rerank` |
| ✅ | `rag.py` / `reranker.py`：邏輯完整 |
| ✅ | `agent.py` line 329–331：isinstance string check 已移除（PR #36） |
| ✅ | **Design Document Section 4**：完整撰寫，含 4.1 policy documents 說明（PR #36） |
| 🟡 | `config.py` `VECTOR_SIMILARITY_THRESHOLD=0.5` 可能過高，必要時調低至 0.3 |
| 🟡 | **embedding 維度驗證（J2）**：seed 後實際跑 `query_policy_vector_search` 確認有回結果 |
| 🔴 | **`skeleton/agent.py`：`query_station_connections` 未接入**：函式存在於 `databases/graph/queries.py:403` 但未 import、未加入 TOOLS list、未加入 TOOLS_SCHEMA、未加入 `_execute_tool` → C6 透過 chatbot 完全不可觸發。需補：1) import，2) tool 定義，3) TOOLS_SCHEMA，4) `_execute_tool` handler |
| 🔴 | **`WORK_ALLOCATION.md`**：補上 Student ID、GitHub username、email、簽名（全部空白） |
| 🔴 | **Peer Review**：填寫 `PEER_REVIEW_TEMPLATE.md`（保密，各自填） |

---

### 👥 三人共同

| 狀態 | 項目 |
|------|------|
| ✅ | 本機環境全套跑通（seed PG / vectors / Neo4j 均無 traceback） |
| ✅ | Task 1 Normalisation：junction table 完成（PR #34） |
| ✅ | 評分細則三份已完整閱讀 |
| ✅ | **Design Document**：全部六節完成（蔡 Sec1+2+5+6，黃 Sec3，蔣 Sec4）|
| 🟡 | **Work Allocation Report**：蔡已填；黃蔣需補 |
| 🔴 | **Peer Review**：三人各自填，保密 |
| ⭐ | **Unit Test（pytest）**：目前完全沒有，課堂筆記明確要求 |

---

## 二、繳交項目狀態

| 項目 | 狀態 |
|------|------|
| Code Repository | ✅ |
| Design Document | ✅ 全部六節完成 |
| Work Allocation Report | 🟡 蔡已填；黃缺 Student ID / email / 簽名；蔣全部空白 |
| Peer Review Report | 🔴 三人均未填 |

---

## 三、評分風險

### 靜態程式碼（/100）

| 項目 | 狀態 |
|------|------|
| Task 1 Schema 完整性 / PK / FK / 資料型別 | ✅ |
| Task 1 bcrypt 密碼 | ✅ |
| Task 1 FK ON DELETE | ✅ |
| Task 1 PK comment / soft delete comment | ✅ |
| Task 1 Normalisation（junction table） | ✅ PR #34 |
| Task 2 Query functions 15/15 | ✅ |
| Task 3 Seeding | ✅ |
| Task 4 Graph Design | ✅ |
| Task 5 C1–C5 graph queries | ✅ |
| Task 5 C6 `query_station_connections` | ⚠️ 函式正確但 agent 未接入 |
| Code Quality（WHY comments / docstring） | ✅ |

### Live Testing（/100）

| 項目 | 滿分 | 狀態 |
|------|------|------|
| Section A Seeding | /15 | ✅ |
| Section B B1–B10 | /50 | ✅ 全過 |
| Section C C1/C2/C5 | /15 | ✅ |
| Section C C3 duplicate routes | /7 | ✅ PR #30 |
| Section C C4 interchange path | /8 | ✅ PR #30 |
| Section C C6 station connections | /5 | 🔴 chatbot 不可觸發（蔣需補 agent.py） |

---

## 四、已知不修（學校專題可接受）

- `execute_booking` race condition（無 `SELECT FOR UPDATE`）
- 連線風格不統一（read-only 用 `_connect()`，write 用手動連線）
- 密碼強度驗證、登入失敗次數限制
- `.env` 存 credentials（非 secrets manager）

---

## 五、本機環境設定

| # | 步驟 | 狀態 |
|---|------|------|
| 1 | Clone repo | ✅ |
| 2 | `python3 -m venv .venv && source .venv/bin/activate` | ✅ |
| 3 | `pip install -r requirements.txt` | ✅ |
| 4 | 複製 `.env.example` → `.env`；port 衝突只改 `.env`，不動 `config.py` | ✅ |
| 5 | `docker compose up -d` | ✅ |
| 6 | `python3 skeleton/seed_postgres.py` | ✅ |
| 7 | `ollama serve` → `ollama pull llama3.2:1b` + `nomic-embed-text` | ✅ 需官方安裝（非 Homebrew） |
| 8 | `python3 skeleton/seed_vectors.py` | ✅ 101 chunks |
| 9 | `python3 skeleton/seed_neo4j.py` | ✅ 20站、66條邊 |
| 10 | `python3 skeleton/ui.py` | ✅ |

---

## 六、Live Testing 注意事項

**TA 有額外測試題，範例題只是基礎。**

**Q4 陷阱**：`If Old Town station (NR03) is closed...` → llama3.2:1b 把 "Old Town" 對應 MS07 而非 NR03，呼叫錯誤 tool。改成 `If Old Town junction (NR03) is closed...` 可正確觸發。老師立場：不建議針對範例題調 prompt（不計分 + 影響泛化能力）。

---

## 七、Task 6 Bonus 條件（+15 × 3 = +45）

要拿任一 bonus，**全部四項**必須齊備：
1. 改動 database code（schema / queries / seed）
2. 每個新函式 / 新表格有詳細 inline comment
3. Design Document 加 Section 7
4. repo root 建立 `TASK6.md`，且每個改動檔案頭有 `# TASK 6 EXTENSION:` comment

> 缺少 `TASK6.md` → bonus 不計分
