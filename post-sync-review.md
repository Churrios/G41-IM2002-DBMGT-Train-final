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

## 二、Code Review 問題（PR #13）

### 🔴 已修正
- `execute_cancellation`：`open()` 已移入 `try` 內 ✅
- `register_user`：DB 異常改回傳 `(False, str(e))` ✅
- `update_password`：DB 異常改回傳 `False` ✅
- `execute_booking`：指定 seat_id 時加入可用性驗證 ✅

### 🟡 待確認
- `execute_cancellation`：JOIN 只對 `national_rail_schedules`，metro booking 會回傳 "Booking not found"（agent 層應只對國鐵呼叫，需確認）

### 🟢 已知但不修
- `execute_booking` race condition（無 `SELECT FOR UPDATE`）：學校專題可接受
- 連線風格不統一（read-only 用 `_connect()`，write 用手動 `psycopg2.connect()`）：功能正確，不改

---

## 三、蔣的 embed() 快取問題

`lru_cache` 只有 import，未套用。`embed()` 是 instance method，無法直接加 `@lru_cache`。

**修法（方案 A）**：
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

## 四、評分風險

### Task 4 — Neo4j Graph Design /8 ❌ 高風險

| 評分標準要求 | 我們的實作 |
|---|---|
| `MetroStation` / `NationalRailStation` labels | 單一 `Station` label |
| `METRO_LINK` / `RAIL_LINK` 關係 | `CONNECTS_TO` |
| `INTERCHANGE_TO` 關係 | `INTERCHANGE_WITH` |

→ 8 分整個歸零風險，需討論是否修改 seed_neo4j.py

### Task 1 — Relational Schema /40 四個扣分點

| 問題 | 說明 |
|------|------|
| Normalisation ❌ | 評分要求 junction table，我們用 `VARCHAR[]` array |
| PK design comment ❌ | 未說明為何選 VARCHAR(10) 而非 UUID/SERIAL |
| Delete strategy comment ❌ | `is_active` 存在但無 comment 說明 soft delete |
| FK cascade ❌ | 所有 FK 未指定 `ON DELETE RESTRICT/CASCADE/SET NULL` |

### Code Quality /2 ⚠️
queries.py 幾乎無 inline comment，可能失去 1 分

---

## 五、文件補齊

| 檔案 | 狀態 |
|------|------|
| `AI_SESSION_CONTEXT.md` | ✅ 原本已完整 |
| `AI_SESSION_CONTEXT.zh-TW.md` | ✅ 今日補齊 |
| `TEAM.md` | ✅ 今日更新三人完整姓名 |
| `SideNote1-RelationalDBPractices.zh-TW.md` | ✅ 加入本專案狀態欄 |
| `README.md` / `README.zh-TW.md` | ✅ Your Tasks 打勾 |

---

## 六、本機執行環境（未設定）

- [ ] 複製 `.env.example` → `.env`，填入 LLM 設定
- [ ] 建立 venv + `pip install -r requirements.txt`
- [ ] 啟動 Docker：`docker compose up -d`
- [ ] 執行三支 seed 腳本（postgres / neo4j / vectors）
- [ ] 啟動 UI，用 README Try These Queries 驗證

---

## 七、待辦事項

- [ ] **Task 4**：討論是否修改 graph schema 命名符合評分標準
- [ ] **Task 1 FK cascade**：所有 FK 加上 `ON DELETE RESTRICT`
- [ ] **Task 1 PK comment**：schema.sql PK 欄位加設計決策說明
- [ ] **Task 1 Delete strategy**：加 comment 說明 soft delete
- [ ] **Task 1 Normalisation**：討論是否改用 junction table
- [ ] **Code Quality**：queries.py 非顯而易見函式加 inline comment
- [ ] **蔣**：確認是否補 commit 修正 `embed()` 快取
- [ ] **execute_cancellation**：確認 metro booking 邊界
