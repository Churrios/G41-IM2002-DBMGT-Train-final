# TransitFlow Graph DB — 開發規劃 & 待組員確認問題清單

> 負責人：Chien（Graph DB Engineer）
> 範圍：`skeleton/seed_neo4j.py`、`databases/graph/seed.cypher`、`databases/graph/queries.py`
> 對應分數：Task 3 Seeding /10（共享）、Task 4 Graph 設計 /8、Task 5 Cypher Queries /10、Live Section C /35 → **共 /63**
> 文件狀態：**待決策**。下面第 2 章的問題請先帶去跟蔡晟郁、蔣組員討論，定案後我再把第 4 章的暫定流程鎖定成正式計畫並開始實作。

---

## 0. 為什麼需要先討論

我讀完所有文件後，發現**現況有一個根本性的 schema 衝突**，而且它牽涉到隊友已經 merge 的程式碼與團隊契約，照「跨邊界規則」我不能自己決定：

| 來源 | 主張的 schema |
|---|---|
| 評分標準 `STUDENT_GUIDE_CODE.md` Task 4 + `STUDENT_GUIDE_LIVE.md` Section A | **分離標籤** `MetroStation` / `NationalRailStation` + `METRO_LINK` / `RAIL_LINK` / `INTERCHANGE_TO` |
| 你的 `Chien_graph_AI_prompt.md` | 同上（分離標籤 + 三種關係） |
| **已 merge 的** `skeleton/seed_neo4j.py`（commit `89d214b`） | **單一** `Station` 標籤 + `CONNECTS_TO` + `INTERCHANGE_WITH` |
| 團隊契約 `AI_SESSION_CONTEXT.md`（標示「CONFIRMED 2026-05-28，蔣組員投票通過」） | 同上（單一 Station + CONNECTS_TO） |

➡️ **評分標準和現有程式碼是相反的。** 直接影響 Task 4（/8）與 Live Section A 的 `METRO_LINK`/`RAIL_LINK` 檢查。這是第 2 章 Q1～Q3 的核心。

---

## 1. 我已查證 / 可自行處理（不需團隊決定）

這幾項我已經從程式碼確認，列出來讓大家放心，**不必花時間討論**：

1. **演算法用 APOC，不是 GDS。** `docker-compose.yml` 只啟用 `NEO4J_PLUGINS: '["apoc"]'`，沒有裝 GDS。所以 `query_shortest_route` / `query_cheapest_route` 用 `apoc.algo.dijkstra`（SideNote 提到的 GDS 寫法在此環境跑不起來）。
2. **回傳格式不會弄壞 UI。** `skeleton/agent.py` 用 `_flatten_to_text()` 把任何 dict/list 通用攤平給 LLM，所以回傳欄位主要是「對齊評分標準」，不會因 key 不同而讓 UI crash。
3. **`query_station_connections` 沒有被 agent.py 匯入使用** → 只會被評分時「直接呼叫」測試（Live C6 /2），不影響聊天流程。
4. **連線埠陷阱（infra，我會在實作時處理）。** `skeleton/config.py` 預設 `NEO4J_URI=bolt://localhost:7687`，但 `docker-compose.yml` 對主機映射的是 **7688**（`7688:7687`）。從主機跑 `python skeleton/seed_neo4j.py` 時，`.env` 必須設 `NEO4J_URI=bolt://localhost:7688`，否則連不上。你的 prompt 寫的 7688 是對的。
5. **`find_alternative_routes` 在 agent.py 沒傳 `max_routes`**（用預設 3）；評分 C3 會「直接呼叫」函式測 `max_routes=1`，所以函式本身一定要正確支援這個參數。

---

## 2. 必須團隊討論決定的問題（依重要性排序）

### 🔴 Q1.（最重要）Schema 標籤模型要用哪一種？
- **選項 A — 改用評分標準模型**（分離 `MetroStation`/`NationalRailStation`）：可拿滿 Task 4 /8 與 Live Section A，符合你的 prompt。**代價**：要重寫已 merge 的 `seed_neo4j.py` 與 `queries.py`，並請蔡晟郁更新 `AI_SESSION_CONTEXT.md` 的 graph schema 段落。
- **選項 B — 維持現有 `Station`/`CONNECTS_TO`**：與蔣組員已 merge 的程式碼、團隊契約一致，改動最小。**代價**：Task 4（/8）與 Live Section A 對 `METRO_LINK`/`RAIL_LINK` 的明文檢查會失分。
- **選項 C — 兩種並存（雙寫）**：seeding 同時建 `:Station:MetroStation` 雙標籤 + 兩種關係，查詢用評分那套。相容性最高但圖冗餘、seed 較複雜。
- **我的建議：A**。評分標準是分數的最終依據，Task 4 + Live A 直接點名 `METRO_LINK`/`RAIL_LINK`；現有程式碼是團隊在沒看評分標準時投票的，值得為了分數調整。

> ⚠️ 若選 A 或 C，請蔣組員/蔡晟郁同意我**重寫 `seed_neo4j.py`**（屬於 Chien 範圍，但牽動契約）。

### 🔴 Q2. 關係類型命名 `METRO_LINK`/`RAIL_LINK` vs `CONNECTS_TO`
跟 Q1 綁在一起。評分要兩種獨立關係型別；現況是單一 `CONNECTS_TO` 用 `network` 屬性區分。**建議：用 `METRO_LINK`/`RAIL_LINK`。**

### 🟠 Q3. 換乘關係 `INTERCHANGE_TO` 的方向與命名
- 評分/SideNote：`INTERCHANGE_TO`，方向 metro → rail。
- 現況：`INTERCHANGE_WITH`，雙向（兩條有向邊）。
- **問題**：`query_interchange_path` 要支援「rail → metro」與「metro → rail」兩個方向。若只建單向 `INTERCHANGE_TO`，查詢時得用**無向比對** `-[:INTERCHANGE_TO]-`，或 seeding 時就建雙向。**建議：命名用 `INTERCHANGE_TO`，seeding 建雙向兩條邊**（兼顧評分命名與雙向查詢）。

### 🟠 Q4. 節點與邊要放哪些屬性？
- 你的 prompt：`MetroStation{station_id, name, line, is_interchange}`、`NationalRailStation{station_id, name, line, metro_interchange_id}`。
- SideNote：用 `lines[]`（陣列）。
- JSON 實際有：`lines[]`（陣列）、`is_interchange_metro`、`is_interchange_national_rail`、`interchange_*_station_id`。
- **建議**：節點存 `station_id, name, lines[]`（用陣列，與 JSON 一致），換乘旗標 `is_interchange_national_rail` 也存上去備用。邊存 `line, travel_time_min`（+ Q5 的票價）。**請確認大家接受用 `lines` 陣列而非單數 `line`。**

### 🟠 Q5. `query_cheapest_route` 的票價權重從哪來？
JSON 的 `adjacent_stations` **只有 `travel_time_min`，沒有票價**，但評分 C2 要求「`fare_class` 要明顯影響邊權重」。
- **選項 A — seeding 時把票價算進邊屬性**：用簡單模型（每跳 `base + travel_time × 費率`，`first` class 乘數較高）算出 `fare_standard_usd` / `fare_first_usd` 存到每條 `*_LINK`，Dijkstra 直接用該屬性。最乾淨、純圖內計算。
- **選項 B — 查詢時 Python 套乘數**：邊只存 `travel_time_min`，跑完最短路徑後在 Python 乘 `fare_class` 係數估票價。`fare_class` 對「路徑選擇」影響弱。
- **選項 C — 跨 DB 從 PostgreSQL 取真實票價**：用 `metro_schedules` / `national_rail_schedules` 的 `base_fare`/`per_stop_rate` 計算。最真實但 graph 層耦合關聯式 DB、較複雜。
- **我的建議：A**。完全在圖內、`fare_class` 真正改變邊權重，最符合 C2 評分。需大家同意一個簡單票價公式（例如 metro：`1.0 + 0.5×hops`；rail standard：`2.0 + per_stop`、first ≈ standard × 1.6）。

### 🟡 Q6. metro 沒有 fare class，`cheapest_route(fare_class=...)` 在 metro 怎麼處理？
national rail 才有 standard/first。**建議**：metro 一律用單一票價、忽略 `fare_class`；只有 rail 路徑才套 class。請確認。

### 🟡 Q7. `INTERCHANGE_TO` 的 `transfer_time_min` 值從哪來？
SideNote 範例有 `transfer_time_min: 5`，但 JSON 沒有換乘時間。**建議**：seeding 給一個固定預設（例如 5 分鐘），並在 `query_interchange_path` 的總時間納入。請確認預設值。

### 🟡 Q8. 要不要同步把 `databases/graph/seed.cypher` 填好？
現在 `seed.cypher` 是空的（標示 deprecated）。Task 4 可由 `seed_neo4j.py` **或** `seed.cypher` 評分。**建議**：以 `seed_neo4j.py` 為主，另外在 `seed.cypher` 放一份可讀的 schema/constraint Cypher，讓靜態評分的 TA 一眼看到 `METRO_LINK`/`RAIL_LINK`/`INTERCHANGE_TO`。請確認要不要做這份雙保險。

### 🟡 Q9. seeding 要不要建 constraints / indexes？
SideNote 第 3 節建議 `CREATE CONSTRAINT ... REQUIRE station_id IS UNIQUE`。非硬性評分項，但屬「production best practice」且能加 Code Quality 印象分。**建議：seeding 開頭建立兩個 unique constraint**（`MetroStation.station_id`、`NationalRailStation.station_id`），用 `IF NOT EXISTS` 保持冪等。

### 🟢 Q10. driver 用 singleton 還是 per-call？
SideNote 第 1 節推薦 singleton；但你的 prompt 範例與現有 `queries.py` 都用 per-call `_driver()`。評分沒強制。**建議：維持 per-call `_driver()`**（與既有契約一致、改動最小），在註解說明 production 會改 singleton 以對應 Code Quality「解釋 why」。請確認。

### 🟢 Q11. `AI_SESSION_CONTEXT.md` 的 graph schema 段落由誰更新？
該檔案歸蔡晟郁維護。若 Q1 改 schema，契約需同步更新。**建議**：我把新 schema 寫成一段文字，你轉給蔡晟郁貼進去（符合「跨邊界由本人改」）。

### 🟢 Q12. 要不要做 Task 6 加分（+15）？
圖相關的好題材：GDS 不可用，但可用 APOC/純 Cypher 做（a）PageRank-style 樞紐站分析、（b）無障礙/避開壅塞站的路徑、（c）站點中心度排名。需 `TASK6.md` + 設計文件 Section 7 + 每檔 `# TASK 6 EXTENSION:` 註解才算分。**建議**：先專注核心 /63，Task 6 列為核心完成後的 optional。請給方向。

---

## 3. 技術細節待確認（影響實作，非團隊政策）

這些我傾向自己依最佳做法處理，但先點出來讓你知道風險點：

- **`query_delay_ripple` 的 `hops` 不能直接參數化。** Cypher 的可變長度路徑 `*1..N` 的 `N` 不接受 query 參數綁定。需用 `apoc.path.subgraphNodes` / `apoc.neighbors` 帶 `maxLevel` 參數，或在 Python 端驗證 `hops` 為整數後組字串（**不可**拼接使用者原始輸入，先 `int()` 轉型）。評分 C5 要求 `hops=0` 只回傳該站本身 → 用 APOC 並包含起點。
- **邊方向**：JSON 的鄰接是雙向都列（MS01→MS05 且 MS05→MS01 都存在），所以建有向邊也能雙向走。但為保險，**查詢一律用無向比對** `-[:METRO_LINK]-`，避免漏邊。需確認 JSON 鄰接完全對稱（我會在 seeding 加驗證輸出）。
- **`network="auto"` 推斷規則**：用 ID 前綴，`MS`→metro、`NR`→rail；起訖跨網（一 MS 一 NR）時 agent 會改走 `query_interchange_path`，所以 shortest/cheapest 只需處理同網。
- **回傳欄位精確定義**（對齊評分 + 現有 docstring）：
  - `query_shortest_route` → `{found, origin_id, destination_id, total_time_min, path:[{station_id,name}], legs:[{line,travel_time_min}]}`
  - `query_cheapest_route` → `{found, total_fare_usd, path, legs, fare_class}`
  - `query_alternative_routes` → `list[list[dict]]`（每條路徑是 leg dict 串列）
  - `query_interchange_path` → `{found, path, legs, total_time_min, interchange_points}`
  - `query_delay_ripple` → `list[{station_id, name, hops_away, lines_affected}]`（`hops=0` 含起點本身）
  - `query_station_connections` → `list[{station_id, name, line, travel_time_min}]`
  - 全部空結果回傳 `{}` / `[]`，**絕不 raise**。

---

## 4. 暫定開發流程（待第 2 章決策後鎖定）

> 假設 Q1 選 A（評分標準模型）。若團隊改選 B/C，我會調整 Phase 1。

**Phase 0 — 環境與分支（每次工作前）**
- `git fetch origin` 確認 main 無新 commit；有則先同步。
- `docker compose ps` 確認 neo4j healthy；`.env` 設 `NEO4J_URI=bolt://localhost:7688`。
- 開分支 `git checkout -b feature/Chien/neo4j-seeding`。

**Phase 1 — Schema + Seeding（Task 3 /10 共享、Task 4 /8、Live A）**
1. 重寫 `skeleton/seed_neo4j.py`：
   - 建 unique constraints（Q9）。
   - `MERGE` 建 `MetroStation` / `NationalRailStation` 節點（冪等，Q1/Q2/Q4）。
   - `MERGE` 建 `METRO_LINK` / `RAIL_LINK`（含 `travel_time_min` + 票價屬性 Q5）。
   - `MERGE` 建 `INTERCHANGE_TO` 雙向（含 `transfer_time_min` Q7）。
   - 結尾印出節點/邊統計做驗證。
   - **commit**：`feat(graph): rewrite seed_neo4j with MetroStation/RAIL labels and MERGE`
2.（若 Q8 同意）`databases/graph/seed.cypher` 補一份可讀 schema Cypher。
   - **commit**：`feat(graph): add readable seed.cypher schema mirror`
3. 實跑 `python skeleton/seed_neo4j.py`，Neo4j Browser（:7475）肉眼驗證。

**Phase 2 — Cypher Query Functions（Task 5 /10、Live C /35）**
依風險/分數順序逐一實作並各自 commit：
1. `query_station_connections`（C6，最簡單，先暖身）
2. `query_shortest_route`（C1，APOC dijkstra by `travel_time_min`）
3. `query_cheapest_route`（C2，dijkstra by 票價屬性，Q5/Q6）
4. `query_delay_ripple`（C5，APOC subgraphNodes，`hops` gotcha）
5. `query_alternative_routes`（C3，避開站 + `max_routes`）
6. `query_interchange_path`（C4，跨網走 `INTERCHANGE_TO`）
- 每個函式：參數化 Cypher、空結果回傳 `{}`/`[]`、docstring 含 Args/Returns、非顯然邏輯加 why 註解（Code Quality /2）。
- 每函式一個 commit，格式 `feat(graph): implement query_xxx ...`。

**Phase 3 — Live Section C 自我驗證（/35）**
- 對照 `STUDENT_GUIDE_LIVE.md` C1～C6 每個情境逐一手動測（含 metro/rail 兩網、未連通站、`hops=0`、`max_routes=1`、跨網等邊界）。
- 修正後 commit。

**Phase 4 — 收尾**
- 請蔡晟郁更新 `AI_SESSION_CONTEXT.md`（Q11）。
- push 後等你指示是否開 PR（不主動發 PR）。
- （Q12 若做）Task 6：`TASK6.md` + 設計文件 Section 7 + 每檔 `# TASK 6 EXTENSION:`。

---

## 5. 一頁速覽：帶去問組員的 12 個問題

| # | 問題 | 我的建議 | 影響分數 |
|---|------|---------|---------|
| Q1 | 分離標籤 vs 單一 Station | **A 分離標籤** | Task4 /8、Live A |
| Q2 | `METRO_LINK`/`RAIL_LINK` vs `CONNECTS_TO` | **分離關係** | Task4、Live A |
| Q3 | `INTERCHANGE_TO` 方向/命名 | 命名 `INTERCHANGE_TO`、建雙向 | C4 /8 |
| Q4 | 節點/邊屬性集合 | `lines[]` 陣列 + `travel_time_min` | Task4 |
| Q5 | cheapest 票價來源 | **A：seeding 寫入邊屬性** | C2 /7 |
| Q6 | metro 的 fare_class | metro 忽略 class | C2 |
| Q7 | `transfer_time_min` 預設值 | 固定 5 分鐘 | C4 |
| Q8 | 是否同步填 `seed.cypher` | 做雙保險 | Task4 |
| Q9 | 是否建 constraints/index | 建 unique constraint | Code Quality |
| Q10 | driver singleton vs per-call | 維持 per-call | Code Quality |
| Q11 | 誰更新 `AI_SESSION_CONTEXT` | 我寫、你轉蔡晟郁 | 契約一致性 |
| Q12 | 要不要做 Task 6 | 核心優先、後續再評估 | +15 bonus |

---

**討論完把結論告訴我，我就把這份暫定流程鎖定成正式計畫，並等你說「動工」後開始實作。**
