# Side Note 1 — 正式環境中的關聯式資料庫最佳實務

> **免責聲明**
> 本文件是在多個 AI 工具協助下共同撰寫。雖然已盡力確保內容正確，但仍可能存在非預期錯誤。如果你發現任何錯誤，請[在 GitHub 提交 issue](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/issues)。

---

> **這是寫給誰的？**
> 這份 note 是給剛開始接觸資料庫的學生。
> 你已經看過 SQL，也已經在 Python 中執行過一些 queries。現在讓我們看看真實正式環境系統如何正確處理這些事情。

---

## 為什麼這件事重要？

`databases/relational/queries.py` 中的程式碼很適合教學環境。但正式環境系統，也就是真實使用者大規模使用的 apps，對**效能**、**安全性**與**可維護性**有更嚴格的要求。這份 note 會逐一說明每個差距，解釋它*為什麼*存在，並展示正式環境版本會長什麼樣子。

---

## 1. Connection Pooling

### 什麼是 database connection？

每次你的 Python code 要和 PostgreSQL 溝通時，都必須先開啟一個 **connection**，也就是 app 與 database server 之間的專用溝通通道。這會包含 TCP handshake、authentication，以及雙方的 resource allocation。

在教學程式碼中，每個 query function 都會這樣做：

```python
def _connect():
    conn = psycopg2.connect(PG_DSN)  # 每次都開一個全新的 connection
    conn.autocommit = True
    return conn
```

這代表如果 100 位使用者同時搜尋火車座位，你的 app 會試著同時開啟 100 個獨立 connections。PostgreSQL 預設 connection 上限大約是 100，你的 app 會開始拒絕使用者。

### 正式環境解法：Connection Pools

**Connection pool** 會維持一組已開啟並準備好的 connections。你的程式碼不再每次 query 都開啟與關閉 connection，而是從 pool 借一個 connection、使用它、再歸還。

```python
from psycopg2 import pool

# App 啟動時建立一次，保持 2 到 10 個 connections ready
_pool = pool.ThreadedConnectionPool(minconn=2, maxconn=10, dsn=PG_DSN)

def query_national_rail_availability(origin_id, destination_id, travel_date=None):
    conn = _pool.getconn()       # 借用一個 connection
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (origin_id, destination_id))
            return cur.fetchall()
    finally:
        _pool.putconn(conn)      # 即使發生 error，也一定要歸還
```

對非常大規模的 apps，會有一個叫做 **PgBouncer** 的獨立工具放在 app 與 PostgreSQL 之間。它能比任何 in-process pool 更有效率地管理上千個 connections。

### 延伸閱讀
- [psycopg2 Connection Pools（官方文件）](https://www.psycopg.org/docs/pool.html)
- [PgBouncer — 官方網站與文件](https://www.pgbouncer.org/)
- [What is Connection Pooling?（CockroachDB blog）](https://www.cockroachlabs.com/blog/what-is-connection-pooling/)

---

## 2. SQL 如何組織

教學程式碼把 SQL 當成 inline strings 存在每個 Python function 內。這對學習沒問題，但正式環境團隊會有更嚴謹的 conventions。

### Option A — ORM（Object-Relational Mapper）

ORM 讓你撰寫 Python objects，而不是 raw SQL。Library 會自動把你的 Python 轉換成 SQL。

最受歡迎的 Python ORM 是 **SQLAlchemy**。

```python
# 不直接寫 SQL，而是定義對應 tables 的 Python classes
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select

# Step 1：建立 shared base，所有 models 都繼承它
class Base(DeclarativeBase):
    pass

# Step 2：透過繼承 Base 來定義 model
class TrainService(Base):
    __tablename__ = "train_services"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_code: Mapped[str]
    available_seats: Mapped[int]

# 接著用 Python 查詢，完全沒有 SQL string
stmt = select(TrainService).where(TrainService.available_seats > 0)
services = session.execute(stmt).scalars().all()
```

**優點：** Type-safe、editor autocomplete、database-agnostic（你可以用一行 config 從 PostgreSQL 切到 MySQL）、內建 migration support。

**缺點：** 把 SQL 藏起來（學習時是問題），對複雜 joins 可能產生低效率 queries。

### Option B — 獨立 `.sql` 檔

另一種在 data-heavy systems 中常見的 pattern，是把 SQL 放在專用檔案中：

```text
databases/
  relational/
    queries/
      seat_availability.sql
      user_bookings.sql
      ticket_prices.sql
```

一個叫做 **aiosql** 的 library 會在 startup 時載入這些檔案，並自動把它們暴露成 Python functions。DBAs（database administrators）可以不碰 Python code 就調校 SQL，而你也可以直接在 pgAdmin 測試 queries。

### Option C — Query Builder（SQLAlchemy Core）

這是中間路線。你寫的是*接近* SQL，但使用結構化、可組合的 Python style：

```python
from sqlalchemy import select, and_

stmt = (
    select(train_services, stations)
    .join(stations, train_services.c.origin_id == stations.c.id)
    .where(
        and_(
            stations.c.code == origin_code,
            train_services.c.available_seats > 0
        )
    )
)
```

### 延伸閱讀
- [SQLAlchemy ORM Tutorial（官方）](https://docs.sqlalchemy.org/en/20/orm/quickstart.html)
- [aiosql — Python 的 .sql files SQL 管理](https://nackjicholson.github.io/aiosql/)
- [SQLAlchemy Core Tutorial（官方）](https://docs.sqlalchemy.org/en/20/core/tutorial.html)
- [Full Stack Python — SQLAlchemy overview](https://www.fullstackpython.com/sqlalchemy.html)

---

## 3. Asynchronous Database Access

### 這裡的「synchronous」是什麼意思？

在教學程式碼中，當 query 執行時，Python 會**停下來等待** PostgreSQL 回應，然後才做其他事情。這稱為 **blocking** 或 synchronous I/O。

對單一使用者來說，這沒問題。對服務數百位使用者的 web API 來說，這代表一個慢 database query 可能會卡住後面等待的所有人。

### 正式環境解法：Async I/O

現代 Python web frameworks，例如 **FastAPI**，是圍繞 `async`/`await` 建立的。搭配 **asyncpg** 這類 async database driver 時，你的 app 可以同時處理許多 requests，而不必一直等待：

```python
import asyncpg

async def query_seat_availability(origin_code: str, dest_code: str):
    async with pool.acquire() as conn:          # async pool，不會 block
        rows = await conn.fetch(sql, origin_code, dest_code)
        return [dict(row) for row in rows]
```

可以把它想像成餐廳服務生。Synchronous waiter 接一筆點餐後，走到廚房，站在那裡等餐點完成，再回來。Async waiter 會接很多筆點餐，把它們都送到廚房，然後先處理任何已經準備好的餐點。

### 延伸閱讀
- [asyncpg — Python 的快速 PostgreSQL client（GitHub）](https://github.com/MagicStack/asyncpg)
- [FastAPI with Databases tutorial（官方 FastAPI 文件）](https://fastapi.tiangolo.com/tutorial/sql-databases/)
- [Real Python — Async IO in Python](https://realpython.com/async-io-python/)

---

## 4. Password Security

### Plain-text passwords 有什麼問題？

教學程式碼會按照使用者輸入的原樣儲存與檢查 passwords：

```python
# In register_user()
INSERT INTO users (..., password, ...) VALUES (..., %s, ...)

# In login_user()
WHERE u.email = %s AND u.password = %s
```

如果攻擊者曾經取得你資料庫的 read access（透過 SQL injection、backup leak 或 misconfigured cloud bucket），每位使用者的密碼就會立刻外洩，包括他們在其他網站重複使用同一密碼的帳號。

### 正式環境解法：Password Hashing

Passwords 在儲存前應該先通過**單向 hashing function**。Hash 無法反推回原始 password。當使用者登入時，你 hash 他們輸入的內容，並比較兩個 hashes。你永遠不直接比較 plain text。

```python
from argon2 import PasswordHasher

ph = PasswordHasher()

# 註冊時，儲存 hash，而不是 password
hashed = ph.hash(plain_password)
# e.g. "$argon2id$v=19$m=65536,t=3,p=4$..."

# 登入時，拿 input 與 stored hash 驗證
try:
    ph.verify(stored_hash, input_password)  # 錯誤時會 raise exception
    return True
except Exception:
    return False
```

**argon2** 是目前的 gold standard，由 OWASP（Open Web Application Security Project）推薦。**bcrypt** 也廣泛使用且可接受。

### 為什麼不直接用 Python 內建的 `hashlib`？

像 `hashlib.sha256()` 這類 functions 設計目標是*快速*。這對 checksums 很好，但對 passwords 很糟。攻擊者可以針對 SHA-256 hash 每秒測試數十億個猜測。Argon2 與 bcrypt 則刻意變慢且 memory-intensive，讓 brute-force attacks 不切實際。

### 延伸閱讀
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [argon2-cffi — Python library（文件）](https://argon2-cffi.readthedocs.io/en/stable/)
- [Python hashlib module — 官方文件（說明為什麼它不適合 passwords）](https://docs.python.org/3/library/hashlib.html)

---

## 5. Repository Pattern

### 問題是什麼？

在教學程式碼中，agent 會直接呼叫 query functions：

```python
# Inside agent.py
results = query_user_bookings(user_email)
```

這樣可以運作，但它會讓你的 business logic 和 database layer 緊密**耦合**。如果你有一天想要：
- 把 PostgreSQL 換成不同資料庫
- 在沒有真實資料庫的情況下寫 automated tests
- 改變 bookings 的取得方式，但不想碰每個 caller

你就必須找到並編輯每個呼叫 `query_user_bookings` 的地方。

### 正式環境解法：Repository classes

**Repository** 是一個 class，負責某個 domain concept 的所有 database operations。App 的其他部分只和 repository 溝通，不直接和 database 溝通。

```python
class BookingRepository:
    def __init__(self, session):
        self.session = session

    def get_by_user(self, user_email: str) -> list[dict]:
        # 所有 SQL 都放在這裡
        ...

    def create(self, user_id: int, service_id: int, travel_date: str) -> dict:
        ...

# 在 tests 中，你可以用 fake version 取代它
class FakeBookingRepository:
    def get_by_user(self, user_email: str) -> list[dict]:
        return [{"booking_ref": "TEST001", ...}]   # 不需要 database
```

這符合一個稱為 **Separation of Concerns** 的軟體設計原則，也就是程式碼的每個部分都有一個清楚責任。

### 延伸閱讀
- [Martin Fowler — Repository Pattern（reference）](https://martinfowler.com/eaaCatalog/repository.html)
- [ArjanCodes — Repository Pattern in Python（YouTube）](https://www.youtube.com/watch?v=9pymbjfqfNs)
- [Cosmic Python — Repository Pattern（free book）](https://www.cosmicpython.com/book/chapter_02_repository.html)

---

## 6. Database Migrations

### 問題是什麼？

在開發階段，當你想替 table 新增 column 時，你可能會 drop 整個 database，然後重新執行 `schema.sql`。在正式環境中，**你不能這樣做**。Database 裡有不能被刪除的真實使用者資料。

### 正式環境解法：Migration tools

**Migration** 是一個 versioned script，用來描述 schema 的*一個遞增變更*。每個變更，不管是新增 column、建立 table、加入 index，都會有自己的 migration file。

Migration tool（SQLAlchemy 用 **Alembic**、Java 用 **Flyway**、Django 用 **Django migrations**）會追蹤哪些 scripts 已經執行過，並且只套用新的 scripts。每個環境，不管是 developer laptop、staging server、production server，都會執行完全相同的 migration history，最後得到相同 schema。

每個工具使用自己的檔案格式。Flyway 使用帶有 version prefix 的 plain `.sql` files：

```text
migrations/
  V1__initial_schema.sql          ← creates all base tables
  V2__add_delay_records.sql       ← adds the delay_records table
  V3__add_user_accounts.sql       ← adds the user_accounts table
  V4__add_railcard_expiry.sql     ← adds a new column to users
```

Alembic（Python/SQLAlchemy 工具）則產生 Python scripts，放在 `versions/` folder 中，檔名自動產生：

```text
alembic/versions/
  a1b2c3d4_initial_schema.py
  e5f6a7b8_add_delay_records.py
```

兩種方法都使用相同的 CLI-driven workflow：

```bash
# 套用所有 pending migrations
alembic upgrade head

# 如果出錯，rollback 上一個 migration
alembic downgrade -1
```

### 延伸閱讀
- [Alembic Tutorial（官方）](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
- [Alembic — Auto Generating Migrations（官方）](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
- [Flyway — Database migrations documentation（Redgate）](https://documentation.red-gate.com/fd)

---

## Summary

| Topic | Teaching Code | Production Approach |
|---|---|---|
| **Connections** | 每個 query 建立新 connection | Connection pool（psycopg2 pool / PgBouncer） |
| **SQL location** | Functions 中的 inline strings | ORM、`.sql` files 或 query builder |
| **I/O model** | Synchronous（blocking） | Async（`asyncpg` + `async`/`await`） |
| **Passwords** | Plain text | `argon2` 或 `bcrypt` hash |
| **DB layer structure** | Standalone functions | Repository pattern（classes） |
| **Schema changes** | Drop and recreate | Versioned migrations（Alembic / Flyway） |

這些做法都不是說教學程式碼「錯了」，而是解決只有在 scale 或 security-sensitive contexts 中才會出現的問題。理解每個 practice *為什麼*存在，比死背工具更重要。

---

## Recommended Starting Points

如果你想在這門課後繼續深入，以下免費資源是不錯的下一步：

| Resource | 你會學到什麼 |
|---|---|
| [SQLAlchemy Tutorial（官方）](https://docs.sqlalchemy.org/en/20/orm/quickstart.html) | 從零開始學 ORM 與 query builder |
| [FastAPI SQL Databases Guide](https://fastapi.tiangolo.com/tutorial/sql-databases/) | 將真實 async API 連到 PostgreSQL |
| [Cosmic Python（free book）](https://www.cosmicpython.com/) | 包含 Repository 與 Unit of Work 的 architecture patterns |
| [OWASP Top 10](https://owasp.org/www-project-top-ten/) | 十大最常見 web security mistakes（SQL injection 是第 3 名） |
| [Real Python — Databases](https://realpython.com/tutorials/databases/) | 各種程度的實用 Python + database tutorials |
| [PostgreSQL Official Docs](https://www.postgresql.org/docs/current/) | PostgreSQL 一切內容的權威 reference |
