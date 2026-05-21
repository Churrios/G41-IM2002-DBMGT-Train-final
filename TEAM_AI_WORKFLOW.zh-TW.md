# Team AI Workflow Guide — TransitFlow

這是一份實用指南，給三位學生一起使用任何 AI coding assistant（Claude Code、GitHub Copilot、Cursor、Gemini Code Assist 等）協作開發 TransitFlow。

**在寫任何一行程式碼前，請先讀這份文件。**

---

## 目錄

- [Part 0：任何人寫程式前 — Schema-First 規則](#part-0任何人寫程式前--schema-first-規則)
- [Part 1：使用 AI 的團隊協作](#part-1使用-ai-的團隊協作)
- [Part 2：AI 整合工作流程循環](#part-2ai-整合工作流程循環)
- [Part 3：小型可運作範例](#part-3小型可運作範例)
- [Part 4：有效的 Prompts](#part-4有效的-prompts)
- [Appendix：Session 前檢查清單](#appendixsession-前檢查清單)

---

## Part 0：任何人寫程式前 — Schema-First 規則

> **關鍵：** `databases/relational/queries.py` 與 `databases/graph/queries.py` 中的每個 query function 都會對你的資料庫執行 SQL 或 Cypher。那些 SQL 會引用由**你們**設計的 table names 與 column names。如果某人的 AI 產生 `SELECT * FROM stations`，另一人的 AI 產生 `SELECT * FROM metro_stations`，整個系統就無法一起運作。
>
> **規則：在任何人實作任何 query function 前，團隊必須先共同同意 `databases/relational/schema.sql`。**

### Step 0.1 — 一起進行 Schema Design Workshop

在分工前，團隊一起做一次。大約需要 90 分鐘。

**準備工作（每個人在會議前）：**
1. 閱讀 `train-mock-data/metro_stations.json` 與 `train-mock-data/bookings.json`
2. 閱讀 `databases/relational/queries.py` 中的 stub function signatures。函式名稱與 docstrings 會明確告訴你 queries 需要回傳哪些資料
3. 快速瀏覽 `train-mock-data/national_rail_schedules.json`、`train-mock-data/registered_users.json`、`train-mock-data/payments.json`

**Workshop 中：**
1. 每個人問自己的 AI assistant：*"Given this JSON data [paste 10–20 lines], what SQL tables would you design?"*
2. 團隊一起比較三份 AI 輸出。它們會不一樣
3. 一起討論並決定（AI 提出選項，人類做決策）
4. 把同意好的 schema 寫進 `databases/relational/schema.sql`

Part 3 的 [Example 1](#example-1schema-design-workshop) 有具體 walkthrough。

### Step 0.2 — Commit 並鎖定 Schema

團隊同意 schema 後，由一個人 commit：

```bash
git checkout -b feature/schema-design
git add databases/relational/schema.sql
git commit -m "Add agreed relational schema - team reviewed"
```

開 Pull Request，讓三位隊友都 approve 後再 merge 到 main。Merge 後，**不要在沒有通知全隊的情況下改 table 或 column 名稱**，這會破壞其他人的 queries。

### Step 0.3 — Graph Schema 也要做同樣的事

`databases/graph/queries.py` 中的 graph queries（例如 `query_shortest_route`、`query_station_connections`）需要 Neo4j node/relationship schema。請讀 `train-mock-data/metro_stations.json` 與 `train-mock-data/national_rail_stations.json`，並在實作 graph queries 前，團隊一起決定 node labels（`Station`、`MetroStation` 等）與 relationship types（`CONNECTS_TO`、`INTERCHANGE` 等）。

---

## Part 1：使用 AI 的團隊協作

### 1.1 — 誰負責什麼

用以下分工當起點，依你們團隊情況調整。

| 區域 | 要實作的檔案 | 共享相依項目 |
|---|---|---|
| Relational schema | `databases/relational/schema.sql` | **全隊一起同意** |
| Relational queries | `databases/relational/queries.py` | Schema 必須先 finalized |
| Graph schema + queries | `databases/graph/queries.py` | 來自 relational schema 的 station IDs |
| Seeding & testing | `skeleton/seed_postgres.py`, `skeleton/seed_neo4j.py` | 兩種 schemas |

**記錄你們的分工。** 在專案根目錄建立 `TEAM.md`：

```markdown
# Team Assignments

| Name  | Primary responsibility                          |
|-------|-------------------------------------------------|
| Alice | Relational schema + relational query functions  |
| Bob   | Graph schema + graph query functions            |
| Carol | Seeding scripts + integration testing           |
```

### 1.2 — Git 基礎（逐步操作）

如果你不熟 Git，每次開始工作時都照這個模式做：

**一次性設定：**
```bash
# Clone shared repo（只做一次）
git clone <your-repo-url>
cd transitflow-demo
```

**每次開始工作 session：**
```bash
# 1. 確認你有隊友的最新程式碼
git checkout main
git pull origin main

# 2. 為你接下來要做的事建立 branch
git checkout -b feature/alice/metro-schedules-query
```

**工作中：**
```bash
# 經常儲存進度
git add databases/relational/queries.py
git commit -m "Implement query_metro_schedules - returns schedules by origin/destination"
```

**完成一個 feature 時：**
```bash
# Push branch 到 GitHub
git push origin feature/alice/metro-schedules-query
# 接著在 GitHub 開 Pull Request，並請隊友 review
```

**Branch naming convention：** `feature/<your-name>/<what-youre-doing>`

範例：
- `feature/alice/relational-schema`
- `feature/bob/graph-shortest-route`
- `feature/carol/seed-postgres`

### 1.3 — 共享 AI Context File

> **這是你們能做的、對一致性影響最大的事情。**

在 repo root 建立 `AI_SESSION_CONTEXT.md`（已提供 template，請看 [AI_SESSION_CONTEXT.md](AI_SESSION_CONTEXT.md)）。每次有人開啟 AI chat session，都要**把這個檔案的內容貼成第一則訊息**。

這個檔案包含：
- 專案已同意的 coding conventions
- finalized schema（決定後填入）
- 你們要實作的 function signatures
- 團隊 decisions log

這樣 AI 就會知道你們的 table names、column names、return types 與 style，並產生符合你們 codebase 的程式碼，而不是自己發明 convention。

**誰更新它：** 任何 merge schema change 或做出 architectural decision 的人，都要在同一個 commit 中更新 `AI_SESSION_CONTEXT.md`。把它當成一份活文件。

### 1.4 — Before-You-Start Ritual

每次 session 打開 AI assistant 前：

1. `git pull origin main` — 取得隊友最新 merged work
2. 檢查 GitHub 上 open Pull Requests，有沒有需要你 review 的？
3. 透過團隊聊天告訴隊友你準備做什麼：*"Working on query_metro_schedules today"*
4. 把 `AI_SESSION_CONTEXT.md` 貼到 AI chat，作為第一則訊息

這只需要兩分鐘，可以避免三個人讓 AI 用三種不同方式解同一個問題。

### 1.5 — 為每個 Stub 約定 Definition of Done

實作任何 stub function 前，團隊先回答這些問題：

- 它收到什麼 input？（docstring 已經記錄）
- 它應該回傳什麼？（也已經記錄，請看 `Returns:` section）
- 對一組已知 input，正確 output 長什麼樣子？

把答案寫下來。例如，對 `query_metro_schedules("MS01", "MS09")`：
- *"Should return at least one schedule. Each dict must have keys `schedule_id`, `line`, `departure_time`, `stops_list`."*

這就是你的 acceptance criterion。當 AI 產生程式碼後，在把任務標成完成前，先用這個 criterion 測試。

---

## Part 2：AI 整合工作流程循環

每次實作 feature 或 function，都遵循這個五階段循環。不要直接跳到 Implementation。

```text
Analysis & Planning → Options Evaluation → Minimal Implementation → Testing → Merging
         ↑                                                                        |
         └────────────────────────────────────────────────────────────────────────┘
                            (如果 tests fail 或發現新需求，就 loop back)
```

### Stage 1 — Analysis & Planning

**你要做什麼：** 在請 AI 解決問題前，先理解問題。

1. 閱讀 stub function 的 docstring，它會精確告訴你函式必須做什麼
2. 查看該函式會查詢的 mock data
3. 根據你們同意的 schema，追蹤需要哪些 table

**AI 在這階段的角色：** 請 AI *解釋*，不要請它產生程式碼。例如：

> *"I need to implement `query_metro_schedules(origin_id, destination_id)`. It should return schedules that serve both stations in the correct order. My schema has a `metro_schedules` table with columns: `schedule_id, line, direction, stops (JSONB array)`. Can you explain what SQL approach I'd use to find schedules where both station IDs appear in the stops array in the right order?"*

**人類決策點：** 你是否在繼續前理解了做法？如果沒有，請 AI 再解釋，不要還沒懂就請它產生程式碼。

### Stage 2 — Options Evaluation

**你要做什麼：** 請 AI 提出 2–3 種方法，並和隊友比較。

範例 prompt：

> *"Give me two different SQL approaches to find metro schedules where MS01 comes before MS09 in a JSONB array of stop IDs. Show the tradeoffs."*

AI 可能會提出：
- Option A：使用 `jsonb_array_elements` 並追蹤 position
- Option B：使用 `@>` containment operator + position comparison

和隊友比較。選擇符合你們 schema 與團隊 SQL 熟悉度的方案。把決策記錄在 `AI_SESSION_CONTEXT.md`：
> *"Metro schedule stop-order checking: using jsonb_array_elements approach (Option A) — clearer to read, easier to debug"*

### Stage 3 — Minimal Implementation

**你要做什麼：** 一次只實作一個 function。先讓它運作，再移到下一個。

**產生程式碼前，先準備 prompt：**
1. 貼上你的 `AI_SESSION_CONTEXT.md` 內容（如果還沒貼過）
2. 貼上精確的 stub function signature 與 docstring
3. 貼上 schema 中相關 table definition

範例 prompt 結構（templates 請看 [Part 4](#part-4有效的-prompts)）：

> *[paste AI_SESSION_CONTEXT.md]*
>
> *Now implement this function. Match the signature exactly — do not change parameter names or return types:*
> *[paste stub function]*
>
> *My schema for the relevant tables:*
> *[paste CREATE TABLE statements]*

**使用 AI output 前先 review：**
- 它是否使用你們 schema 中的 table names？（不是發明的）
- 它是否符合 docstring 描述的 return type？
- 它是否遵循 `example_query()` 中的 `_connect()` / `RealDictCursor` pattern？

Part 3 的 [Example 2](#example-2implementing-a-relational-query-stub) 有完整 walkthrough。

### Stage 4 — Testing

**你要做什麼：** 手動執行 function，確認它回傳你預期的內容。

你不需要正式 test framework。打開 Python shell：

```python
# 從 project root 執行，並確認 virtual environment 已啟用
python

>>> from databases.relational.queries import query_metro_schedules
>>> result = query_metro_schedules("MS01", "MS09")
>>> print(result)
>>> # 它是否回傳 list？每個 item 是否有預期 keys？
>>> # 對 seed data 中存在的 route，結果是否非空？
```

**要檢查什麼：**
- 是否回傳 list（不是 None，也不是 error）？
- 每個 dict 是否有 agent 預期的 keys？
- 對你知道存在的 station pair，是否回傳合理結果？
- 對不存在的 station pair，是否回傳 empty list（而不是 crash）？

如果 function raise error，把 error 與你的 code 貼回 AI chat，請它修正問題。

### Stage 5 — Merging

**你要做什麼：** 讓隊友 review 你的 work，並 merge。

1. Push 你的 branch：`git push origin feature/alice/metro-schedules-query`
2. 在 GitHub 開 Pull Request
3. 請隊友 review，見 Part 3 的 [Example 4](#example-4pr-review-and-merging)
4. 處理 feedback
5. Approved 後 merge
6. 如果 architectural decisions 有變，更新 `AI_SESSION_CONTEXT.md`

**Merge 後更新 main branch：**
```bash
git checkout main
git pull origin main
```

---

## Part 3：小型可運作範例

### Example 1：Schema Design Workshop

**情境：** 你的團隊正在根據 mock data 設計 `metro_stations` table。

**Step 1 — 查看 mock data**（`train-mock-data/metro_stations.json`）：

```json
{
  "station_id": "MS01",
  "name": "Central Square",
  "lines": ["M1", "M2"],
  "is_interchange_metro": true,
  "interchange_metro_lines": ["M1", "M2"],
  "is_interchange_national_rail": true,
  "interchange_national_rail_station_id": "NR01",
  "adjacent_stations": [
    { "station_id": "MS05", "line": "M1", "travel_time_min": 3 },
    { "station_id": "MS02", "line": "M1", "travel_time_min": 3 }
  ]
}
```

**Step 2 — 請 AI 提出 schema：**

> *"Here is one entry from our metro station data: [paste the JSON above]. Design a PostgreSQL schema to store this data. Note that `adjacent_stations` represents graph relationships — we have a separate Neo4j database for those, so you do not need to store them in SQL. Focus on what the relational database needs."*

**Step 3 — AI 可能產生類似內容：**

```sql
CREATE TABLE metro_stations (
    station_id          VARCHAR(10) PRIMARY KEY,
    name                TEXT NOT NULL,
    is_interchange_metro         BOOLEAN DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN DEFAULT FALSE,
    interchange_nr_station_id    VARCHAR(10) REFERENCES national_rail_stations(station_id)
);

CREATE TABLE metro_station_lines (
    station_id  VARCHAR(10) REFERENCES metro_stations(station_id),
    line        VARCHAR(5) NOT NULL,
    PRIMARY KEY (station_id, line)
);
```

**Step 4 — 團隊討論問題：**
- 我們需要把 `metro_station_lines` 做成 separate table，還是可以把 lines 存成 simple array？（提示：看哪些 queries 需要依 line filter）
- `interchange_nr_station_id` 現在就要做 foreign key constraint，還是等兩張 tables 都存在後再加？
- `query_metro_schedules` 會需要從這張 table 取得什麼？

**人類決策：** 團隊決定。AI 提出選項。Normalization choices 會影響每個人的 query functions，所以全員都必須同意。

---

### Example 2：實作 Relational Query Stub

**情境：** Alice 正在實作 `query_metro_schedules`。

**Step 1 — Alice 閱讀 stub**（`databases/relational/queries.py`，lines 110–118）：

```python
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Return metro schedules that serve both origin and destination in the correct order.

    Args:
        origin_id:       e.g. "MS01"
        destination_id:  e.g. "MS09"
    """
    raise NotImplementedError("TODO: implement after designing your schema")
```

**Step 2 — Alice 準備 prompt：**

```text
[paste AI_SESSION_CONTEXT.md first]

Now implement this Python function. Rules:
- Use the _connect() helper and psycopg2.extras.RealDictCursor pattern shown in example_query()
- Match the stub's signature exactly — do not change parameter names or return types
- Use only table/column names from the schema below

Stub to implement:
[paste the stub above]

My schema (relevant tables):
CREATE TABLE metro_schedules (
    schedule_id  VARCHAR(20) PRIMARY KEY,
    line         VARCHAR(5) NOT NULL,
    direction    VARCHAR(10),
    stops        JSONB NOT NULL   -- ordered list of station_ids, e.g. ["MS01","MS02","MS09"]
);
```

**Step 3 — AI 產生 code。Alice 檢查：**
- 是否使用 module 中的 `_connect()`？✓ 或 ✗
- 是否使用 `RealDictCursor`？✓ 或 ✗
- 是否回傳 `list[dict]`，而不是 single row？✓ 或 ✗
- 是否引用 `metro_schedules`（而不是發明的 table name）？✓ 或 ✗

**Step 4 — Alice 測試它：**

```python
python

>>> from databases.relational.queries import query_metro_schedules
>>> result = query_metro_schedules("MS01", "MS09")
>>> print(type(result))      # 應該是 <class 'list'>
>>> print(result)            # 應該顯示 schedule dicts
>>> print(result[0].keys())  # 檢查 key names
```

---

### Example 3：實作 Graph Query Stub

**情境：** Bob 正在實作 `query_station_connections`。

**Stub**（`databases/graph/queries.py`，lines 159–166）：

```python
def query_station_connections(station_id: str) -> list[dict]:
    """
    List all direct connections from a given station.

    Args:
        station_id: e.g. "MS01" or "NR01"
    """
    raise NotImplementedError("TODO: implement after designing your graph schema")
```

**Bob 的 prompt：**

```text
[paste AI_SESSION_CONTEXT.md first]

Implement this Neo4j query function. Rules:
- Use the _driver() helper and the session pattern shown in example_count_nodes()
- Match the stub's signature exactly
- Use the node labels and relationship types from our agreed graph schema below

Stub to implement:
[paste stub above]

Our graph schema:
- Node label: Station, properties: {station_id, name, network}
- Relationship: CONNECTS_TO, properties: {line, travel_time_min}
```

**Bob 檢查 AI output：**
- 是否使用 module 中的 `_driver()`？✓ 或 ✗
- 是否使用 `with driver.session() as session:`？✓ 或 ✗
- Cypher 是否使用 `Station` 作為 node label（不是 `Node` 或 `stop`）？✓ 或 ✗
- 是否回傳 `list[dict]`？✓ 或 ✗

**Bob 測試它：**

```python
python

>>> from databases.graph.queries import query_station_connections
>>> result = query_station_connections("MS01")
>>> print(result)
>>> # 根據 mock data，MS01 (Central Square) 連到 MS05、MS02、MS06、MS07
>>> # 檢查你的結果是否相符
```

---

### Example 4：PR Review and Merging

**情境：** Alice 已 push `feature/alice/metro-schedules-query` 並開了 PR。

**Bob review PR。他檢查：**

1. Function 是否符合 stub signature？（沒有多加或更改 parameters）
2. 是否使用 agreed schema 中的 table/column names？
3. 是否遵循 `_connect()` / `RealDictCursor` pattern？
4. 是否處理 empty-result case（找不到 schedules）？

**如果 Bob 發現問題**，他在 GitHub 留 comment：
> *"Line 45: your query uses `stations` but our schema calls this table `metro_stations`. Also the return dict is missing the `departure_time` key that `query_metro_fare` expects."*

**Alice 修正它**，push 新 commit，並回覆 comment。

**Bob approve 後**，Alice merge PR：
- 在 GitHub 點 "Merge Pull Request"
- 接著在本機執行：`git checkout main && git pull origin main`

---

### Example 5：抓出 AI 不一致

**情境：** Carol 請 AI 實作 `query_national_rail_fare`。AI 產生：

```python
cur.execute("SELECT * FROM fares WHERE route_id = %s", (schedule_id,))
```

但 agreed schema 中沒有 `fares` table。fare 是從 `national_rail_schedules.base_fare_usd` 與 `national_rail_schedules.per_stop_rate_usd` 計算的。

**如何抓出它：**
- Code 會執行，但回傳 `[]`，或丟出 `psycopg2.errors.UndefinedTable` error
- Carol 比對 AI output 中的 table name 與自己的 schema，發現 mismatch

**修正：** Carol 更新 prompt，貼上精確的 `CREATE TABLE` statements，並說：
> *"Do not invent table or column names. Use only what appears in the schema below."*

**Lesson：** 永遠把 schema 貼到 AI prompt。若你沒有給 AI 真實名稱，它會編出聽起來合理的名字。

---

## Part 4：有效的 Prompts

這些是 tool-agnostic templates。可貼到任何 AI assistant（Claude、Copilot、Cursor、Gemini 等）。

### Template A：Schema Design

```text
I'm a student working on a database project. Here is one sample entry from our
raw data file [filename]:

[paste 1–3 JSON objects from the mock data]

Design a PostgreSQL schema to store this data. Constraints:
- Use snake_case for all table and column names
- Use VARCHAR for IDs (they look like "MS01", "NR_SCH01")
- Avoid storing graph/network relationships (those go in Neo4j)
- Include PRIMARY KEY and NOT NULL where appropriate
- Show the CREATE TABLE statement only, no explanation

Note: this schema will be shared with two teammates. Table names must be agreed
before anyone writes query functions.
```

### Template B：Query Function Implementation

```text
I'm implementing a Python function for a PostgreSQL database project.
Follow these rules strictly:
- Use only the table and column names in the schema below — do not invent names
- Use the _connect() helper function already defined in the module
- Use psycopg2.extras.RealDictCursor (so rows come back as dicts)
- Match the stub signature exactly — do not change parameter names or return type
- Return an empty list [] (not None) when no rows are found
- Do not add try/except unless the docstring specifically asks for error handling

[paste AI_SESSION_CONTEXT.md here]

Stub to implement:
[paste the stub function with its docstring]

Schema (relevant tables only):
[paste the CREATE TABLE statements your function will query]
```

### Template C：Code Review

```text
Review this Python database function against the stub contract and schema below.
Check for:
1. Does it use only table/column names from the schema?
2. Does it match the stub's return type and key names?
3. Does it follow the _connect() / RealDictCursor pattern?
4. Does it handle the empty-result case gracefully?
5. Any SQL injection risk (are all user inputs parameterised with %s)?

Report only real issues — no style suggestions.

Stub (the contract):
[paste the original stub]

Implementation to review:
[paste your code]

Schema:
[paste relevant CREATE TABLE statements]
```

### Template D：Debugging

```text
This Python function is raising an error. Help me fix it.

Error:
[paste the full traceback]

Function:
[paste your code]

Schema:
[paste relevant CREATE TABLE statements]

What I expected it to do:
[one sentence]
```

### 如何分享有效的 Prompts

當你找到能產生好 output 的 prompt，把它加到 `AI_SESSION_CONTEXT.md` 的 **Prompts log** section。隊友就能重複使用，不需要花時間自己寫。

---

## Appendix：Session 前檢查清單

每次 AI-assisted work session 前，跑過這份清單。

```text
[ ] git checkout main && git pull origin main
[ ] Check GitHub for open Pull Requests — anything needing your review?
[ ] Confirm Docker containers are running: docker compose ps
    (should show postgres, neo4j, pgadmin as "Up")
[ ] Confirm your virtual environment is active: python -c "import psycopg2; print('ok')"
[ ] Open AI_SESSION_CONTEXT.md and paste its contents into your AI chat
[ ] Tell your teammates what you're about to work on
```

如果 Docker 沒有執行：在 project root 執行 `docker compose up -d`。

如果你的 venv 不存在：請看 README.md 的 [Python Virtual Environments](README.md#python-virtual-environments) section。

---

## Quick Reference

| 問題 | 到哪裡看 |
|---|---|
| 我需要實作哪些 functions？ | `databases/relational/queries.py`, `databases/graph/queries.py` — 閱讀 stubs 與 docstrings |
| 我有哪些 data 可以用？ | `train-mock-data/` — 每個 entity 的 JSON files |
| Agent 會用什麼參數呼叫我的 function？ | `skeleton/agent.py` — `TOOLS` list 顯示精確 parameters |
| 我要在哪裡設計 schema？ | `databases/relational/schema.sql` — 目前是空的，由你填入 |
| 一開始要貼什麼給 AI？ | `AI_SESSION_CONTEXT.md` — 共享 context file |
| 通用 team practices 與 checklists | `TEAM_PROJECT_GUIDE.md` |
