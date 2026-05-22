# AI Session Context — TransitFlow

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

<!-- ============================================================
  團隊完成 schema design workshop 後填寫這裡。
  把最終 CREATE TABLE statements 貼在這裡。
  ============================================================ -->

```sql
-- TODO：team review 後，把最終 schema.sql 內容貼在這裡
```

## Agreed Graph Schema

<!-- ============================================================
  團隊同意 Neo4j node labels 與 relationship types 後填寫這裡。
  ============================================================ -->

```text
Node labels:
- TODO

Relationship types:
- TODO

Key properties:
- TODO
```

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

- [ ] Schema design: TODO — 在這裡加入你們的 table/column decisions
- [ ] Graph schema: TODO — 在這裡加入你們的 node label 與 relationship type decisions
- [ ] (example) Metro schedule stop ordering: using `jsonb_array_elements` approach — 比 containment operators 更容易 debug

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
