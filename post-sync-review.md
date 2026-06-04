# Post-Sync Review — 蔡晟郁 檢查紀錄

> 檢查時間：2026-06-03 | 範圍：Sync 2 完成後全專案整合確認

---

## 一、實作完成度

| 負責人 | 狀態 | 說明 |
|--------|------|------|
| 蔡晟郁（Relational） | ✅ | 15 個函式全部實作，agent.py tool call 簽名吻合 |
| 黃謙儒（Graph） | ✅ | 6 個函式全部實作 |
| 蔣耀德（Vector） | ⚠️ | 4 模組完成，但 `embed()` 快取未實作（見下） |

---

## 二、已修正問題（Code Review PR #13 + 本輪審查）

- `execute_cancellation`：`open()` 已移入 `try` 內 ✅
- `register_user`：DB 異常改回傳 `(False, str(e))` ✅
- `update_password`：DB 異常改回傳 `False` ✅
- `execute_booking`：指定 seat_id 時加入可用性驗證 ✅
- `execute_cancellation`：回傳 key 由 `refund_amount_usd` 改為 `refund_amount`（評分 B10） ✅
- `query_user_profile`：回傳 dict 補上 `year_of_birth = date_of_birth.year`（評分 B6） ✅
- `query_national_rail_availability`：SQL 補上 `available_seats` 子查詢（評分 B1） ✅

**已知但不修：**
- `execute_booking` race condition（無 `SELECT FOR UPDATE`）：學校專題可接受
- 連線風格不統一（read-only 用 `_connect()`，write 用手動 `psycopg2.connect()`）：功能正確

---

## 三、評分風險總覽

| 項目 | 評分標準 | 我們的狀態 | 分數風險 |
|------|---------|-----------|---------|
| Task 4 Graph Design | `MetroStation`/`METRO_LINK`/`INTERCHANGE_TO` | 用 `Station`/`CONNECTS_TO`/`INTERCHANGE_WITH` | 🔴 /8 歸零 |
| Task 1 Normalisation | junction table for stops | `VARCHAR[]` array | 🔴 扣分 |
| Task 1 FK cascade | `ON DELETE` 明確指定 | 未指定 | 🔴 扣分 |
| Task 1 PK comment | 說明 VARCHAR(10) vs UUID 選擇理由 | 無 | 🔴 扣分 |
| Task 1 Delete strategy | comment 說明 soft delete | 無 | 🔴 扣分 |
| Code Quality | 3–5 個函式有 inline comment | 幾乎無 | 🟡 失 1 分 |
| Task 5 C2 `query_cheapest_route` | `fare_class` 影響 Dijkstra edge weight | 只影響最後費用計算 | 🟡 可能扣 1–2 分 |
| Live A Neo4j | `METRO_LINK`/`RAIL_LINK` | `CONNECTS_TO` | 🔴 2 分 |
| Live C4 `query_interchange_path` | 走 `INTERCHANGE_TO` | 走 `INTERCHANGE_WITH` | 🔴 部分分數 |

---

## 四、繳交項目狀態

| 項目 | 繳交方式 | 狀態 |
|------|---------|------|
| Code Repository | GitHub repo link → EEClass | ✅ |
| Design Document | Markdown → EEClass | ❌ **完全未開始** |
| Work Allocation Report | `WORK_ALLOCATION_TEMPLATE.md` → EEClass | ❌ 未填寫 |
| Peer Review Report | 每人個別填 `PEER_REVIEW_TEMPLATE.md` → EEClass | ❌ 未填寫 |

### Design Document 各章節要求（/100）

| 章節 | 分數 | 狀態 | 關鍵扣分點 |
|------|------|------|-----------|
| Section 1 — ER Diagram | /25 | ❌ | 關係線上要有基數標記（1:N / M:N），缺少 → 0 分；需工具繪製 |
| Section 2 — Normalisation | /20 | ❌ | ① 3NF 決策 + functional dependency ② bcrypt：為何優於 MD5/SHA-1、salt 防彩虹表 |
| Section 3 — Graph Rationale | /25 | ❌ | ① nodes/rel/properties 各自理由 ② Dijkstra vs SQL recursive CTE 論證 ③ node identity 說明 |
| Section 4 — Vector / RAG | /15 | ❌ | ① cosine similarity 為何適合 ② RAG 四階段 pipeline ③ embedding dimension 及換 provider 後果 |
| Section 5 — AI Tool Usage | /10 | ❌ | 3–5 例；每例需 Context + Prompt + Outcome；至少一例描述 AI 輸出錯誤並修正 |
| Section 6 — Reflection | /5 | ❌ | ① 兩個具體設計決策（要說理由）② 一個生產環境差異 |

---

## 五、待辦事項

### 🔵 蔡晟郁

| 優先 | 項目 | 說明 |
|------|------|------|
| 🔴 | `schema.sql` 所有 FK 加 `ON DELETE RESTRICT` | 評分 Task 1 直接扣分 |
| 🔴 | `schema.sql` PK 欄位加 comment 說明 VARCHAR(10) 選擇理由 | 評分 Task 1 直接扣分 |
| 🔴 | `schema.sql` 加 comment 說明 soft delete（`is_active`）策略 | 評分 Task 1 直接扣分 |
| 🟡 | `queries.py` 3–5 個複雜函式加 inline comment（解釋 WHY） | Code Quality 1 分 |
| 🟡 | 確認 `execute_cancellation` 是否只對國鐵呼叫（metro booking 邊界） | agent 層確認 |
| 🟢 | 移除 `queries.py:68` 殘留 TODO scaffold comment | 清理 |

### 🟢 黃謙儒

| 優先 | 項目 | 說明 |
|------|------|------|
| 🔴 | `seed_neo4j.py`：`Station` → `MetroStation` / `NationalRailStation` | Task 4 / Live A 直接 0 分 |
| 🔴 | `seed_neo4j.py`：`CONNECTS_TO` → `METRO_LINK` / `RAIL_LINK` | Task 4 / Live A 直接 0 分 |
| 🔴 | `seed_neo4j.py`：`INTERCHANGE_WITH` → `INTERCHANGE_TO` | Task 4 / Live C4 直接扣分 |
| 🔴 | `graph/queries.py`：所有 Cypher 同步更新至新 label / relationship 名稱 | 與 seed 改動一致 |
| 🟡 | `query_cheapest_route`：評估 `fare_class` 是否需影響 Dijkstra edge weight | Task 5 C2 |
| 🟢 | 移除 `graph/queries.py:68` 殘留 TODO scaffold comment | 清理 |

### 🟣 蔣耀德

| 優先 | 項目 | 說明 |
|------|------|------|
| 🟡 | `llm_provider.py`：補 `embed()` module-level cache（見方案 A） | Code Quality / 效能 |

**方案 A：**
```python
_embed_cache: dict[str, tuple[float, ...]] = {}

def embed(self, text: str) -> List[float]:
    if text in _embed_cache:
        return list(_embed_cache[text])
    result = self._ollama_embed(text) if self._embed_provider == "ollama" else self._gemini_embed(text)
    _embed_cache[text] = tuple(result)
    return result
```

---

### 👥 三人共同處理

| 優先 | 項目 | 說明 |
|------|------|------|
| 🔴 | **Design Document** 撰寫（6 個章節）| 可分工：蔡 Sec1+2，黃 Sec3，蔣 Sec4，三人共 Sec5+6 |
| 🔴 | **Work Allocation Report** 填寫 | `WORK_ALLOCATION_TEMPLATE.md`，三人對齊後填入 |
| 🔴 | **Peer Review** 每人各自填寫 | `PEER_REVIEW_TEMPLATE.md`，個人填但需三人都完成 |
| 🔴 | **本機環境設定**（Step 2–12）| 至少一人跑通 seed scripts，確認 live testing 可執行 |
| 🟡 | `schema.sql` Normalisation 討論 | 決定是否改用 junction table；決定後由蔡實作 |
| 🟡 | 黃改好 graph schema 後，蔡更新 `AI_SESSION_CONTEXT.md` 兩版本 | 保持文件一致 |

---

## 六、本機環境設定步驟

| # | 步驟 | 狀態 |
|---|------|------|
| 1 | Clone repo | ✅ |
| 2 | 建立 venv（`python3 -m venv .venv`） | ❌ |
| 3 | 啟用 venv（`source .venv/bin/activate`） | ❌ |
| 4 | `pip install -r requirements.txt` | ❌ |
| 5 | 複製 `.env.example` → `.env`，填入 LLM 設定 | ❌ |
| 6 | `docker compose up -d` | ❌ |
| 7 | 確認容器 healthy（`docker compose ps`） | ❌ |
| 8 | `python3 skeleton/seed_postgres.py` | ❌ |
| 9 | Ollama pull（`llama3.2:1b` + `nomic-embed-text`） | ❌ |
| 10 | `python3 skeleton/seed_vectors.py` | ❌ |
| 11 | `python3 skeleton/seed_neo4j.py` | ❌（需等黃改好 schema） |
| 12 | `python3 skeleton/ui.py` 啟動助理 | ❌ |
