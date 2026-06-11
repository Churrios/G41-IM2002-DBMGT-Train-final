# TransitFlow — 第二輪本地端到端測試與最終驗證紀錄（黃謙儒）

> 接續第一輪測試（2026-06-09，見 `local-testing-notes-chien.md` / `local-testing-results-chien.md`）。
> 本輪目標：驗證第一輪分派出去的修正是否生效、補測 768 維（Ollama）RAG、並在所有修正 merge 後於 main 做最終回歸。
> 方法沿用雙軌：**直接呼叫 Python function**（測程式正確性）＋ **chatbot 經 LLM**（測端到端與 LLM 行為），兩軌分離可區分「程式 bug」與「LLM 行為」。
> 測試工具：`verify_seeding.py`（Live A 自檢：14 張 PG 表 + Neo4j 節點/關係計數）、`smoke_test_functions.py`（49 項斷言，涵蓋 Graph C1–C6、Relational B1–B8、寫入錯誤路徑、Task 6 全流程）。

---

## 最終結論（TL;DR）

| 驗證 | 環境 | 結果 |
|------|------|------|
| 直接呼叫 49 項斷言 | **main**（commit `04087f6`，全部修正 merge 後）| **49 PASS / 0 FAIL** ✅ |
| Seeding（Live A）| 全新 `down -v` 重建 | 14 表 + Neo4j 20/10/42/18/6 全有資料 ✅ |
| RAG 768 維（交付設定）| Ollama `nomic-embed-text` + `vector(768)` | 101 chunks seeded、向量檢索正確 ✅ |
| Chatbot 端到端 21 題 | Gemini `gemini-3.1-flash-lite` | 全數函式層正確；LLM 行為瑕疵均已歸因（見下）|
| Task 6 三段 bonus 前置 | — | `TASK6.md`、per-file markers、Design Doc §7（含 §7.4 截圖）皆齊 ✅ |

---

## Session 1 — 2026-06-10（Gemini, 3072 維, chatbot 21 題 + 直接呼叫）

環境：Windows / Docker / `LLM_PROVIDER=gemini`（`gemini-3.1-flash-lite`）/ DB 全新重建重灌。

### 直接呼叫（程式正確性）
- `verify_seeding`：14 張表筆數全對（含 `delay_events` 5、`policy_documents` 101）；Neo4j 30 節點 / 66 邊。
- `smoke_test`：47 PASS / 0 FAIL（當時版本，尚無 C6 envelope 斷言）。
- legs 深測：`query_alternative_routes('MS01','MS09','MS07')` 回 3 條，legs 數 = 站數−1、sum(legs)=total、皆不含 MS07。

### Chatbot 端到端（21 題）摘要
- **全綠**：B1' B2 B3 B4 B5 B7 B8 B9（明確座位）B10 C1 C1' C3 C4 C5 R1 R2 T1（明確 severity）T3。
- **LLM 行為瑕疵（函式皆正確）**：B1（過去日期腦補「無班次」）、B6（profile 依設計需登入）、C6（裸 list 被誤讀）、T2/T3（LLM 漏報舊日期的 active 事件）。
- **發現的真缺口（非 graph 函式）**：
  1. **B9「any」訂票幻覺**：agent 為單輪工具執行，無法串接 get_available_seats→make_booking，LLM 會謊報訂票成功（DB 查證無該筆）。規避：給明確 seat_id（單一工具即可完成，DB 查證 `BK-HZ6MO4` 真實寫入）。
  2. **C2 `find_route` 工具缺 `fare_class` 參數**：頭等「最便宜路線」經助理無法觸達（函式 `query_cheapest_route(fare_class='first')` 直接呼叫正確回 $138 ≠ standard $86）。
  3. **T1 severity 模糊詞**：LLM 傳 "serious" 撞 `severity CHECK` 約束、漏出原始 DB 錯誤。
- **上一輪分派修正全部驗證 close**：B4 票價字串型別轉換（蔡）、B8 `get_payment_info` 工具註冊（蔣）、B10 取消的 `encoding='utf-8'`（蔡）、C3 fallback guard（蔣）。

## Session 2 — 2026-06-11（Ollama, 768 維 = 交付設定）

環境：`LLM_PROVIDER=ollama`（`llama3.2:1b` + `nomic-embed-text` 768 維）/ schema `vector(768)` / DB 全新重建。

- `verify_seeding`：全過，**`policy_documents` 101 chunks（768 維）**確認 seeded。
- `smoke_test`：48/49（唯一 FAIL = C3 legs，因 legs 修正當時尚未 merge 至該分支，預期中）。
- **R1 退費政策 RAG ✅**：`search_policy` 正確觸發、檢索 Delay Compensation（sim 0.64–0.67）、回答內容來自文件 → **768 維 + nomic-embed-text 檢索功能確認正常**。
- R2 ❌（LLM 行為）：`llama3.2:1b` 未呼叫工具、直接亂答 —— 同題在 Gemini 下通過（Session 1），RAG 架構本身無誤，屬小模型 tool-use 能力限制（Design Doc §6 Decision 2 已記載此取捨）。

## 最終回歸 — 2026-06-11（main `04087f6`）

PR #59 merge 後於 main 重跑：`verify_seeding` 全過、`smoke_test` **49 PASS / 0 FAIL**（C6 envelope 4 項新斷言 + C3 legs 斷言全過）。

---

## 本輪測試發現 → 修正對照（功勞歸屬）

| 發現（測試輪）| 修正 | PR | 作者 |
|---|---|---|---|
| C6 回裸 list、LLM 誤讀「MS01 的鄰站」| `query_station_connections` 改回 `{station_id, connections}` envelope | #59 | 黃謙儒 |
| T1 severity "serious" 撞 CHECK、漏原始 DB 錯 | `report_delay` dispatch 正規化 severity（serious/severe→high 等）+ 非法值友善訊息 | #59 | 黃謙儒 |
| C3 回應缺每段路線資訊 | `query_alternative_routes` 增加 `legs`（line + travel_time_min）| #59 | 黃謙儒 |
| §1.2 實體表列出 schema 不存在的欄位（zone/managed_by）| Design Doc §1.2 對齊實際 schema | #57 | 蔡晟郁 |
| Task 6 marker 不在檔案頂部 | 四檔頂部補 `# TASK 6 EXTENSION:` | #58 | 蔡晟郁 |
| Task 6 文件前置（第一輪遺留）| `TASK6.md` + Design Doc §7 | #56 | 蔣耀德 |
| §7.4 Testing Evidence 空白 | 補 T1–T3 chatbot 截圖（debug panel 佐證）| docs（待 commit）| 黃謙儒 |
| B4/B8/B10/C3 第一輪分派修正 | 型別轉換 / 工具註冊 / encoding / fallback guard | #50 等 | 蔡晟郁、蔣耀德 |

## 已知限制（非阻斷，皆已歸因記錄）

- **B9「any」自動選位**：單輪 agent 架構限制 + LLM 幻覺；demo 請給明確座位。
- **C2 頭等最便宜路線**：`find_route` 工具層缺 `fare_class` 參數（函式正確）；可列為未來小改進。
- `query_delay_ripple` 起點以 hops_away=2 自我重現（變長路徑折返）；TA 檢核點（hops=0 特判、hops_away 欄位）皆滿足。
- seed 的 `delay_events` 日期較舊（2025-03-10），LLM 摘要時傾向略過；demo 可先 `report_delay` 一筆新事件再查。