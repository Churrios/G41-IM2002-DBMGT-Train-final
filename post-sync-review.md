# Post-Sync Review — 蔡晟郁 檢查紀錄

---

## PR #13 Code Review — `databases/relational/queries.py`

> 來源：黃謙儒 AI agent 對蔡晟郁 PR 的 review

### 🔴 Serious（會在 runtime 造成 bug）

**1. `execute_cancellation` — `open()` 在 `try` 外**

`refund_policy.json` 的讀取在 `try/except` 之前，若檔案不存在或 JSON 格式錯誤，`conn.rollback()` 不會執行，exception 直接傳播。函式應回傳 `(False, error_msg)` 但實際會 raise。

**2. `register_user` / `update_password` — `except: raise` 而非回傳**

兩支函式的 DB 異常會直接 re-raise，而 docstring 明確說 failure 應回傳 `(False, error_message)` / `False`。ON CONFLICT 的 email 衝突有正確處理，其他 DB 錯誤則不行。

---

### 🟡 Moderate

**3. `execute_cancellation` — JOIN 只對 `national_rail_schedules`**

若傳入的 `booking_id` 是 metro 訂單，JOIN 找不到資料，回傳 "Booking not found"。需確認 agent 層是否永遠只對國鐵呼叫此函式。

**4. `execute_booking` — 指定 `seat_id` 時無驗證可用性**

Seat 不存在於 `seat_layouts` 或已被預訂時，`coach` 變空字串但 booking 仍會被 INSERT。

---

### 🟢 Minor

**5. `execute_booking` — seat 競爭寫入（race condition）**

無 `SELECT ... FOR UPDATE` 鎖定。學校專題影響不大，若有 unique constraint 則其中一筆會 rollback。

**6. 連線風格不一致**

read-only 函式用 `_connect()`，write 函式用 `psycopg2.connect()` 手動 commit/rollback。功能正確但風格不統一。

---

### 待修正清單

- [x] 🔴 `execute_cancellation`：`open()` 移入 `try` 內 ✅
- [x] 🔴 `register_user`：`except Exception` 改為 `return (False, str(e))` ✅
- [x] 🔴 `update_password`：`except Exception` 改為 `return False` ✅
- [ ] 🟡 `execute_cancellation`：確認 metro booking 的處理邊界
- [x] 🟡 `execute_booking`：指定 seat_id 時加驗證（seat 存在且未被預訂）✅

---

## TEAM_AI_WORKFLOW.zh-TW.md 對照

| 項目 | 狀態 |
|------|------|
| Schema-First workshop → commit → lock | ✅ |
| Graph schema 團隊同意並記錄 | ✅ |
| 分工記錄（`TEAM.md`） | ✅ 已建立並更新三人完整姓名 |
| AI_SESSION_CONTEXT.md 維護 | ✅ 中文版今天補齊，英文版已完整 |
| Session 前 git pull | ✅ |
| 五階段 AI 工作流程循環 | ✅ |
| Appendix 清單（Docker / venv 確認） | ⚠️ 未逐項確認 |

- [x] 補建 `TEAM.md`（分工記錄）✅ 已更新三人完整姓名與負責檔案

---

> 檢查時間：2026-06-03
> 檢查範圍：Sync 2 完成後，全專案整合確認

---

## ✅ 蔡晟郁（Relational DB）

15 個函式全部實作，無 `NotImplementedError` 殘留。  
agent.py tool call 簽名全部吻合。

---

## ✅ 黃謙儒（Graph DB）

6 個函式全部實作，無 `NotImplementedError` 殘留。

---

## ⚠️ 蔣耀德（Vector DB）— 發現問題

### 問題：`embed()` 快取未實作

**位置**：`skeleton/llm_provider.py`

**現況**：
- `from functools import lru_cache` — import 存在 ✅
- `embed()` 為 class `LLMProvider` 的 instance method
- 函式本體沒有任何快取裝飾器或快取邏輯 ❌

**原因分析**：
`@lru_cache` 不能直接套用於 instance method，因為 `self` 不是 hashable。蔣的計劃原稿寫的是 module-level function，但實際 `embed` 是 class 方法，導致快取沒有實作。

**正確解法（擇一）**：

**方案 A — module-level cache dict（最簡單）**：
```python
_embed_cache: dict[str, tuple[float, ...]] = {}

def embed(self, text: str) -> List[float]:
    if text in _embed_cache:
        return list(_embed_cache[text])
    result = self._ollama_embed(text) if self._embed_provider == "ollama" else self._gemini_embed(text)
    _embed_cache[text] = tuple(result)
    return result
```

**方案 B — `functools.cache` on inner call（不動簽名）**：
```python
from functools import cache

@cache
def _cached_ollama_embed(url: str, model: str, text: str) -> tuple[float, ...]:
    ...
```

**評分影響**：
- 快取功能本身不在 Task 2 直接評分項目內，但 SideNote2 最佳實踐要求有實作
- 若 Demo 時相同問題重複送出兩次，仍會看到 LLM embedding 二次呼叫的 log

---

## ✅ AI Session Context 文件補齊

| 檔案 | 狀態 |
|------|------|
| `AI_SESSION_CONTEXT.md`（英文版） | ✅ 原本已完整 |
| `AI_SESSION_CONTEXT.zh-TW.md`（中文版） | ✅ 2026-06-03 補齊（Schema、Graph Schema、Team Decisions Log） |

---

## ⚠️ 評分標準對照發現的問題（STUDENT_GUIDE_CODE.md）

### Task 4 — Neo4j Graph Design /8 ❌ 高風險

| 評分標準要求 | 我們的實作 | 風險 |
|---|---|---|
| `MetroStation` / `NationalRailStation` 兩個 label | 單一 `Station` label + `network` 屬性 | 可能 0 分 |
| `METRO_LINK` / `RAIL_LINK` 關係 | `CONNECTS_TO` | 可能 0 分 |
| `INTERCHANGE_TO` 關係 | `INTERCHANGE_WITH` | 可能 0 分 |

**8 分整個歸零風險。** 評分標準明確列出特定名稱，我們的設計雖然更好但與評分不符。

---

### Task 1 — Relational Schema Design /40 四個扣分點

| 評分標準 | 狀態 | 說明 |
|---|---|---|
| **Normalisation** | ❌ | 評分要求站點順序放獨立 junction table（stop_order 欄位），我們用 `VARCHAR[]` array |
| **PK design comment** | ❌ | schema.sql 未說明為何選 VARCHAR(10) 而非 UUID/SERIAL |
| **Delete strategy comment** | ❌ | `is_active` 存在但沒有 comment 說明採用 soft delete 策略 |
| **FK cascade behaviour** | ❌ | 所有 FK 均未指定 `ON DELETE RESTRICT/CASCADE/SET NULL` |

---

### Code Quality /2 ⚠️

評分要求「3–5 個非顯而易見的函式有 inline comment 解釋為什麼（不只是什麼）」。
目前 `databases/relational/queries.py` 幾乎無 comment，可能失去 1 分。

---

## 待確認

- [ ] **Task 4**：討論是否修改 seed_neo4j.py 改用 `MetroStation`/`NationalRailStation`/`METRO_LINK`/`RAIL_LINK`/`INTERCHANGE_TO`
- [ ] **Task 1 Normalisation**：討論是否新增 junction table（`schedule_stops`）取代 VARCHAR[] array
- [ ] **Task 1 FK cascade**：在 schema.sql 所有 FK 加上 `ON DELETE RESTRICT`（或其他策略）
- [ ] **Task 1 PK comment**：在 schema.sql PK 欄位旁加 comment 說明設計決策
- [ ] **Task 1 Delete strategy comment**：加 comment 說明採用 soft delete
- [ ] **Code Quality**：在 queries.py 非顯而易見的函式加 inline comment
- [ ] 蔣耀德確認是否要補 commit 修正 `embed()` 快取
- [ ] 若修正，commit message：`fix(vector): implement embed cache using module-level dict`
