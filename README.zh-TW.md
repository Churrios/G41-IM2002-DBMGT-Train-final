# TransitFlow — 智慧鐵路助理
hahahahaha
> **課程起始專案** — 你們的工作是建立支撐這個 AI 助理運作的資料庫。
> AI 流程、網頁介面與資料庫連線都已經接好，而且可以運作。

---

## 目錄

1. [這是什麼專案？](#這是什麼專案) — TransitFlow 的概覽，以及你們要建置的內容
2. [三種資料庫](#三種資料庫以及各自的用途) — 為什麼分別使用 PostgreSQL、pgvector 與 Neo4j
3. [它實際上如何運作？](#它實際上如何運作完整流程) — 用真實範例完整走過端到端流程，包含 LLM 正規化步驟與 RAG 說明
4. [先決條件](#先決條件) — Docker、Python 與 LLM 需求
5. [設定](#設定只需做一次) — 一次性的安裝與啟動步驟，包含虛擬環境說明
6. [瀏覽資料庫](#瀏覽資料庫) — 登入 pgAdmin 與 Neo4j Browser 來檢查資料
7. [團隊合作](#最後團隊合作) — 讓隊友之間的資料庫狀態保持同步
8. [試試這些查詢](#試試這些查詢) — 用來確認一切正常運作的範例問題
9. [專案結構](#專案結構) — 檔案與資料夾配置總覽
10. [真實世界與教學用結構的差異](#這個結構與真實正式環境應用程式有何不同) — 本專案與正式產品程式碼庫的差異，以及為什麼這樣設計
11. [databases/ 資料夾](#databases-資料夾隨插即用元件) — 每個模組要編輯什麼，以及變更如何生效
12. [原始資料](#原始資料設計資料庫前請先研讀) — 設計 schema 前要先研究的來源檔案
13. [你們的任務](#你們的任務) — 需要完成的四項課程任務
14. [進階 — 擴充 Agent 或 UI](#進階擴充-agent-或-ui) — 為 agent 新增工具或修改 UI，請小心進行
15. [在 Ollama 與 Gemini 之間切換](#在-ollama-與-gemini-之間切換) — 如何更換 LLM 供應者，以及切換後要做什麼
16. [實用 URL](#實用-urldocker-執行時) — 本機服務位址快速參考
17. [疑難排解](#疑難排解) — 常見錯誤與修正方式
18. [Python 虛擬環境](#python-虛擬環境) — venv 是什麼、為什麼要用，以及如何設定

---

## 這是什麼專案？

TransitFlow 是一個可運作的 AI 聊天助理，服務對象是一個虛構的雙網路大眾運輸營運商。你可以輸入像這樣的問題：

- *「今天有沒有從 Central Station (NR01) 到 Ferndale (NR07) 的列車？」*
- *「我的火車延誤了 45 分鐘，我有權獲得什麼補償？」*
- *「如果 MS05 關閉，從 MS01 到 MS09 最快的地鐵路線是什麼？」*

助理會透過**查詢三種不同類型的資料庫**，並把結果整合成有幫助的回覆。你們的任務是理解這些資料庫、研究原始資料、設計 schema、填入資料，並進一步擴充它們。

---

## 三種資料庫以及各自的用途

這個專案的設計目的是展示你在什麼情況下會選擇各種資料庫類型，以及為什麼只用一種資料庫不夠。

| 資料庫 | 最擅長處理 | 在 TransitFlow 中儲存什麼 |
|---|---|---|
| **PostgreSQL**（關聯式） | 具有精確關係的結構化紀錄，例如數字、日期、外鍵 | 地鐵與國鐵車站、時刻表、座位配置、票價、使用者、國鐵訂票、地鐵旅程、付款 |
| **PostgreSQL + pgvector**（向量） | 依照「語意」而不是精確字詞尋找文件 | 公司政策文件，例如退費規則、鐵路優惠卡指南、無障礙資訊 |
| **Neo4j**（圖形） | 在網路中尋找路徑與連線 | 實體鐵路網路，也就是以車站為節點、鐵路連結為邊 |

**為什麼不能只用一種資料庫？** 沒有單一資料庫類型能把所有事情都做得很好：

- SQL 很適合回答 *「07:00 NR1 班次 (NR_SCH01) 還剩多少座位？」*，但要回答 *「從 London 到 Exeter，在任何車站轉乘都可以，最快路線是什麼？」* 就會很彆扭。
- 圖形資料庫能很自然地處理路線尋找，這正是它的設計目的，但它無法完成智慧文件搜尋所需的數學運算。
- 向量資料庫可以在使用者用意外的問法提問時，仍然根據「意思」而不是關鍵字找到正確的退費政策。但它不能管理座位訂位。

使用三種資料庫不是過度設計，而是為每項工作選擇正確工具。

---

## 它實際上如何運作？完整流程

以下精確說明從使用者送出訊息，到使用者看到答案之間發生的每一步。我們會用一個真實範例從頭到尾追蹤。

> **使用者輸入：** *「我在 2026-04-02 搭了 07:00 從 Central (NR01) 到 Stonehaven (NR05) 的車，延誤了 45 分鐘。我可以拿到補償嗎？」*

---

### 步驟 1 — 問題抵達網頁介面

使用者在 Gradio 聊天介面輸入內容，這段程式碼位於 `skeleton/ui.py`。訊息會被交給 agent。

---

### 步驟 2 — LLM 讀取問題並選擇要查詢哪些資料庫

`skeleton/agent.py` 會把問題送給 **LLM**（Large Language Model，大型語言模型，也就是 AI 大腦，可以是 Google Gemini 或本機 Ollama 模型）。LLM 會看到一份可用**工具**清單。你可以把工具想像成有標籤的按鈕，每個按鈕都連到一個資料庫查詢函式。LLM 會決定要按哪些按鈕。

針對這個問題，LLM 會選擇：

```text
Tool 1: get_user_bookings()
Tool 2: search_policy(query="compensation for delayed train 45 minutes")
```

這種讓 LLM 選擇要呼叫哪些函式的技術，稱為**工具使用**或**函式呼叫**。LLM 不會親自查詢資料庫；它只會發出指令，接著由 Python 程式碼執行。

> **Ollama 與 Gemini 的工具路由差異：** 使用 Ollama 時，agent 會使用模型原生的工具呼叫 API（`llm_provider.py` 中的 `ollama_tool_call`），這比要求小模型產生 JSON 更可靠。使用 Gemini 時，agent 會送出結構化 JSON 路由提示。兩條路徑最後都會產生相同的工具呼叫清單。

> **登入感知路由：** 如果使用者已登入，agent 會把使用者姓名、email 與 user ID 注入 system prompt。需要登入的工具（`get_user_bookings`、`make_booking`、`cancel_booking`）會自動使用已登入身分，LLM 不需要向使用者詢問 email 或 ID。

---

### 步驟 3 — 工具查詢真實資料庫

每個工具都對應到 `databases/relational/queries.py` 或 `databases/graph/queries.py` 中的一個 Python 函式：

**`get_user_bookings`** → 對 PostgreSQL 中的 `national_rail_bookings` 表執行 SQL

```sql
SELECT b.booking_id, b.travel_date, b.departure_time::text,
       b.amount_usd, b.status,
       orig.name AS origin_name, dest.name AS destination_name, ...
FROM national_rail_bookings b
JOIN national_rail_stations orig ON orig.station_id = b.origin_station_id
JOIN national_rail_stations dest ON dest.station_id = b.destination_station_id
WHERE b.user_id = 'RU01'
ORDER BY b.travel_date DESC
```

回傳原始 JSON：*`[{"booking_id": "BK001", "travel_date": "2026-04-02", ...}]`*

**`search_policy`** → 先把問題轉成向量，接著在 PostgreSQL（pgvector）的 `policy_documents` 中執行相似度搜尋

```sql
SELECT title, content,
       1 - (embedding <=> '[...query vector...]') AS similarity
FROM policy_documents
ORDER BY similarity DESC
LIMIT 3
```

回傳原始 JSON：*`[{"title": "Delay Compensation Policy", "content": "RF005: 30–59 minutes...", ...}]`*

---

### 步驟 4 — 原始結果被正規化成結構化、可讀的文字

每個工具回傳的原始 JSON 都會傳入一個 **Python 扁平化器**（`agent.py` 中的 `_normalise_result`），它會遞迴地把任何 JSON 結構轉成縮排的 key-value 文字。例如 Alice 的訂票結果會變成：

```text
[get_user_bookings]
national_rail:
  [1]
    booking_id: BK020
    travel_date: 2026-05-13
    origin_name: Bridgeport
    destination_name: Central Station
    fare_class: standard
    amount_usd: 4.00
    status: confirmed
  [2]
    booking_id: BK001
    ...
metro:
  [1]
    trip_id: MT009
    ...
```

這個正規化步驟就是為什麼**新增工具時，你不需要寫任何格式化程式碼**。扁平化器會自動處理任何 JSON 結構，不管巢狀深度或欄位名稱如何。它使用純 Python，沒有 LLM 參與，所以沒有模型幻覺、破壞資料或在轉換過程中漏掉紀錄的風險。

---

### 步驟 5 — LLM 組合最終答案

LLM 會讀取正規化後的資料摘要與原始問題，然後寫出最終回覆：

> *「我看到你有一筆 BK001 訂票，搭乘 2026 年 4 月 2 日 07:00 的 NR01 → NR05，票價 $8.50。依照延誤補償政策 (RF005)，延誤 30–59 分鐘可獲得票價 50% 的退費，也就是退回 $4.25。你可以在 28 天內透過 app 的『My Journeys → Claim Compensation』提交申請，或聯絡客服。」*

---

### 步驟 6 — 顯示答案

回覆會傳回 `skeleton/ui.py`，並顯示在聊天視窗中。

---

### 流程摘要圖

```text
User types a question
        │
        ▼
  skeleton/ui.py  (Gradio web chat — handles login/register state)
        │  current_user_email passed on every message
        ▼
  skeleton/agent.py  ◄──────────────────────── LLM (Gemini or Ollama)
        │                                               ▲  ▲  ▲
        │   [1] LLM reads question +                    │  │  │
        │       login context, picks tools ─────────────┘  │  │
        │   [2] Agent executes tools                        │  │
        │       against real databases                      │  │
        │   [3] Python flattener normalises ─────────────────┘  │
        │       raw JSON to readable text                       │
        │   [4] LLM writes the final answer ────────────────────┘
        │       using normalised data
        │
        ├── databases/relational/queries.py ──► PostgreSQL (port 5433)
        │                                          ├── Relational tables
        │                                          │     metro_stations, national_rail_stations,
        │                                          │     schedules, seat_layouts, users,
        │                                          │     national_rail_bookings, metro_travels
        │                                          └── Vector table
        │                                                policy_documents  (searched by meaning)
        │
        └── databases/graph/queries.py ─────► Neo4j (port 7688)
                                                 └── Graph network
                                                       MetroStation / NationalRailStation nodes,
                                                       METRO_LINK / RAIL_LINK / INTERCHANGE_TO edges
                                                       (route finding, delay ripple)
```

---

### 什麼是 RAG？（政策搜尋如何運作）

政策文件搜尋使用一種稱為 **RAG — Retrieval-Augmented Generation（檢索增強生成）** 的技術：

1. 當資料庫被 seed 時，每份政策文件會被轉換成一長串稱為**向量嵌入**的數字。這些數字以數學方式捕捉文字的「意思」。
2. 當使用者詢問政策問題時，該問題也會用同一種方法轉換成向量。
3. 資料庫會找出向量與問題向量最「接近」（最相似）的政策文件。
4. 這些文件會交給 LLM，LLM 會閱讀它們並用它們回答問題。

關鍵好處是：即使使用者的措辭與文件完全不同，它仍然能找到正確政策，因為比對的是意思，而不是關鍵字。

---

## 先決條件

- **Git** — [git-scm.com/downloads](https://git-scm.com/downloads)
  > 用來 clone repository。大多數 macOS 與 Linux 系統已預先安裝。Windows 使用者應下載並執行 Git 安裝程式。
- **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
  > Docker 會執行資料庫，讓你不必直接安裝 PostgreSQL 或 Neo4j。可以把它想成一個乾淨、獨立的盒子，裡面放著資料庫伺服器。
  > **Windows 使用者：** Docker Desktop 需要 WSL2（Windows Subsystem for Linux 2）。如果尚未啟用，請依照 [Docker 的 WSL2 設定指南](https://docs.docker.com/desktop/wsl/) 操作。
- **Python 3.10 或更新版本** — [python.org/downloads](https://www.python.org/downloads/)
  > 在 **Windows** 上，指令是 `python`。在 **macOS 與 Linux** 上，通常是 `python3`。本 README 中請使用你機器上可用的那個指令。
- **一個 LLM，二選一：**
  - **Ollama**（推薦，完全在你的筆電上執行，不需要 API key）：[ollama.com/download](https://ollama.com/download)
  - **Gemini**（替代方案，回應較快，但需要免費 API key）：[aistudio.google.com](https://aistudio.google.com/app/apikey)

---

## 設定只需做一次

> **推薦：** 在 Python 虛擬環境中執行本專案。它會把本專案套件與你電腦上的其他東西隔離，避免版本衝突。這不是強制要求，但這是良好實務，也是大多數專業 Python 開發者採用的方法。關於原因的完整說明，請看本檔底部的 [Python 虛擬環境](#python-虛擬環境)。

### 1. Clone repository、建立虛擬環境並安裝 Python 套件

```bash
git clone https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-final transitflow
cd transitflow
```

**推薦：先建立並啟用虛擬環境：**

**macOS / Linux：**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)：**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> **Windows PowerShell 注意事項：** 如果啟用失敗並顯示 "running scripts is disabled on this system"，請先在 PowerShell 執行一次以下指令，然後重試：
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

環境啟用時，終端機提示字元會變成顯示 `(.venv)`。接著把專案套件安裝到裡面：

```bash
pip install -r requirements.txt
```

> 如果你選擇不使用虛擬環境，請直接執行 `pip install -r requirements.txt`。但要注意，這會把套件安裝到系統 Python，可能和其他專案產生衝突。

### 2. 建立環境設定檔

```bash
cp .env.example .env
```

預設供應者是 **Ollama**，不需要 API key。如果你想改用 Gemini，請開啟 `.env`，設定 `LLM_PROVIDER=gemini`，然後貼上你的 `GEMINI_API_KEY`。

### 3. 啟動資料庫

```bash
docker compose up -d
```

這會在背景下載並啟動三個服務：
- **PostgreSQL** 在 port 5433 — 關聯式 + 向量資料庫
- **Neo4j** 在 port 7688 — 圖形資料庫
- **pgAdmin** 在 port 5051 — 用瀏覽器瀏覽與查詢 PostgreSQL 的 UI

關聯式資料庫 schema（表與索引）會在第一次啟動時自動從 `databases/relational/schema.sql` 載入。Seed data 會在下一步另外載入。

> **第一次執行時**，Docker 還必須下載資料庫映像檔（總計約 500 MB）。這可能會依照網路狀況花上數分鐘。之後再次啟動時，兩個容器通常會在 15–30 秒內準備好。
>
> **較舊的 Docker 安裝：** 如果 `docker compose` 無法辨識，請試試 `docker-compose`（有連字號）。建議把 Docker Desktop 更新到最新版。

等待兩個容器都準備好：

```bash
docker compose ps
```

兩個容器在 Status 欄都應顯示 `healthy`。

### 4. Seed 關聯式資料庫

> **你們的任務：** 在執行這一步前，你們需要實作 `skeleton/seed_postgres.py` 中的 seed 函式。連線設定與 helper functions 已經提供，你們要撰寫每個 `seed_*` 函式的內容。請參考 [你們的任務 — 撰寫 Seeding Scripts](#撰寫-seeding-scripts) 中的指引與範例。

實作完成後：

```bash
# macOS / Linux:
python3 skeleton/seed_postgres.py

# Windows (PowerShell):
python skeleton/seed_postgres.py
```

這會讀取 `train-mock-data/` 資料夾中的所有 mock data，並依照相依順序插入 PostgreSQL：stations → schedules → seat layouts → users → bookings → trips → payments → feedback。它使用 `ON CONFLICT DO NOTHING`，因此可以安全地重複執行。

### 5. Pull Ollama 模型並載入政策文件 embeddings

如果你使用 Ollama（預設），請先確認 Ollama 正在執行，並先 pull 所需模型。這只需要做一次：

```bash
ollama pull llama3.2:1b        # ~1.3 GB  — chat model
ollama pull nomic-embed-text   # ~274 MB  — embedding model for pgvector
```

接著 seed 向量資料庫：

```bash
# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

這會直接從 `train-mock-data/` 中的 JSON 檔（`refund_policy.json`、`ticket_types.json`、`booking_rules.json`、`travel_policies.json`）載入政策文件，使用 Ollama（`nomic-embed-text`）把每個項目轉換成向量嵌入，並把結果存入 PostgreSQL。

> 如果你改用 Gemini，請先在 `.env` 設定 `LLM_PROVIDER=gemini` 並加入你的 `GEMINI_API_KEY`，再執行這一步。你不需要 pull Ollama 模型。

### 6. 載入運輸網路圖

```bash
# macOS / Linux:
python3 skeleton/seed_neo4j.py

# Windows (PowerShell):
python skeleton/seed_neo4j.py
```

這會執行 `databases/graph/seed.cypher` 中的 Cypher 查詢，在 Neo4j 建立所有車站節點與鐵路連結邊。該檔案中的圖形拓撲來自 `train-mock-data/metro_stations.json` 與 `train-mock-data/national_rail_stations.json`；如果你需要擴充或修正圖形，請研究那些檔案。

### 7. 啟動助理

```bash
# macOS / Linux:
python3 skeleton/ui.py

# Windows (PowerShell):
python skeleton/ui.py
```

在瀏覽器開啟 **http://localhost:7860**。應該會看到 TransitFlow 聊天介面。

---

## 瀏覽資料庫

Docker 容器啟動後，你可以直接在瀏覽器檢查資料。這對確認 seeding 是否成功、以及開發時執行臨時查詢很有幫助。

### pgAdmin — PostgreSQL 瀏覽器

1. 在瀏覽器開啟 **http://localhost:5051**。
2. 使用以下資訊登入：
   - **Email:** `admin@admin.com`
   - **Password:** `admin`
3. 在左側欄右鍵點擊 **Servers → Register → Server…**
4. 填寫兩個分頁：

   **General tab**
   - Name: `TransitFlow`（或任何你喜歡的標籤）

   **Connection tab**
   - Host: `postgres`
   - Port: `5432`
   - Maintenance database: `transitflow`
   - Username: `transitflow`
   - Password: `transitflow`
   - 勾選 **Save password**

5. 點擊 **Save**。server 會出現在左側欄。
6. 展開 **Servers → TransitFlow → Databases → transitflow → Schemas → public → Tables** 來瀏覽所有表。
7. 若要執行 SQL 查詢，請右鍵點擊 `transitflow` database 並選擇 **Query Tool**。

> **為什麼這裡是 port 5432 而不是 5433？** pgAdmin 在 Docker 內執行，並透過 Docker 內部網路連到 PostgreSQL，在那裡 Postgres 使用原生 port 5432。Port 5433 只在從 Docker 外部連線時使用，例如從你的終端機或本機 Python script 連線。

---

### Neo4j Browser — 圖形視覺化工具

1. 在瀏覽器開啟 **http://localhost:7475**。
2. 將 connect URL 設為 `bolt://localhost:7688`（Bolt port 從預設 7687 被重新映射）。
3. 使用以下資訊登入：
   - **Username:** `neo4j`
   - **Password:** `transitflow`
4. 若要視覺化整個鐵路網路，貼上這段查詢並按 **Run (Ctrl+Enter)**：

   ```cypher
   MATCH (n)-[r]->(m) RETURN n, r, m
   ```

   點擊圖中的任何節點或邊即可檢查其 properties。

---

## 試試這些查詢

把以下內容貼到聊天介面，以確認一切正常運作：

```text
What national rail trains run from Central (NR01) to Stonehaven (NR05)?
```
→ 測試 PostgreSQL relational（針對 `national_rail_schedules` 的 `check_national_rail_availability`）

```text
What is the fastest metro route from MS01 to MS14?
```
→ 測試 Neo4j（透過 metro graph 依 `travel_time_min` 執行 Dijkstra）

```text
How do I get from Central Square (MS01) to Stonehaven (NR05)?
```
→ 測試 Neo4j 跨網路路由（METRO_LINK → INTERCHANGE_TO → RAIL_LINK）

```text
If Old Town station (NR03) is closed, what alternative routes exist from NR01 to NR05?
```
→ 測試 Neo4j（避開特定節點的替代路由）

```text
My train was delayed 45 minutes — what compensation am I entitled to?
```
→ 測試 pgvector RAG（延誤補償政策 RF005）

```text
What is the company policy on travelling with a bicycle on national rail?
```
→ 測試 pgvector RAG（旅遊政策文件，包含腳踏車、行李、寵物）

**認證感知查詢 — 請先登入（使用右上角 Register 或 Login 按鈕）：**

```text
Show my bookings
```
→ 測試 `get_user_bookings`，從 PostgreSQL 回傳你的訂票紀錄（新註冊使用者會是空的）

```text
Book me a standard ticket from Central Station (NR01) to Stonehaven (NR05) on 2026-06-01
```
→ 測試多步驟訂票流程：`check_national_rail_availability` → `get_available_seats` → `make_booking`

```text
Cancel booking BK-XXXXXX
```
→ 測試 `cancel_booking`，並依適用政策自動計算退款

在 UI 側邊欄啟用 **"Show database debug panel"**，即可看到實際呼叫了哪些工具、資料庫回傳了什麼，以及 LLM 如何正規化原始結果。

---

## 專案結構

```text
transitflow/
├── docker-compose.yml                  # 啟動 PostgreSQL + Neo4j + pgAdmin
├── requirements.txt
├── .env.example                        # 複製成 .env 並填入你的 API key
│
├── train-mock-data/                    #   來源 JSON 檔 — 設計 schema 前請先研究
│   ├── metro_stations.json
│   ├── national_rail_stations.json
│   ├── metro_schedules.json
│   ├── national_rail_schedules.json
│   ├── registered_users.json
│   ├── bookings.json
│   ├── metro_travel_history.json
│   ├── payments.json
│   ├── feedback.json
│   └── ...                             #   （政策 JSON 檔）
│
├── databases/                          # ← 你們的工作區
│   ├── relational/
│   │   ├── schema.sql                  # ← 編輯這個：table definitions（僅 DDL）
│   │   └── queries.py                  # ← 編輯這個：新增 SQL query functions
│   │
│   ├── graph/
│   │   ├── seed.cypher                 # ← 編輯這個：graph nodes 與 relationships
│   │   └── queries.py                  # ← 編輯這個：新增 Cypher query functions
│   │
│   └── vector/
│       └── documents.py                #   （已棄用，不再使用）
│
└── skeleton/                           # ← 不要編輯（除非你清楚自己在做什麼）
    ├── agent.py                        #   LLM orchestration 與 tool routing
    ├── ui.py                           #   Gradio 網頁介面
    ├── llm_provider.py                 #   LLM abstraction（Gemini / Ollama）
    ├── config.py                       #   環境設定（讀取 .env）
    ├── seed_postgres.py                #   將 train-mock-data/ JSON 檔載入 PostgreSQL
    ├── seed_neo4j.py                   #   執行 databases/graph/seed.cypher（graph data 來自 train-mock-data/ station JSONs）
    └── seed_vectors.py                 #   將 train-mock-data/ policy JSONs embedding 到 pgvector
```

---

## 這個結構與真實正式環境應用程式有何不同

本專案的資料夾配置是為了學習而刻意簡化。理解它與真實程式碼庫的差異，以及為什麼會有這些差異，能幫助你理解兩種世界。

### 正式環境程式碼庫通常會長什麼樣子

在真實系統中，如果使用三種資料庫，查詢程式碼通常會放在它所屬的功能旁邊，而不是依資料庫類型分組。典型的 Python service 可能會像這樣：

```text
transitflow/
├── api/                          # HTTP layer — FastAPI 或 Django REST
│   ├── routes/
│   │   ├── bookings.py           # POST /bookings, GET /bookings/{id}
│   │   ├── routes.py             # GET /routes?from=LDN&to=BRS
│   │   └── policies.py           # GET /policies/search?q=...
│   └── middleware/
├── services/                     # Business logic，這裡不包含資料庫知識
│   ├── booking_service.py
│   ├── routing_service.py
│   └── policy_service.py
├── repositories/                 # 每個資料庫關注點一個檔案
│   ├── postgres/
│   │   ├── bookings_repo.py      # bookings 與 users 的 SQL
│   │   └── pricing_repo.py
│   ├── neo4j/
│   │   └── network_repo.py       # route finding 使用的 Cypher
│   └── vector/
│       └── policy_repo.py        # pgvector similarity search
├── migrations/                   # 遞增式 schema changes（Alembic / Flyway）
│   ├── 001_initial_schema.sql
│   ├── 002_add_loyalty_points.sql
│   └── 003_add_operators_table.sql
├── tests/
│   ├── unit/
│   └── integration/              # Tests 會打到真實的 test databases
├── infrastructure/               # Docker, Kubernetes, Terraform
└── config/
    ├── settings_dev.py
    ├── settings_staging.py
    └── settings_prod.py          # Secrets 從 Vault / AWS Secrets Manager 載入
```

與本專案的主要差異：

| 面向 | 本專案 | 正式環境實務 |
|---|---|---|
| **Schema changes** | 編輯 `schema.sql`，接著用 `docker compose down -v` 清空並重建 | Migration files，一次變更一個檔案，逐步套用且不造成資料遺失 |
| **Query code location** | 依資料庫類型分組（`databases/relational/`、`databases/graph/`） | 依業務領域分組（`repositories/bookings/`、`repositories/routing/`） |
| **Seeding data** | 手動執行 scripts | 由 CI pipeline 或專門的 seed/fixture framework 處理 |
| **Configuration** | 一個 `.env` 檔 | dev/staging/prod 分別有不同 config；secrets 由 vault 管理，絕不放在檔案中 |
| **Web interface** | Gradio，一個 Python 檔，沒有 frontend code | 專用 frontend（React、Vue）與 REST 或 GraphQL API 溝通 |
| **The agent** | 單一 `agent.py` | 可能是獨立 microservice 或託管 AI 平台（例如 AWS Bedrock、Google Vertex AI） |
| **LLM provider** | 透過環境變數切換 | 包裝在版本化 API contract 後面；模型升級會經過分階段 rollout |
| **Testing** | 手動，執行 app 並輸入查詢 | 自動化 unit、integration 與 end-to-end tests，在每次 commit 時由 CI 執行 |

### 為什麼本專案使用較簡單的結構

本專案的目標是教你**何時以及為什麼**選擇每種資料庫類型，而不是教軟體架構。每個結構上的決策，都是為了讓焦點保持清楚：

- **`databases/` 依資料庫類型分組，而不是依功能分組** — 因此每個資料夾都是聚焦、獨立的學習單元。你可以在不碰圖形或向量程式碼的情況下處理關聯式資料庫。
- **使用單一 `schema.sql` 檔，而不是 migrations** — migrations 在正式環境中是正確工具，但它們會增加一層間接性。單一檔案讓你能一眼看到整個資料模型，並把它當成整體來推理。
- **`skeleton/` 包含所有預先建立的程式碼** — 這個界線是刻意設計的。它清楚告訴你負責什麼，也讓你不必先理解 LLM orchestration 或 UI code，就能開始處理資料庫。
- **使用 Gradio 而不是完整 API + frontend** — 正式 UI 需要花好幾天設定。Gradio 讓你用一個指令就得到可運作、可互動的介面，焦點因此能停留在資料庫上。
- **手動 seed scripts，而不是 migration/fixture framework** — 自己執行 `python skeleton/seed_vectors.py` 會讓 seeding 過程可見且容易 debug。在正式環境中，這通常會藏在 deployment pipeline 裡，反而比較不容易學習。

當你離開這門課並建立真實系統時，自然會超越這些簡化。本專案的結構是一個教學腳手架。它有用，正是因為它讓事情保持可見且分離，即使這不是你實際要交付給使用者的系統會採用的組織方式。

我們也提供了三種資料庫正式環境實務的補充說明：關聯式、向量與圖形資料庫。[可在專案根目錄找到]

- Relational Database: [SideNote1-RelationalDBPractices.md](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/blob/master/SideNote1-RelationalDBPractices.md)
- Vector Database: [SideNote2-VectorDBPractices.md](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/blob/master/SideNote2-VectorDBPractices.md)
- Graph Database: [SideNote3-GraphDBPractices.md](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/blob/master/SideNote3-GraphDBPractices.md)

---

## databases/ 資料夾隨插即用元件

`databases/` 中的每個子資料夾都是一個自包含元件。`skeleton/` 中的 AI pipeline 會自動從它們 import；你只需要修改 `databases/` 裡面的檔案，就能擴充助理能做的事。

把每個資料庫資料夾想成一個**隨插即用模組**：

| 資料夾 | 你控制什麼 | 變更如何生效 |
|---|---|---|
| `databases/relational/` | SQL schema 與查詢函式 | 編輯 `schema.sql`，接著 reset database（見下方）。編輯 `queries.py` 來新增 Python 查詢函式。 |
| `databases/graph/` | 圖形拓撲與 Cypher 查詢 | 編輯 `seed.cypher` 來新增 nodes 與 edges（資料來源是 `train-mock-data/` 的 station JSONs）。編輯 `queries.py` 來新增 Cypher 查詢函式。 |
| `databases/vector/` | 助理知道的政策文件 | 編輯 `train-mock-data/` 中的 policy JSON files 來新增或更新文件，接著重新執行 seed script。 |

### 關聯式資料庫（PostgreSQL）

**要編輯的檔案：** `databases/relational/schema.sql`

這個檔案定義所有表與索引（僅 DDL，沒有資料）。先研究 `train-mock-data/` 中的 JSON 檔，理解資料模型。Seed data 會由 `skeleton/seed_postgres.py` 另外載入。

擴充想法：
- 新增 `delay_records` table，記錄營運商回報的每個服務延誤
- 新增 `season_tickets` table，處理 weekly、monthly 與 annual metro passes
- 新增 `platform_assignments` table，記錄每個服務從哪個月台出發
- 在 `users` table 新增 `loyalty_points` 欄位
- 新增 `disruptions` table，處理計畫性工程

任何 schema 變更後，reset 並重新載入資料庫：
```bash
docker compose down -v && docker compose up -d
```

**要編輯的檔案：** `databases/relational/queries.py`

依照現有 pattern 在這裡新增 Python 函式。任何以 `query_` 開頭的函式都可以被註冊成 agent 的工具（請看下方 Advanced section）。

---

### 圖形資料庫（Neo4j）

**要編輯的檔案：** `databases/graph/seed.cypher`

這個 Cypher 檔會建立所有 `MetroStation` 與 `NationalRailStation` 節點，以及 `METRO_LINK`、`RAIL_LINK`、`INTERCHANGE_TO` 邊。請研究 `train-mock-data/metro_stations.json` 與 `train-mock-data/national_rail_stations.json` 來理解網路拓撲。

擴充想法：
- 新增 `BUS_LINK` relationship type，把 bus stops 連到 metro 或 rail stations
- 新增更多 metro stations 並延伸現有路線
- 在 nodes 加入 zone properties（zone 1、2、3），用於分區票價計算
- 新增 `OPERATED_BY` relationship，將 stations 連到 operators
- 在 nodes 加入 `CLOSED` property，用於即時 disruption modeling

編輯 Cypher seed 檔後：
```bash
# macOS / Linux:
python3 skeleton/seed_neo4j.py

# Windows (PowerShell):
python skeleton/seed_neo4j.py
```

**要編輯的檔案：** `databases/graph/queries.py`

依照現有 pattern 在這裡新增 Cypher 查詢函式。

---

### 向量資料庫（pgvector / RAG）

**要編輯的檔案：** `train-mock-data/` 中的政策 JSON 檔（`refund_policy.json`、`ticket_types.json`、`booking_rules.json`、`travel_policies.json`）。

依照每個檔案的既有結構新增 entries。

擴充想法：
- 遺失物政策
- 團體訂票折扣（國鐵 10 人以上）
- 無障礙與協助旅行
- 工程與計畫性 disruption
- 罰款票價與逃票

新增或修改文件後：
```bash
# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

> 如果你在 seeding 後切換供應者（Ollama ↔ Gemini），必須重新執行 seed script（macOS/Linux 用 `python3 skeleton/seed_vectors.py`，Windows 用 `python skeleton/seed_vectors.py`）。embedding model 會隨供應者改變，已儲存的 vectors 將無法與新模型產生的 queries 相符。

---

## 原始資料設計資料庫前請先研讀

所有來源資料都以結構化 JSON 檔存放在 `train-mock-data/` 資料夾。開始 schema 或 graph design 任務前，請先研究這些檔案。

| 檔案 | 內容 |
|---|---|
| `metro_stations.json` | 20 個 metro stations（MS01–MS20）、路線、interchange flags、相鄰車站清單 |
| `national_rail_stations.json` | 10 個 national rail stations（NR01–NR10）、路線、連到 metro 的 interchange links |
| `metro_schedules.json` | M1–M4 路線的 metro timetables：stops、fares、frequencies、operating days |
| `national_rail_schedules.json` | NR1–NR2 的 national rail timetables：normal 與 express services、fare classes |
| `national_rail_seat_layouts.json` | 每個 national rail schedule 的車廂與座位圖 |
| `registered_users.json` | 20 個虛構使用者，包含 profile 與 authentication fields |
| `bookings.json` | 所有使用者的 national rail booking history |
| `metro_travel_history.json` | Metro trip history（single tickets 與 day passes） |
| `payments.json` | national rail 與 metro transactions 的付款紀錄 |
| `feedback.json` | 乘客評分與評論 |
| `refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` | 會嵌入 pgvector 用於 RAG 的政策文件。編輯這些檔案可擴充助理知識，接著重新執行 `seed_vectors.py`。 |

**研究資料時可以問自己的問題：**

- 哪些欄位在很多 records 中重複？那些可能適合成為自己的 table。
- 每筆 record 的唯一識別是什麼，也就是自然 primary key 是什麼？
- Records 彼此如何關聯？那些關係會變成 foreign keys。
- 哪些車站連線比較適合表示成一個「網路」，而不是一張 rows table？
- 哪些政策內容需要依照「意思」而不是精確關鍵字搜尋？

---

## 你們的任務

**必做：你們必須編輯這些檔案才能完成專案：**

| 檔案 | 要做什麼 | 狀態 |
|---|---|---|
| `skeleton/seed_postgres.py` | 實作每個 `seed_*` 函式，將 JSON 資料載入 PostgreSQL tables | ✅ 10 個函式，ON CONFLICT DO NOTHING |
| `skeleton/seed_neo4j.py` | 實作 `seed()` 函式，在 Neo4j 建立車站 nodes 與 rail link relationships | ✅ 完成，使用 MERGE |
| `databases/relational/schema.sql` | 為所有 relational data 設計並撰寫 table definitions（DDL） | ✅ 7 張表 + indexes + FKs |
| `databases/relational/queries.py` | 新增查詢 PostgreSQL tables 的 Python 函式 | ✅ 15 個函式已實作 |
| `databases/graph/seed.cypher` | 定義 graph topology，也就是 station nodes 與它們之間的 links | ⚠️ 已廢棄，改由 seed_neo4j.py 負責 |
| `databases/graph/queries.py` | 新增對 Neo4j 執行 Cypher 查詢的 Python 函式 | ✅ 6 個函式已實作 |
| `train-mock-data/refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` | 新增或擴充 policy entries，讓助理能回答更多政策問題 | ⚠️ 使用原始提供的內容，未額外擴充 |

**選做：你可以編輯這些檔案以加入延伸功能：**

| 檔案 | 可以做什麼 |
|---|---|
| `skeleton/agent.py` | 將新的 query functions 註冊成 tools，讓 AI 可以呼叫 |
| `skeleton/ui.py` | 自訂聊天介面，例如 layout、example queries、display options |

---

### 撰寫 Seeding Scripts

有兩個 seeding scripts 留給你們實作：

- `skeleton/seed_postgres.py` — 讀取 `train-mock-data/` 的 JSON 檔，並插入 rows 到 PostgreSQL tables
- `skeleton/seed_neo4j.py` — 讀取 station JSON files，並在 Neo4j 建立 nodes 與 relationships

連線設定、helper functions 與整體呼叫順序都已經放好。**你們的工作是實作每個 `seed_*` 函式**，從已載入的 JSON 中取出正確欄位並撰寫 insert logic。

---

#### PostgreSQL seeder (`seed_postgres.py`)

每個 `seed_*` 函式都會收到一個開啟中的 cursor。使用 `insert_many` helper 來 bulk-insert rows。你傳入的欄位名稱必須與 `schema.sql` 中的 table definition 完全相符。

**基本範例 — 插入 flat records：**

```python
def seed_metro_stations(cur):
    data = load("metro_stations.json")
    rows = [
        (s["station_id"], s["name"], s["zone"])
        for s in data
    ]
    n = insert_many(cur, "metro_stations", ["station_id", "name", "zone"], rows)
    print(f"  metro_stations: {n} rows")
```

**巢狀範例 — 展開每筆 record 內部的 list：**

有些 JSON 欄位是巢狀 list，例如 schedule 中包含多個 stops。把外層 list 與內層 list 一起 loop，為每個 stop 產生一列：

```python
def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    rows = []
    for schedule in data:
        for stop in schedule["stops"]:
            rows.append((
                schedule["schedule_id"],
                stop["station_id"],
                stop["arrival_time"],
                stop["stop_order"],
            ))
    n = insert_many(cur, "metro_schedule_stops",
                    ["schedule_id", "station_id", "arrival_time", "stop_order"], rows)
    print(f"  metro_schedule_stops: {n} rows")
```

`insert_many` 會產生單一 `INSERT … VALUES %s ON CONFLICT DO NOTHING`，因此可以安全地重複執行任意次。

---

#### Neo4j seeder (`seed_neo4j.py`)

在 `seed()` 函式中，使用 `session.run()` 執行 Cypher。使用 `MERGE` 而不是 `CREATE`，這樣重跑時不會產生重複 nodes 或 relationships。

**建立 nodes：**

```python
for s in metro_stations:
    session.run(
        "MERGE (n:MetroStation {station_id: $id}) "
        "SET n.name = $name, n.zone = $zone",
        id=s["station_id"], name=s["name"], zone=s.get("zone"),
    )
print(f"  Created {len(metro_stations)} MetroStation nodes")
```

**建立 nodes 之間的 relationships：**

每個 metro station 都列出它的 adjacent stations。Loop 過它們來建立 directed links：

```python
for s in metro_stations:
    for adj in s.get("adjacent_stations", []):
        session.run(
            "MATCH (a:MetroStation {station_id: $from_id}) "
            "MATCH (b:MetroStation {station_id: $to_id}) "
            "MERGE (a)-[r:METRO_LINK {line: $line}]->(b) "
            "SET r.travel_time_min = $time",
            from_id=s["station_id"], to_id=adj["station_id"],
            line=adj["line"], time=adj["travel_time_min"],
        )
print("  Created metro links")
```

撰寫 seeder 前，請仔細研究 `train-mock-data/` 中的每個 JSON 檔。JSON 中的 fields 會成為 table 中的 columns（PostgreSQL），或 nodes 與 relationships 上的 properties（Neo4j）。

---

### Task 1 — 設計並擴充關聯式 Schema（PostgreSQL）

**要編輯的檔案：** `databases/relational/schema.sql`、`databases/relational/queries.py`

研究 `train-mock-data/` 中的 JSON 檔，接著依照上方說明擴充 schema 並新增 query functions。

SQL schema 檔有任何變更後：
```bash
docker compose down -v && docker compose up -d

# macOS / Linux:
python3 skeleton/seed_postgres.py

# Windows (PowerShell):
python skeleton/seed_postgres.py
```

### Task 2 — 豐富圖形資料庫（Neo4j）

**要編輯的檔案：** `databases/graph/seed.cypher`、`databases/graph/queries.py`

研究 `train-mock-data/metro_stations.json` 與 `train-mock-data/national_rail_stations.json`，接著依照上方說明擴充 graph 並新增 Cypher query functions。

編輯 seed file 後：
```bash
# macOS / Linux:
python3 skeleton/seed_neo4j.py

# Windows (PowerShell):
python skeleton/seed_neo4j.py
```

### Task 3 — 新增政策文件（pgvector / RAG）

**要編輯的檔案：** `train-mock-data/` 中的 policy JSON files。依照既有結構新增 entries。

新增 documents 後：
```bash
# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

### Task 4 — 撰寫新的 Query Functions

**要編輯的檔案：** `databases/relational/queries.py`、`databases/graph/queries.py`

依照那些檔案裡已有的 pattern 新增函式。若要讓 agent 使用新函式，請看下方 Advanced section。

---

## 進階擴充 Agent 或 UI

> **請自行承擔風險。** `skeleton/` 中的檔案是刻意完整且可運作的。完成課程任務不需要編輯它們，這裡的錯誤可能會破壞整個系統。修改前請先備份。

### 新增一個工具到 agent

如果你已經在 `databases/relational/queries.py` 或 `databases/graph/queries.py` 寫了一個新的 query function，並希望 AI 能呼叫它，你需要在 `skeleton/agent.py` 做四個小改動。你**不需要**寫任何格式化或摘要程式碼，pipeline 會自動把原始 JSON 結果轉成 plain English。

---

**Step 1 — 匯入你的函式**，放在檔案頂部既有 imports 旁邊：

```python
from databases.relational.queries import (
    query_national_rail_availability,
    # ... existing imports ...
    your_new_function,          # 加入這個
)
```

---

**Step 2 — 在 `TOOLS` list 加入 tool definition**。這是 LLM 用來判斷何時以及如何呼叫你的工具的資訊。描述請寫成清楚的觸發語句。越精準，LLM 越能可靠地在正確時機呼叫工具：

```python
{
    "name": "your_tool_name",
    "description": (
        "One or two sentences explaining what this tool does. "
        "Include the exact kinds of question that should trigger it, e.g. "
        "'Use when the user asks about platform numbers or departure boards.'"
    ),
    "parameters": {
        "param_one": {"type": "string", "description": "What this parameter is, e.g. station ID like NR01"},
        "param_two": {"type": "string", "description": "What this parameter is"},
    },
    "required": ["param_one"],
},
```

---

**Step 3 — 在 `TOOLS_SCHEMA` 加入一行**（這是 `TOOLS` list 下方幾行、Gemini JSON router 使用的 compact text summary）：

```python
TOOLS_SCHEMA = """\
...existing tools...
your_tool_name(param_one, param_two?)"""
```

使用 `?` 標示 optional parameters。

---

**Step 4 — 在 `_execute_tool` 函式中接上 execution**，依照所有既有工具使用的相同 `elif` pattern：

```python
elif tool_name == "your_tool_name":
    result = your_new_function(**params)
```

就是這樣。pipeline 的 Python 扁平化器（`agent.py` 中的 `_normalise_result`）會自動把你的函式回傳的任何 JSON 轉成結構化、可讀的文字，不需要格式化程式碼。

---

**Optional Step 5 — 新增 Ollama routing hint**（只有在使用小型本機模型時，LLM 無法可靠呼叫你的工具才需要）：

在 `run_agent()` 中找到 `ollama_tool_call` system prompt string，並加入一行 hint：

```python
system_prompt=(
    "...existing hints..."
    "Platform/departure board questions → your_tool_name. "   # 加入這個
    ...
),
```

你可以在 UI 啟用 **"Show database debug panel"** 來確認工具是否被呼叫。它會顯示 tool selection output、raw database result，以及 LLM 針對每個回合產生的 data summary。

---

**完整範例** — 新增一個查詢月台號碼的工具：

```python
# Step 1：在 agent.py 頂部的 imports 中
from databases.relational.queries import (
    ...,
    query_platform_assignment,
)

# Step 2：在 TOOLS list 中
{
    "name": "get_platform",
    "description": (
        "Look up the platform number for a national rail service at a station. "
        "Use when the user asks which platform to go to, or about departure boards."
    ),
    "parameters": {
        "station_id":   {"type": "string", "description": "Station ID e.g. NR01"},
        "schedule_id":  {"type": "string", "description": "Schedule ID e.g. NR_SCH01"},
    },
    "required": ["station_id", "schedule_id"],
},

# Step 3：在 TOOLS_SCHEMA 中
"get_platform(station_id, schedule_id)"

# Step 4：在 _execute_tool 中
elif tool_name == "get_platform":
    result = query_platform_assignment(**params)
```

---

### 修改 UI

聊天介面位於 `skeleton/ui.py`，使用 [Gradio](https://www.gradio.app/) 建立。如果你想改 layout、新增 example queries 或加入新的 UI controls，只需要編輯這個檔案。

可以安全修改的 `skeleton/ui.py` 內容：
- `EXAMPLES` list — 新增或移除側邊欄中可點擊的 example queries
- `gr.Markdown()` 中的 title 與 description text
- UI layout（column widths、number of rows、colour theme）

不應在未理解影響的情況下修改的 `skeleton/ui.py` 內容：
- `chat()` function — 它會呼叫 `run_agent()` 並管理 conversation history
- `agent_history_state` state variable — 移除它會破壞 multi-turn conversation
- `debug_panel` 與 `debug_toggle` — 它們已連到 agent 的 debug output

---

## 在 Ollama 與 Gemini 之間切換

**Ollama**（預設，本機執行、不需要 API key、不需要網路）：
```bash
# 從 https://ollama.com/download 安裝 Ollama，接著 pull 所需模型：
ollama pull llama3.2:1b        # ~1.3 GB  — chat model
ollama pull nomic-embed-text   # ~274 MB  — embedding model for pgvector
```
```env
LLM_PROVIDER=ollama
```

**Gemini**（替代方案，回應較快，需要免費 API key）：
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Gemini 的 embedding model 會產生 **3072 維** vectors。Schema 預設為 **768**（Ollama）。如果你切換到 Gemini，reset database 前也必須更新 `databases/relational/schema.sql`：

```sql
-- 在 policy_documents table definition 中修改這一行：
embedding   vector(3072),
```

接著 reset database 並重新 seed：
```bash
docker compose down -v && docker compose up -d

# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

> **重要：** 如果你在 seeding vector database 後切換供應者，必須永遠重新執行 seed script。embedding model 會隨供應者改變，已儲存的 vectors 將無法與新模型產生的 queries 相符。

---

## 實用 URL（Docker 執行時）

| 服務 | URL | 登入資訊 |
|---|---|---|
| TransitFlow Chat UI | http://localhost:7860 | — |
| Neo4j Browser（graph visualiser） | http://localhost:7475 | neo4j / transitflow |
| pgAdmin（PostgreSQL browser UI） | http://localhost:5051 | admin@admin.com / admin |
| PostgreSQL（direct connection） | localhost:5433 | transitflow / transitflow |

### 將 pgAdmin 連到 PostgreSQL

1. 開啟 **http://localhost:5051**，並用 `admin@admin.com` / `admin` 登入
2. 在左側欄右鍵點擊 **Servers → Register → Server…**
3. 填寫兩個分頁：

   **General tab**
   - Name: `TransitFlow`（或任何你喜歡的標籤）

   **Connection tab**
   - Host: `postgres`
   - Port: `5432`
   - Maintenance database: `transitflow`
   - Username: `transitflow`
   - Password: `transitflow`
   - 勾選 **Save password**

4. 點擊 **Save**，server 會出現在側邊欄。展開它即可在 **Databases → transitflow → Schemas → public → Tables** 下瀏覽 tables。

若要執行 SQL query，請右鍵點擊 database 並選擇 **Query Tool**。

---

若要在 Neo4j Browser 視覺化整個鐵路網路，貼上這段查詢：
```cypher
MATCH (n)-[r]->(m) RETURN n, r, m
```

---

## 疑難排解

**"Cannot connect to Neo4j"** — Neo4j 啟動最多需要 30 秒。請等待後重試。

**"GEMINI_API_KEY is not set"** — 你設定了 `LLM_PROVIDER=gemini` 但沒有 key。請把 key 加到 `.env`，或切換為 `LLM_PROVIDER=ollama` 以便不使用 key 執行。

**"Cannot reach Ollama"** — Ollama 沒有執行。請從 Applications 資料夾或 system tray 啟動它，然後重試。

**"embedding dimension mismatch"** — 資料庫中儲存的 vector 維度與目前 active embedding model 不一致。你可能在 seeding 後切換供應者，或 `schema.sql` 仍宣告錯誤維度。確認 `schema.sql` 對 Ollama 使用 `vector(768)`，對 Gemini 使用 `vector(3072)`，reset database（`docker compose down -v && docker compose up -d`），接著重新執行 `python skeleton/seed_vectors.py`。

**Docker containers won't start** — 確認 Docker Desktop 已開啟且正在執行。接著試試：`docker compose down -v && docker compose up -d`

**Gradio shows an error on startup** — 查看終端機中的 Python traceback。最常見原因是缺少 `.env` 檔，或 database container 尚未完全 ready。

**`pip install` works but `python skeleton/ui.py` says "ModuleNotFoundError"** — 你的虛擬環境沒有啟用。執行 `source .venv/bin/activate`（macOS/Linux）或 `.venv\Scripts\Activate.ps1`（Windows PowerShell）後再試一次。

**Windows PowerShell says "running scripts is disabled"** — 先執行以下指令一次，然後重試 activation：
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**`python` not found on macOS or Linux** — 改用 `python3`。在這些系統上，`python` 可能指向 Python 2，或根本不存在。本 README 中所有 `python` commands 都可以替換成 `python3`。

---

## Python 虛擬環境

### 什麼是虛擬環境？

當你用 `pip install` 安裝 Python packages 時，它們會被放在你電腦上的某個位置。沒有虛擬環境時，它們會進入你的**系統 Python**，也就是作業系統、其他專案，以及你可能甚至不知道的工具共同使用的全域位置。

**虛擬環境**（venv）會為單一專案建立一份私有、隔離的 Python copy。安裝在其中的 packages 會留在其中。你的系統 Python 不會被碰到。如果你刪除專案，也會一起刪除該環境，不需要額外清理。

```text
Without venv                         With venv
────────────────────────────────     ───────────────────────────────────
System Python                        System Python  (unchanged)
  └── site-packages/                   └── site-packages/  (unchanged)
        requests==2.28                        ← nothing added here
        gradio==4.0
        neo4j==5.0                   transitflow/.venv/
        psycopg2==2.9                  └── site-packages/
        (used by ALL projects)               requests==2.28
                                             gradio==4.0
                                             neo4j==5.0
                                             psycopg2==2.9
                                             (used ONLY by this project)
```

### 為什麼這對本專案很重要

本專案會安裝特定版本的 `gradio`、`neo4j`、`psycopg2`、`google-genai` 與其他套件。如果你在同一台機器上處理其他 Python 專案，那些專案可能需要同一套件的不同版本。沒有隔離時，安裝某個專案的 requirements 可能會在你沒注意到的情況下破壞另一個專案。

虛擬環境可以完全避免這件事。每個專案都有自己的 sandbox。

### `apt install` 與 `pip install` 有什麼不同？

你可能看過這兩個指令，並想知道何時該用哪個。

**`apt install`**（僅 Debian/Ubuntu Linux）是你的**作業系統** package manager。它會在系統層級安裝軟體，不只是 Python packages，也包含 OS 需要的任何程式、library 或工具。當你要安裝整台機器都需要的東西時使用它：

```bash
# 安裝 Python 本身或系統層級工具
sudo apt install python3
sudo apt install python3-pip
sudo apt install postgresql-client
```

`apt` packages 會針對你的 OS distribution 測試相容性。它們通常會刻意比最新版稍微落後，因為在系統層級穩定性比新穎性更重要。

**`pip install`** 是 **Python 的** package manager。它會從 [PyPI](https://pypi.org)（Python Package Index）把 packages 安裝到目前 active 的 Python environment 中。當你要安裝程式碼會 import 的 Python library 時使用它：

```bash
# 安裝你的程式碼會 import 的 Python libraries
pip install gradio
pip install psycopg2-binary
pip install neo4j
```

關鍵差異是：`apt` 管理你的機器；`pip` 管理你的 Python 專案。對應用程式開發來說，在虛擬環境裡使用 `pip`，就是管理所有 Python dependencies 的方式。`apt` 只有在安裝 Python 本身，或資料庫 client 之類的系統層級 prerequisites 時才需要。

| | `apt install` | `pip install` |
|---|---|---|
| 安裝什麼 | System software 與 OS-level libraries | 給你的程式使用的 Python packages |
| Packages 放哪裡 | System directories（`/usr/lib` 等） | Active Python environment |
| 由誰維護 | 你的 Linux distribution | Python community（PyPI） |
| 何時使用 | 安裝 Python、system tools、drivers | 安裝專案 import 的 libraries |
| 需要 `sudo` 嗎？ | 需要 | 不需要（在 venv 中） |

### 為本專案設定虛擬環境

**Step 1 — 建立環境**（clone 後做一次）：

**macOS / Linux：**
```bash
cd transitflow
python3 -m venv .venv
```

**Windows (PowerShell)：**
```powershell
cd transitflow
python -m venv .venv
```

這會在專案中建立 `.venv/` 資料夾。它包含一個私有 Python interpreter 與空的 `site-packages/` 目錄。此資料夾列在 `.gitignore` 中，永遠不應 commit。

**Step 2 — 啟用它**（每次開新 terminal 都要做）：

**macOS / Linux：**
```bash
source .venv/bin/activate
```

**Windows (PowerShell)：**
```powershell
.venv\Scripts\Activate.ps1
```

> **Windows PowerShell 注意事項：** 如果啟用失敗並顯示 "running scripts is disabled"，請先執行一次以下指令再重試：
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

你的 prompt 會變成顯示 `(.venv)`，作為確認。啟用期間，`python` 與 `pip` 會指向該環境的私有 copy，而不是系統版本。

**Step 3 — 安裝專案 packages：**

```bash
pip install -r requirements.txt
```

所有 packages 都會進入 `.venv/site-packages/`。你的系統 Python 不會被碰到。

**Step 4 — 完成後停用**（選用）：

```bash
deactivate
```

### 快速參考

| 任務 | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| 建立環境 | `python3 -m venv .venv` | `python -m venv .venv` |
| 啟用 | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| 安裝專案 packages | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| 查看已安裝 packages | `pip list` | `pip list` |
| 停用 | `deactivate` | `deactivate` |
| 刪除環境 | `rm -rf .venv` | 刪除 `.venv\` 資料夾 |

### 虛擬環境與 IDE

大多數 IDE 會自動偵測並使用虛擬環境：

- **VS Code** — 開啟專案資料夾，按 `Ctrl+Shift+P`，選擇 **Python: Select Interpreter**，並選擇標示 `.venv` 的項目。VS Code 之後會讓所有 terminals 與 debugger 使用它。
- **PyCharm** — 前往 Settings → Project → Python Interpreter → Add Interpreter → Existing → 指向 `.venv/bin/python`（macOS/Linux）或 `.venv\Scripts\python.exe`（Windows PowerShell）。

IDE 設定好後，你不需要在 integrated terminal 手動啟用環境，它會自動啟用。

---

## 最後團隊合作

### Git 追蹤什麼以及不追蹤什麼

Docker volumes 不是 git repository 的一部分。每位隊友的資料庫資料都只存在自己的機器上。**Git 只追蹤定義資料的檔案**，不追蹤資料本身。

| 項目 | Git 會追蹤嗎？ | 備註 |
|---|---|---|
| `databases/relational/schema.sql` | 是 | Tables、constraints 與所有 seed data |
| `databases/graph/seed.cypher` | 是 | Station nodes 與 rail link edges |
| `train-mock-data/refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` | 是 | 要被 embedded 的 policy documents |
| `databases/*/queries.py` | 是 | Python query functions |
| `.env` | **否**（gitignored） | 每位隊友各自根據 `.env.example` 建立自己的 copy |
| Docker volume data | **否** | 只由 Docker 存在你的本機 |

這代表：如果隊友修改 `schema.sql` 並 push 到 git，你正在執行的資料庫不會自動受影響，除非你明確 reset 並 reload。

---

### 黃金法則

> **如果 git 中的 seed file 有變更，就 reset 你的資料庫。**

每次 `git pull` 後，檢查三個 seed files 是否有變更，並採取對應動作：

```bash
# 查看隊友修改了哪些 seed files：
git diff HEAD~1 HEAD -- databases/relational/schema.sql databases/graph/seed.cypher train-mock-data/refund_policy.json train-mock-data/ticket_types.json train-mock-data/booking_rules.json train-mock-data/travel_policies.json
```

| 變更的檔案 | 要執行的指令 |
|---|---|
| `databases/relational/schema.sql` | `docker compose down -v && docker compose up -d`，接著 `python skeleton/seed_postgres.py` |
| `skeleton/seed_postgres.py`（或任何 `train-mock-data/*.json`） | `python skeleton/seed_postgres.py` |
| `databases/graph/seed.cypher` | `python skeleton/seed_neo4j.py` |
| `train-mock-data/` policy JSON files | `python skeleton/seed_vectors.py` |

> **重要：** `docker compose down -v` 會清除**兩個** Docker volumes（PostgreSQL 與 pgvector 一起）。如果你因 schema change 而 reset，之後也必須重新執行 `seed_neo4j.py` 與 `seed_vectors.py`，即使那些檔案沒有變更。

---

### Seeding 前先約定同一個 LLM provider

pgvector 中的政策文件會以數值 vectors 儲存。那些 vectors 的大小取決於 embedding model，而 embedding model 會隨 LLM provider 改變：

| Provider | `schema.sql` 中的 vector size | `.env` 設定 |
|---|---|---|
| Ollama（預設） | `vector(768)` | `LLM_PROVIDER=ollama` |
| Gemini | `vector(3072)` | `LLM_PROVIDER=gemini` |

**這兩種格式不相容。** 如果一位隊友用 Ollama seed，另一位用 Gemini query（或反過來），app 會因 `embedding dimension mismatch` error 而失敗。

在任何人執行 `seed_vectors.py` 前，團隊請先約定單一 provider。請確認：
1. 每個人在自己的 `.env` 中設定相同的 `LLM_PROVIDER` 值
2. `databases/relational/schema.sql` 中的 `vector(...)` 維度符合該 provider

如果之後整個團隊切換 provider，每個人都必須 reset database（`docker compose down -v && docker compose up -d`）並重新執行 `seed_vectors.py`。

---

### 完整重新同步流程（每次 `git pull` 後若 seed files 有變更就執行）

```bash
# 1. 清除 volumes 並重新啟動 containers（只有 schema.sql 變更時才需要）
docker compose down -v && docker compose up -d

# 2. 等到兩個 containers 都 healthy
docker compose ps

# 3. Seed relational database
#    macOS / Linux:
python3 skeleton/seed_postgres.py
#    Windows (PowerShell):
python skeleton/seed_postgres.py

# 4. 重新 seed graph database
#    macOS / Linux:
python3 skeleton/seed_neo4j.py
#    Windows (PowerShell):
python skeleton/seed_neo4j.py

# 5. 重新 seed vector database
#    macOS / Linux:
python3 skeleton/seed_vectors.py
#    Windows (PowerShell):
python skeleton/seed_vectors.py
```

---

### 要 commit 什麼以及不要 commit 什麼

**一定要 commit** `databases/` 裡任何檔案的變更。那是你們的工作區，也是共享的 source of truth。

**永遠不要 commit：**
- `.env` — 已 gitignored，因為它包含 credentials。每位隊友都應複製 `.env.example` 並填入自己的值。
- `.venv/` 資料夾 — 已 gitignored，而且很大。每位隊友都應透過 `python -m venv .venv` 建立自己的環境。
- 任何本機產生的 data exports 或 dump files。

Push 前請執行 `git status` 與 `git diff --staged`，確認你只 commit 了 `databases/` 中的檔案。
