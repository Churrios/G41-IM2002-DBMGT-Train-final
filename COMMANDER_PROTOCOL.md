# COMMANDER PROTOCOL — TransitFlow 總架構師指揮手冊

> **受眾：** 蔡晟郁（總架構師 AI）使用本文件向黃組員 AI 與蔣組員 AI 下達指令。
> **原則：** 每一條指令都必須讓收令 AI 在沒有歷史對話的情況下，獨立完成任務並產出可直接 merge 的 code。

---

## 一、指揮架構總覽

```
                    ┌─────────────────────────────────┐
                    │   總架構師 AI（蔡晟郁）          │
                    │   - 制定 Schema Contract         │
                    │   - 指派任務、審核 PR             │
                    │   - 維護 AI_SESSION_CONTEXT.md   │
                    └────────────┬────────────────────┘
                                 │  下達指揮 Prompt
               ┌─────────────────┼─────────────────────┐
               ▼                                       ▼
   ┌───────────────────────┐             ┌───────────────────────┐
   │  黃組員 AI（工程師 A） │             │  蔣組員 AI（工程師 B） │
   │  - Relational Queries │             │  - Graph Queries       │
   │  - Seed PostgreSQL    │             │  - Seed Neo4j          │
   └───────────────────────┘             └───────────────────────┘
```

---

## 二、每一條指揮 Prompt 的必備區塊

每次下達任務，Prompt **必須包含以下六個區塊**，順序固定：

```
[BLOCK 1] COMMANDER CONTEXT     — 誰在指揮、專案是什麼
[BLOCK 2] SCHEMA CONTRACT       — 絕對不可偏離的資料庫設計
[BLOCK 3] AGENT ROLE            — 收令者的身分與限制
[BLOCK 4] VERSION MANAGEMENT    — Git 操作規範（每次必含）
[BLOCK 5] TASK SPECIFICATION    — 精確的任務交付規格
[BLOCK 6] RESPONSE FORMAT       — 回覆格式（供總架構師審核）
```

---

## 三、六大區塊完整範本

### BLOCK 1 — COMMANDER CONTEXT（固定貼上，每次不變）

```
═══════════════════════════════════════════════════════
COMMANDER CONTEXT
═══════════════════════════════════════════════════════
Project   : TransitFlow — 雙網路大眾運輸訂票系統（學術專案）
Stack     : PostgreSQL 16 · Neo4j 5 · pgvector · Python 3.12
Repo      : Churrios/G41-IM2002-DBMGT-Train-final (private fork)
Main branch: main（受保護，所有 work 須以 feature branch + PR 進入）

團隊：
  - 蔡晟郁（總架構師）— 負責 schema 最終決策、PR 審核、指揮
  - 黃組員（工程師 A）— Relational queries + seed_postgres.py
  - 蔣組員（工程師 B）— Graph queries + seed_neo4j.py

Schema-First 規則（不可破）：
  schema.sql 已鎖定於 main branch。
  任何 query function 只能引用 schema.sql 中已定義的
  table name 與 column name，禁止自行發明。
═══════════════════════════════════════════════════════
```

---

### BLOCK 2 — SCHEMA CONTRACT（每次貼上當前 schema.sql 完整內容）

```
═══════════════════════════════════════════════════════
SCHEMA CONTRACT（單一事實來源 — 不可修改）
═══════════════════════════════════════════════════════
[在此處完整貼上 databases/relational/schema.sql 的內容]

Graph Schema（Neo4j 已同意）：
  Node Labels  : Station {station_id, name, network: 'metro'|'national_rail'}
  Relationships:
    (Station)-[:CONNECTS_TO {line, travel_time_min}]->(Station)
    (Station)-[:INTERCHANGE_WITH {}]->(Station)
═══════════════════════════════════════════════════════
```

---

### BLOCK 3 — AGENT ROLE（依收令者調整）

**給黃組員 AI（工程師 A）：**
```
═══════════════════════════════════════════════════════
YOUR ROLE — 工程師 A（Relational 負責人）
═══════════════════════════════════════════════════════
你的職責範圍：
  - databases/relational/queries.py  ← 唯一可修改的主要檔案
  - skeleton/seed_postgres.py        ← 如本次任務包含 seeding

禁止觸碰：
  - databases/relational/schema.sql  （已鎖定，唯讀）
  - databases/graph/queries.py       （蔣組員負責）
  - skeleton/seed_neo4j.py           （蔣組員負責）

Coding 規範：
  - 所有 DB 連線使用模組內已定義的 _connect() helper
  - 所有查詢使用 psycopg2.extras.RealDictCursor
  - 回傳型別嚴格遵照 stub docstring（list[dict] / dict / None）
  - 無結果時回傳 [] 而非 None
  - 所有 user input 以 %s 參數化，禁止字串拼接 SQL
  - 每個函式開頭必須有 one-line docstring（保留原有的即可）
  - 密碼儲存前必須使用 bcrypt hash（不可明文）
═══════════════════════════════════════════════════════
```

**給蔣組員 AI（工程師 B）：**
```
═══════════════════════════════════════════════════════
YOUR ROLE — 工程師 B（Graph 負責人）
═══════════════════════════════════════════════════════
你的職責範圍：
  - databases/graph/queries.py       ← 唯一可修改的主要檔案
  - skeleton/seed_neo4j.py           ← 如本次任務包含 seeding

禁止觸碰：
  - databases/relational/schema.sql  （已鎖定，唯讀）
  - databases/relational/queries.py  （黃組員負責）
  - skeleton/seed_postgres.py        （黃組員負責）

Coding 規範：
  - 所有 Neo4j 連線使用模組內已定義的 _driver() helper
  - 所有查詢使用 with driver.session() as session: 模式
  - Cypher 中 Node label 嚴格使用 Station（不可用 Stop、Node 等）
  - Relationship type 嚴格使用 CONNECTS_TO 與 INTERCHANGE_WITH
  - 回傳型別嚴格遵照 stub docstring（list[dict] / dict / None）
  - 無結果時回傳 [] 而非 None
  - 所有 Cypher 參數使用 $param 語法，禁止字串拼接
═══════════════════════════════════════════════════════
```

---

### BLOCK 4 — VERSION MANAGEMENT（每次必含，不可省略）

```
═══════════════════════════════════════════════════════
VERSION MANAGEMENT PROTOCOL（強制執行）
═══════════════════════════════════════════════════════

▌ 開始工作前
  1. git checkout main
  2. git pull origin main
  3. git checkout -b feature/<你的名字>/<任務簡述>
     Branch 命名範例：
       feature/huang/query-metro-schedules
       feature/chiang/seed-neo4j-stations
       feature/huang/query-national-rail-fare

▌ 工作中（分批 commit，嚴禁一次 commit 全部）
  規則：一個函式完成並測試通過 → 立即 commit
  格式（imperative, 50字以內主旨）：
    git add databases/relational/queries.py
    git commit -m "Implement query_metro_schedules - stops array order check"

  ✓ 正確示範：
    "Implement query_metro_fare - base + per_stop calculation"
    "Add seed_postgres stations block - 20 metro + 10 NR stations"
    "Fix query_available_seats - exclude cancelled bookings"

  ✗ 禁止寫法：
    "done"  /  "update"  /  "fix bug"  /  "WIP"
    一個 commit 包含多個不相干函式

▌ 完成任務後
  git push origin feature/<你的名字>/<任務簡述>

▌ 回報給總架構師時，必須附上：
  - 所在 branch 名稱
  - 每個 commit 的 message（依序列出）
  - 尚未 push 的 local changes（如有）

▌ 不要做的事（禁止）：
  - 直接 push 到 main
  - --force push 任何 branch
  - 修改已 merge 的 commit（--amend published commits）
  - 在沒有告知總架構師的情況下更改 schema.sql
═══════════════════════════════════════════════════════
```

---

### BLOCK 5 — TASK SPECIFICATION（每次依任務填寫）

**格式模板：**
```
═══════════════════════════════════════════════════════
TASK SPECIFICATION
═══════════════════════════════════════════════════════
任務類型：[Q=Query實作 / S=Seed腳本 / T=測試 / D=除錯 / R=Review]
優先級  ：[HIGH / MEDIUM / LOW]
截止依據：本次 session 結束前完成

─── 交付物清單 ───────────────────────────────────────
[逐條列出需要完成的函式或功能，一條一個]

例：
  □ query_metro_schedules(origin_id, destination_id)
  □ query_metro_fare(origin_id, destination_id, ticket_type)
  □ 對應的 pytest unit test

─── 相關 Stub 簽名 ──────────────────────────────────
[貼上需要實作的 stub function 原文，包含完整 docstring]

─── 相關 Mock Data 片段 ─────────────────────────────
[貼上 2–3 筆最具代表性的 JSON 資料，幫助 AI 理解資料樣貌]

─── 已知限制與邊緣案例 ──────────────────────────────
[列出需要特別處理的情境]

例：
  - day_pass 票種的 stops_travelled 可能為 null
  - cancelled 狀態的 booking 的 travelled_at 為 null
  - payments.booking_id 同時參照 BK_ 和 MT_ 前綴（無 FK constraint）
  - 查詢不存在的 station pair 應回傳 [] 而非 raise exception
═══════════════════════════════════════════════════════
```

---

### BLOCK 6 — RESPONSE FORMAT（規範收令 AI 的回覆結構）

```
═══════════════════════════════════════════════════════
REQUIRED RESPONSE FORMAT
═══════════════════════════════════════════════════════
請按以下格式回覆，讓總架構師可以快速審核：

## ✅ 完成項目
- [ 函式名稱 ]：一句話說明實作邏輯

## 📋 Git 狀態
Branch: feature/___/___
Commits:
  1. [commit message]
  2. [commit message]

## 💻 程式碼
[貼上完整實作，不要省略任何部分]

## 🧪 測試方式
[提供可直接在 Python shell 執行的測試指令]
期望輸出：[具體說明期望的 return value 樣貌]

## ⚠️ 需要總架構師確認的問題
[列出任何不確定的設計決策，或需要跨組員協調的事項]
如無問題，寫「無」。

## 🔲 未完成項目（如有）
[列出本次未能完成的 stub，說明原因]
═══════════════════════════════════════════════════════
```

---

## 四、任務類型快速組合模板

### 類型 Q — Query Function 實作

> **使用時機：** 指派實作 `queries.py` 中的 stub function

**額外加入 BLOCK 5 的內容：**
```
任務類型：Q — Query Function 實作
相關表格：[列出會用到的 table name]
SQL 方向提示：[如有特定技術要求，例如 array_position()、JSONB 運算等]
接受標準：
  - 對 seed data 中存在的合法輸入，回傳非空 list
  - 對不存在的輸入，回傳 []（不 raise exception）
  - 通過 Template C Code Review checklist 的所有項目
```

---

### 類型 S — Seed 腳本

> **使用時機：** 指派實作 `seed_postgres.py` 或 `seed_neo4j.py`

**額外加入 BLOCK 5 的內容：**
```
任務類型：S — Seed 腳本
資料來源：train-mock-data/ 目錄下的 JSON 檔案
插入順序限制（因外鍵依賴）：
  PostgreSQL 插入順序：
    1. registered_users
    2. metro_stations（先不含 interchange_nr FK）
    3. national_rail_stations
    4. 更新 metro_stations.interchange_nr_station_id
    5. metro_schedules
    6. national_rail_schedules
    7. seat_layouts
    8. bookings
    9. metro_travel_history
   10. payments

  Neo4j 插入順序：
    1. CREATE Station nodes (metro)
    2. CREATE Station nodes (national rail)
    3. CREATE CONNECTS_TO relationships
    4. CREATE INTERCHANGE_WITH relationships

密碼處理：registered_users 的 password 欄位插入前必須 bcrypt hash
冪等性要求：腳本重複執行不應失敗（使用 ON CONFLICT DO NOTHING 或 MERGE）
```

---

### 類型 T — Unit Test

> **使用時機：** 指派撰寫 pytest 測試

**額外加入 BLOCK 5 的內容：**
```
任務類型：T — Unit Test（使用 pytest）
測試原則：
  - 測試行為，不測實作細節
  - 每個 test function 只測一件事
  - 使用真實資料庫連線（不 mock DB），因此需要 Docker 正在執行
  - 測試檔案放置：tests/test_relational_queries.py 或 tests/test_graph_queries.py
  - 測試命名：test_<function_name>_<scenario>
    例：test_query_metro_schedules_valid_route
        test_query_metro_schedules_no_route_returns_empty
        test_query_metro_fare_single_ticket
        test_query_metro_fare_day_pass

必測情境（每個函式至少）：
  1. happy path（正常輸入）
  2. empty result（查詢不存在的資料）
  3. edge case（如 null 欄位、cancelled 狀態）
```

---

### 類型 D — 除錯

> **使用時機：** 收到組員的 error traceback

**額外加入 BLOCK 5 的內容：**
```
任務類型：D — 除錯
Error Traceback：
[貼上完整 traceback]

問題函式原始碼：
[貼上程式碼]

已嘗試的修法（如有）：
[說明]

要求：
  - 找出根本原因，不要只改 symptom
  - 不可更改 schema.sql、function signature、return type
  - 修正後說明為什麼會出錯
```

---

## 五、跨組員協調規則

### 當黃組員需要蔣組員提供的資料時

黃組員實作 `query_national_rail_availability` 前，總架構師確認：
- Neo4j 的 `CONNECTS_TO` relationship 已被蔣組員 seed 進資料庫
- 或改為只依賴 PostgreSQL 的 `national_rail_schedules.stops_in_order`

### 共享 station_id 命名空間

- Metro stations：`MS01`–`MS20`（VARCHAR(10)）
- National rail stations：`NR01`–`NR10`（VARCHAR(10)）
- 這個命名空間被兩位組員的程式碼共同引用，不可單方面更改

### AI_SESSION_CONTEXT.md 更新責任

| 事件 | 誰更新 |
|------|--------|
| Schema 變更 | 總架構師（蔡晟郁）|
| Architectural decision（SQL 做法選定）| 執行該任務的組員|
| PR merge 後 | 提 PR 的組員 |

---

## 六、品質門檻（PR 開前必須全部打勾）

每位組員的 AI 在回覆總架構師前，需自行對照此清單：

```
Relational Queries 品質門檻
  □ 所有 table/column name 與 schema.sql 完全一致
  □ 使用 _connect() + RealDictCursor
  □ 無結果回傳 [] 而非 None
  □ 所有 user input 用 %s 參數化
  □ 密碼處理：有涉及密碼的函式使用 bcrypt
  □ 每個函式有 one-line docstring
  □ 分批 commit（一函式一 commit）
  □ Branch 命名符合規範

Graph Queries 品質門檻
  □ Node label 使用 Station（不是其他名稱）
  □ Relationship type 使用 CONNECTS_TO / INTERCHANGE_WITH
  □ 使用 _driver() + with session: 模式
  □ Cypher 參數使用 $param 語法
  □ 無結果回傳 [] 而非 None
  □ 每個函式有 one-line docstring
  □ 分批 commit（一函式一 commit）
  □ Branch 命名符合規範

共通品質門檻
  □ 沒有 print 除錯殘留（或只在 __main__ 區塊）
  □ 沒有 hardcoded credentials
  □ 沒有更動 schema.sql 或對方負責的檔案
```

---

## 七、進度追蹤格式（總架構師專用）

每次收到組員 AI 回覆後，更新此表格並貼回新一輪指揮 prompt：

```
═══════════════════════════════════════════════════════
PROGRESS BOARD（由總架構師維護）
═══════════════════════════════════════════════════════
Schema     ：[x] relational  [ ] graph
Seed       ：[ ] seed_postgres.py  [ ] seed_neo4j.py

Relational Queries（黃組員）：
  [ ] query_national_rail_availability
  [ ] query_national_rail_fare
  [ ] query_metro_schedules
  [ ] query_metro_fare
  [ ] query_available_seats
  [ ] query_user_profile
  [ ] query_user_bookings
  [ ] query_payment_info
  [ ] execute_booking
  [ ] execute_cancellation
  [ ] register_user
  [ ] login_user

Graph Queries（蔣組員）：
  [ ] query_shortest_route
  [ ] query_station_connections
  [ ] query_interchange_stations
  [ ] query_route_between_networks

Unit Tests：
  [ ] test_relational_queries.py
  [ ] test_graph_queries.py

Last updated：[日期]
═══════════════════════════════════════════════════════
```

---

## 八、指揮黃金法則

1. **永遠先給 Schema Contract** — AI 沒看到 schema 就會亂編 table name
2. **Version Management 每次必含** — 不要假設組員 AI 記得上次說過的 git 規範
3. **一次一任務** — 不要在同一條 prompt 指派超過 3 個函式，品質會下降
4. **明確邊緣案例** — cancelled 的 null、day_pass 的 0 amount、polymorphic FK 這些不說就會出錯
5. **要求 Response Format** — 沒有格式要求，組員 AI 的回覆就無法快速審核
6. **PR 前先 code review** — 在 prompt 中要求組員 AI 先自行對照品質門檻，減少來回次數

---

*文件維護者：蔡晟郁（總架構師）*
*最後更新：2026-05-28*
