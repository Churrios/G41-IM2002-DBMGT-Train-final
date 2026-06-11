# ✅ AI Session Context — TransitFlow

> **⚠️ 歷史快照聲明（2026-06-11）：** 本檔為開發期的 AI context 快照（實質更新至 2026-06-04），**已不再與 codebase 同步**。特別注意：schema 區段早於 junction table 重構（PR #34）與 Task 6 `delay_events` 擴充。最終版本以 `databases/relational/schema.sql`（schema）、`databases/relational/queries.py` / `databases/graph/queries.py`（函式簽名）、`skeleton/seed_postgres.py`（seeding 順序）為準。

**如何使用這個檔案：**
每次開始 AI coding session 時，把這個檔案的完整內容作為第一則訊息貼給你的 AI assistant。這會提供 AI 所需的 context，讓它產生符合你 codebase、且與隊友工作一致的程式碼。

**誰維護這個檔案：**
任何做出 schema change 或 architectural decision 的人，都要在同一個 commit 中更新這個檔案。把它當成團隊契約。

---

## Project Overview

TransitFlow 是一個 Python-based AI chat assistant，服務對象是一個虛構 transit operator。它會查詢三個資料庫：PostgreSQL（relational + vector）與 Neo4j（graph），並使用 LLM 回答使用者問題。我們作為學生的任務，是設計 database schema，並實作 `databases/relational/queries.py` 與 `databases/graph/queries.py` 中的 query functions。

## Tech Stack

- Language: Python 3.11+
- Relational DB: PostgreSQL via `psycopg2` with `RealDictCursor`
- Graph DB: Neo4j via the `neo4j` Python driver
- Vector search: `pgvector` extension（已實作，不要修改）
- Web UI: Gradio
- LLM: Google Gemini 或 local Ollama（透過 `.env` 設定）

## Coding Conventions

- **Naming:** 所有 Python names 與 SQL identifiers 使用 `snake_case`
- **Docstrings:** 所有 functions 都必須有 docstring，並包含 `Args:` 與 `Returns:` sections
- **Return types:** 使用 type hints。Read-only functions 回傳 `list[dict]` 或 `Optional[dict]`
- **Empty results:** 回傳 `[]` 或 `None`（依文件說明），不要因為 "not found" raise exception
- **SQL:** 所有 user inputs 使用 `%s` placeholders，不要把值 string-format 進 SQL
- **Relational pattern:** 使用 `_connect()` helper + `psycopg2.extras.RealDictCursor`：
  ```python
  with _connect() as conn:
      with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
          cur.execute("SELECT ...", (param,))
          return [dict(row) for row in cur.fetchall()]
  ```
- **Graph pattern:** 使用 `_driver()` helper + session：
  ```python
  with _driver() as driver:
      with driver.session() as session:
          result = session.run("MATCH ...", station_id=station_id)
          return [dict(record) for record in result]
  ```

## Agreed Relational Schema

> 資料來源：`databases/relational/schema.sql` — 最後審閱：2026-05-28

```sql
-- ============================================================
--  1. USERS
-- ============================================================

CREATE TABLE registered_users (
    user_id          VARCHAR(10)   PRIMARY KEY,
    full_name        TEXT          NOT NULL,
    email            VARCHAR(200)  NOT NULL UNIQUE,
    password         TEXT          NOT NULL,  -- bcrypt hash，絕對不存明文
    phone            VARCHAR(20),
    date_of_birth    DATE,
    secret_question  TEXT,
    secret_answer    TEXT,
    registered_at    TIMESTAMPTZ   DEFAULT NOW(),
    is_active        BOOLEAN       DEFAULT TRUE
);

-- ============================================================
--  2. STATIONS
--  lines 用 VARCHAR[] — 查詢用 @> 運算子
--  adjacent_stations 不存 SQL，交給 Neo4j
-- ============================================================

CREATE TABLE metro_stations (
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_metro         BOOLEAN       DEFAULT FALSE,
    is_interchange_national_rail BOOLEAN       DEFAULT FALSE,
    interchange_nr_station_id    VARCHAR(10)
);

CREATE INDEX idx_metro_stations_lines ON metro_stations USING GIN (lines);

CREATE TABLE national_rail_stations (
    station_id                   VARCHAR(10)   PRIMARY KEY,
    name                         TEXT          NOT NULL,
    lines                        VARCHAR(10)[] NOT NULL DEFAULT ARRAY[]::VARCHAR(10)[],
    is_interchange_national_rail BOOLEAN       DEFAULT FALSE,
    is_interchange_metro         BOOLEAN       DEFAULT FALSE,
    interchange_metro_station_id VARCHAR(10)   REFERENCES metro_stations(station_id)
);

CREATE INDEX idx_national_rail_stations_lines ON national_rail_stations USING GIN (lines);

ALTER TABLE metro_stations
    ADD CONSTRAINT fk_interchange_nr
    FOREIGN KEY (interchange_nr_station_id)
    REFERENCES national_rail_stations(station_id);

-- ============================================================
--  3. SCHEDULES
--  stops_in_order 用 VARCHAR[] — array_position() 查站序更簡潔
--  travel_time_from_origin 用 JSONB — key-value map {"MS01": 0, ...}
-- ============================================================

CREATE TABLE metro_schedules (
    schedule_id              VARCHAR(20)   PRIMARY KEY,
    line                     VARCHAR(5)    NOT NULL,
    direction                VARCHAR(15)   NOT NULL,
    origin_station_id        VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id   VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    stops_in_order           VARCHAR(10)[] NOT NULL,
    travel_time_from_origin  JSONB         NOT NULL,
    first_train_time         TIME          NOT NULL,
    last_train_time          TIME          NOT NULL,
    frequency_min            INT           NOT NULL,
    operates_on              VARCHAR(10)[] NOT NULL DEFAULT ARRAY['mon','tue','wed','thu','fri','sat','sun'],
    base_fare_usd            NUMERIC(6,2)  NOT NULL,
    per_stop_rate_usd        NUMERIC(6,2)  NOT NULL
);

CREATE INDEX idx_metro_schedules_stops ON metro_schedules USING GIN (stops_in_order);

CREATE TABLE national_rail_schedules (
    schedule_id               VARCHAR(20)   PRIMARY KEY,
    line                      VARCHAR(10)   NOT NULL,
    service_type              VARCHAR(10)   NOT NULL,  -- 'normal' or 'express'
    direction                 VARCHAR(15)   NOT NULL,
    origin_station_id         VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id    VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    stops_in_order            VARCHAR(10)[] NOT NULL,
    passed_through_stations   VARCHAR(10)[],
    travel_time_from_origin   JSONB         NOT NULL,
    first_train_time          TIME          NOT NULL,
    last_train_time           TIME          NOT NULL,
    frequency_min             INT           NOT NULL,
    operates_on               VARCHAR(10)[] NOT NULL DEFAULT ARRAY['mon','tue','wed','thu','fri','sat','sun'],
    std_base_fare_usd         NUMERIC(6,2)  NOT NULL,
    std_per_stop_rate_usd     NUMERIC(6,2)  NOT NULL,
    first_base_fare_usd       NUMERIC(6,2)  NOT NULL,
    first_per_stop_rate_usd   NUMERIC(6,2)  NOT NULL
);

CREATE INDEX idx_nr_schedules_stops ON national_rail_schedules USING GIN (stops_in_order);

-- ============================================================
--  4. SEAT LAYOUTS  (靜態配置，每班車固定)
--  可用性從 bookings 推導，不另開 inventory table
-- ============================================================

CREATE TABLE seat_layouts (
    schedule_id  VARCHAR(20)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    seat_id      VARCHAR(10)  NOT NULL,
    coach        VARCHAR(5)   NOT NULL,
    row_num      INT          NOT NULL,
    col_char     VARCHAR(5)   NOT NULL,
    fare_class   VARCHAR(10)  NOT NULL,
    PRIMARY KEY (schedule_id, seat_id)
);

-- ============================================================
--  5. BOOKINGS & TRAVEL HISTORY
-- ============================================================

CREATE TABLE bookings (
    booking_id              VARCHAR(20)   PRIMARY KEY,
    user_id                 VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    schedule_id             VARCHAR(20)   NOT NULL REFERENCES national_rail_schedules(schedule_id),
    origin_station_id       VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    destination_station_id  VARCHAR(10)   NOT NULL REFERENCES national_rail_stations(station_id),
    travel_date             DATE          NOT NULL,
    departure_time          TIME          NOT NULL,
    ticket_type             VARCHAR(10)   NOT NULL,
    fare_class              VARCHAR(10)   NOT NULL,
    coach                   VARCHAR(5)    NOT NULL,
    seat_id                 VARCHAR(10)   NOT NULL,
    stops_travelled         INT           NOT NULL,
    amount_usd              NUMERIC(8,2)  NOT NULL,
    status                  VARCHAR(15)   NOT NULL,
    booked_at               TIMESTAMPTZ   DEFAULT NOW(),
    travelled_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ
);

CREATE TABLE metro_travel_history (
    trip_id                 VARCHAR(20)   PRIMARY KEY,
    user_id                 VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    schedule_id             VARCHAR(20)   NOT NULL REFERENCES metro_schedules(schedule_id),
    origin_station_id       VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    destination_station_id  VARCHAR(10)   NOT NULL REFERENCES metro_stations(station_id),
    travel_date             DATE          NOT NULL,
    ticket_type             VARCHAR(10)   NOT NULL,
    day_pass_ref            VARCHAR(20),
    stops_travelled         INT,
    amount_usd              NUMERIC(8,2)  NOT NULL,
    status                  VARCHAR(15)   NOT NULL,
    purchased_at            TIMESTAMPTZ,
    travelled_at            TIMESTAMPTZ,
    cancelled_at            TIMESTAMPTZ
);

-- ============================================================
--  6. PAYMENTS
--  booking_id 不加 FK — 同時參照 BK (bookings) 和 MT (metro_travel_history)
-- ============================================================

CREATE TABLE payments (
    payment_id   VARCHAR(20)   PRIMARY KEY,
    booking_id   VARCHAR(20)   NOT NULL,
    amount_usd   NUMERIC(8,2)  NOT NULL,
    method       VARCHAR(20)   NOT NULL,
    status       VARCHAR(15)   NOT NULL,
    paid_at      TIMESTAMPTZ   DEFAULT NOW(),
    refunded_at  TIMESTAMPTZ
);

-- ============================================================
--  7. FEEDBACK
--  booking_id 不加 FK — 同時參照 BK (bookings) 和 MT (metro_travel_history)
-- ============================================================

CREATE TABLE feedback (
    feedback_id   VARCHAR(20)   PRIMARY KEY,
    booking_id    VARCHAR(20)   NOT NULL,
    user_id       VARCHAR(10)   NOT NULL REFERENCES registered_users(user_id),
    rating        SMALLINT      NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment       TEXT,
    submitted_at  TIMESTAMPTZ   DEFAULT NOW()
);
```

### 種子資料寫入順序（FK 相依鏈）

```
registered_users
→ metro_stations（先不填 interchange_nr_station_id）
→ national_rail_stations
→ UPDATE metro_stations SET interchange_nr_station_id（補循環 FK）
→ metro_schedules
→ national_rail_schedules
→ seat_layouts
→ bookings
→ metro_travel_history
→ payments
→ feedback
```

### JSON → 欄位對應注意事項

| JSON key | Schema 欄位 |
|---|---|
| `travel_time_from_origin_min` | `travel_time_from_origin`（JSONB） |
| `fare_classes.standard.base_fare` | `std_base_fare_usd` |
| `fare_classes.standard.per_stop_rate` | `std_per_stop_rate_usd` |
| `fare_classes.first.base_fare` | `first_base_fare_usd` |
| `fare_classes.first.per_stop_rate` | `first_per_stop_rate_usd` |
| coaches → seats（巢狀） | 攤平為 `seat_layouts` 每個 seat 一列 |

## Agreed Graph Schema

> **狀態：已確認 2026-06-04 — 採 Q1=A 分離標籤模型，對齊評分標準。**
> Q1 分離標籤 MetroStation / NationalRailStation ✓ | Q2 METRO_LINK / RAIL_LINK ✓ | Q3 INTERCHANGE_TO（雙向）✓ | Q5 票價寫入邊屬性 ✓

```
節點標籤：
  MetroStation（捷運站）
    屬性：
      station_id                    String   （例："MS01"）── 節點唯一識別、加 unique constraint
      name                          String   （例："Central Square"）
      lines                         List<String>  （例：["M1", "M2"]）
      is_interchange_national_rail  Boolean  （true 代表可換乘國鐵站）

  NationalRailStation（國鐵站）
    屬性：
      station_id                    String   （例："NR01"）── 節點唯一識別、加 unique constraint
      name                          String   （例："Central Station"）
      lines                         List<String>  （例：["NR1", "NR2"]）
      is_interchange_metro          Boolean
      interchange_metro_station_id  String   （對應捷運站 ID，或 null）

  （採分離標籤而非單一 Station，是為對齊評分標準 ——
   Task 4 / Live A 會明文檢查兩種 label 是否存在。）

關係類型：
  METRO_LINK   (MetroStation)-[:METRO_LINK]->(MetroStation)
    屬性：
      line              String
      travel_time_min   Integer
      fare_usd          Float  ── round(1.0 + 0.5 × travel_time_min, 2)；捷運單一票價，無 fare_class 之分

  RAIL_LINK    (NationalRailStation)-[:RAIL_LINK]->(NationalRailStation)
    屬性：
      line                String
      travel_time_min     Integer
      fare_standard_usd   Float  ── round(2.0 + 1.2 × travel_time_min, 2)
      fare_first_usd      Float  ── round(2.0 + 2.0 × travel_time_min, 2)

  INTERCHANGE_TO  (MetroStation)-[:INTERCHANGE_TO]-(NationalRailStation)
    屬性：
      transfer_time_min   Integer  ── 固定 5 分鐘（規格未強制；教授確認可自訂合理值）
    注意：seeding 建雙向兩條 directed edge（metro→rail 與 rail→metro），
          查詢用無向 -[:INTERCHANGE_TO]-。
```

### 設計理由

| 決策 | 選擇 | 理由 |
|---|---|---|
| 分離 `MetroStation` / `NationalRailStation` | ✓ | 對齊評分標準（Task 4 / Live A 以 label 名稱明文檢查） |
| `METRO_LINK` / `RAIL_LINK` 分開 | ✓ | 各自把票價模型掛在邊上；路徑查詢可限定 `'METRO_LINK\|RAIL_LINK'` 維持同網 |
| 票價在 seeding 寫進邊（Q5=A） | ✓ | `apoc.algo.dijkstra` 直接用票價屬性當權重，fare_class 真正影響路徑選擇（Live C2），而非只改最後總額 |
| `INTERCHANGE_TO` 雙向、`transfer_time_min=5` | ✓ | 只有 `query_interchange_path` 會走它（跨網）；shortest/cheapest 刻意不含它，使同網不可達時回 found=False |
| 以 `station_id` 作節點識別 | ✓ | 每個 label 一條 unique constraint；來源 JSON 的穩定外部鍵 |

拓撲統計：30 節點（20 MetroStation + 10 NationalRailStation），
66 邊（42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO）。

## Function Signatures We Are Implementing

這些是固定 contracts。AI-generated code 必須完全符合這些 signatures。

### Relational (`databases/relational/queries.py`)

```python
# Read-only
def query_national_rail_availability(origin_id: str, destination_id: str, travel_date: Optional[str] = None) -> list[dict]: ...
def query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]: ...
def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]: ...
def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]: ...
def query_available_seats(schedule_id: str, travel_date: str, fare_class: str) -> list[dict]: ...
def query_user_profile(user_email: str) -> Optional[dict]: ...
def query_user_bookings(user_email: str) -> dict: ...  # returns {"national_rail": [...], "metro": [...]}
def query_payment_info(booking_id: str) -> Optional[dict]: ...

# Write operations
def execute_booking(user_id, schedule_id, origin_station_id, destination_station_id, travel_date, fare_class, seat_id, ticket_type="single") -> tuple[bool, dict | str]: ...
def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]: ...

# Auth
def register_user(email, first_name, surname, year_of_birth, password, secret_question, secret_answer) -> tuple[bool, str]: ...
def login_user(email: str, password: str) -> Optional[dict]: ...
def get_user_secret_question(email: str) -> Optional[str]: ...
def verify_secret_answer(email: str, answer: str) -> bool: ...
def update_password(email: str, new_password: str) -> bool: ...
```

### Graph (`databases/graph/queries.py`)

```python
def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict: ...
def query_cheapest_route(origin_id: str, destination_id: str, network: str = "auto", fare_class: str = "standard") -> dict: ...
def query_alternative_routes(origin_id, destination_id, avoid_station_id, network="auto", max_routes=3) -> list[list[dict]]: ...
def query_interchange_path(origin_id: str, destination_id: str) -> dict: ...
def query_delay_ripple(delayed_station_id: str, hops: int = 2) -> list[dict]: ...
def query_station_connections(station_id: str) -> list[dict]: ...
```

## Team Decisions Log

<!-- 做出決策時新增 entries。格式："Decision: X. Why: Y." -->

- [x] **2026-05-28** 多型 FK：`payments.booking_id` 與 `feedback.booking_id` **不加 FK 約束**。原因：同時參照兩張表（`bookings` BK_ 前綴、`metro_travel_history` MT_ 前綴）。應用層依 ID 前綴判斷。
- [x] **2026-05-28** 循環站點 FK：`metro_stations.interchange_nr_station_id` → `national_rail_stations`。解法：先插入 metro 列（interchange 欄位為 NULL），再插入 NR 列，最後 UPDATE 補 FK。
- [x] **2026-05-28** 密碼儲存：`registered_users.password` **只存 bcrypt hash**，絕對不種明文。在 `seed_postgres.py` 中使用 `bcrypt.hashpw()`。
- [x] **2026-05-28** `travel_time_from_origin` 以 **JSONB map** 儲存 `{"station_id": minutes}`，不另開 junction table。理由：唯讀查詢、不需 join，JSON key 即為 station_id。
- [x] **2026-05-28** `stops_in_order` 與 `lines` 以 **`VARCHAR(10)[]`** 儲存，使用 `@>`（contains）與 `array_position()` 查詢。避免為有序站點清單另開 junction table。
- [x] **2026-06-04** Graph schema 遷移至分離標簽模型（Q1=A）：`MetroStation` / `NationalRailStation`，`METRO_LINK {line, travel_time_min, fare_usd}` / `RAIL_LINK {line, travel_time_min, fare_standard_usd, fare_first_usd}`，`INTERCHANGE_TO {transfer_time_min:5}`（雙向）。統計：30 節點（20 metro + 10 NR），66 邊（42 METRO_LINK + 18 RAIL_LINK + 6 INTERCHANGE_TO）。取代 2026-05-28 的單一 Station 設計。

## Prompts That Worked

<!-- 分享產生好 output 的 prompts，讓隊友可以重複使用。 -->

### Schema design prompt that worked:
```text
TODO — schema design workshop 後，在這裡加入 prompt
```

### Query implementation prompt that worked:
```text
TODO — 實作第一個 function 後加入
```
