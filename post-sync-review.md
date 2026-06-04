# Post-Sync Review — TransitFlow 整合檢查

> 更新：2026-06-04 | 範圍：Sync 2 完成後 + 課堂討論整合

---

## 一、行動清單

### 🔵 蔡晟郁（Relational DB）

| 優先 | 項目 |
|------|------|
| ✅ | `schema.sql`：所有 FK 加 `ON DELETE`（16 條，RESTRICT / SET NULL / CASCADE） |
| ✅ | `schema.sql`：PK 設計說明 comment（header + 每個表格 PK 欄位） |
| ✅ | `schema.sql`：soft delete 策略 comment（`is_active` 欄位） |
| ✅ | `queries.py`：5 個函式加 inline WHY comment |
| ✅ | 移除 `queries.py:68` TODO scaffold comment |
| ✅ | `execute_cancellation` metro 邊界確認：agent 層 `cancel_booking` description 已限定 national rail，無需改動 |
| 🟡 | `schema.sql`：與組員討論是否改用 junction table 取代 `stops_in_order VARCHAR[]`（影響 Task 1 Normalisation 評分） |

### 🟢 黃謙儒（Graph DB）

| 優先 | 項目 |
|------|------|
| ✅ | `seed_neo4j.py`：`Station` → `MetroStation` / `NationalRailStation` |
| ✅ | `seed_neo4j.py`：`CONNECTS_TO` → `METRO_LINK`（捷運）/ `RAIL_LINK`（國鐵） |
| ✅ | `seed_neo4j.py`：`INTERCHANGE_WITH` → `INTERCHANGE_TO`；加上 `transfer_time_min=5` 屬性 |
| ✅ | `graph/queries.py`：所有 Cypher 同步更新至新 label / relationship 名稱 |
| ✅ | `query_cheapest_route`：fare_usd / fare_standard_usd / fare_first_usd 寫入邊屬性，Dijkstra 直接使用 |
| ✅ | `query_station_connections`：移除 `r.network`，改用關係型別判斷 |

### 🟣 蔣耀德（Vector / LLM）

| 優先 | 項目 |
|------|------|
| ✅ | `llm_provider.py`：補 `embed()` module-level `_embed_cache` dict |

```python
_embed_cache: dict[str, tuple[float, ...]] = {}

def embed(self, text: str) -> List[float]:
    if text in _embed_cache:
        return list(_embed_cache[text])
    result = self._ollama_embed(text) if self._embed_provider == "ollama" else self._gemini_embed(text)
    _embed_cache[text] = tuple(result)
    return result
```

### 👥 三人共同

| 優先 | 項目 |
|------|------|
| 🔴 | **Design Document**：撰寫六章節（建議分工：蔡 Sec1+2，黃 Sec3，蔣 Sec4，三人共 Sec5+6） |
| 🔴 | **Work Allocation Report**：填寫 `WORK_ALLOCATION_TEMPLATE.md` |
| 🔴 | **Peer Review**：每人各自填 `PEER_REVIEW_TEMPLATE.md` |
| 🔴 | **本機環境設定**（Steps 2–12）：至少一人跑通全套 seed scripts，確認 live testing 可執行 |
| 🟡 | 黃改好 graph schema 後，蔡同步更新 `AI_SESSION_CONTEXT.md`（中英兩版） |

---

## 二、繳交項目狀態

| 項目 | 方式 | 狀態 |
|------|------|------|
| Code Repository | GitHub repo link → EEClass | ✅ |
| Design Document | Markdown/PDF → EEClass | ❌ 未開始 |
| Work Allocation Report | `WORK_ALLOCATION_TEMPLATE.md` → EEClass | ❌ 未填 |
| Peer Review Report | 每人個別填 → EEClass（保密） | ❌ 未填 |

---

## 三、評分風險

| 項目 | 評分標準要求 | 我們的狀態 | 風險 |
|------|------------|-----------|------|
| Task 4 Graph Design /8 | `MetroStation` / `METRO_LINK` / `INTERCHANGE_TO` | ✅ 已完成 | ✅ |
| Task 1 Normalisation | junction table for stops | `VARCHAR[]` array（設計取捨） | 🟡 可能扣分 |
| Task 1 FK cascade | `ON DELETE` 明確指定 | ✅ 已補全 | ✅ |
| Task 1 PK comment | 說明選型理由 | ✅ 已補 | ✅ |
| Task 1 Delete strategy | comment 說明 soft delete | ✅ 已補 | ✅ |
| Live A Neo4j | `METRO_LINK` / `RAIL_LINK` | ✅ 已完成 | ✅ |
| Live C4 interchange path | 走 `INTERCHANGE_TO` | ✅ 已完成 | ✅ |
| Code Quality /2 | 3–5 個函式有 inline comment | ✅ 已補 WHY comments | ✅ |
| Task 5 C2 cheapest route | `fare_class` 影響 Dijkstra 路徑 | ✅ 邊屬性已寫入，Dijkstra 直接使用 | ✅ |

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
| 2 | `python3 -m venv .venv` | ❌ |
| 3 | `source .venv/bin/activate` | ❌ |
| 4 | `pip install -r requirements.txt` | ❌ |
| 5 | 複製 `.env.example` → `.env`；port 衝突時**只改 `.env`，不動 `config.py`** | ❌ |
| 6 | `docker compose up -d` | ❌ |
| 7 | `docker compose ps`（確認 healthy） | ❌ |
| 8 | `python3 skeleton/seed_postgres.py` | ❌ |
| 9 | `ollama serve`（先確認 server 跑起來）→ `ollama pull llama3.2:1b` + `nomic-embed-text` | ❌ |
| 10 | `python3 skeleton/seed_vectors.py` | ❌ |
| 11 | `python3 skeleton/seed_neo4j.py`（需等黃完成 schema 改動） | ❌ |
| 12 | `python3 skeleton/ui.py` | ❌ |
