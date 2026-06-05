# Chien Graph DB — 修改計畫（逐段交付 Sonnet 用）

> 目的：把 Chien 負責的三個檔案的修改，拆成**一段一段獨立、可單獨交給 Sonnet 執行**的任務。
> 每段都自帶：目標檔案 / 修改位置 / 要做什麼 / 注意陷阱 / 驗收 / commit message。
> **本文件只給「計畫與規格」，不貼完整程式碼**（完整 Cypher/Python 由 Sonnet 依規格產出）。
>
> 來源依據：
> - [Chien_專案全面檢視_問題清單.md](../Chien_專案全面檢視_問題清單.md)（C1/C2/C3）
> - [post-sync-review.md](../post-sync-review.md)（Graph 行動清單 + 評分風險）
> - [Chien_graph_正式開發流程.md](Chien_graph_正式開發流程.md)（Q1–Q12 已鎖定的決策 + 完整 Cypher 草案）
> - 本次實際複查 `databases/graph/queries.py`、`skeleton/seed_neo4j.py`、`skeleton/agent.py`、JSON 資料
>
> 更新：2026-06-04

---

## 0. 給 Sonnet 的總原則（每段都適用）

1. **只准動三個檔案**：`skeleton/seed_neo4j.py`、`databases/graph/queries.py`、`databases/graph/seed.cypher`。其他檔案（特別是 `skeleton/agent.py`、`skeleton/config.py`、`schema.sql`）一律不動，發現問題回報 Chien。
2. **參數化**：所有 Cypher 用 `$param`，唯一例外是可變長度路徑上限 `*1..N` 的 `N`，需先在 Python `int()` 後再 f-string 嵌入。
3. **絕不 raise**：所有 `query_*` 函式用 `try/except` 包住，空結果回 `{}` / `[]` 或對應的 `found=False` 結構。
4. **idempotent seeding**：一律 `MERGE`，不用 `CREATE`。
5. **一段一 commit**：每段對應一個 commit message（段末已給）。
6. Driver 用 **per-call**，且務必用 `with` 確保連線關閉（見 SEG-3 的陷阱說明）。

---

## 0.5 本次複查「新發現」的 Chien 問題（除既有 C1/C2/C3 外）

這些是這次讀 code 才確認的，已併入下面對應段落，先在這裡列清單讓 Chien 一眼看到：

| 編號 | 嚴重度 | 一句話 | 併入段落 |
|------|--------|--------|----------|
| **N1** | 🔴 | 正式流程草案的 `cheapest_route` 用 `if network == "national_rail"` 選票價欄位，但 **agent.py 呼叫時只傳 `network="auto"`，永遠不會等於 `"national_rail"`** → rail 路線會誤用 `fare_usd`（RAIL_LINK 邊上根本沒這屬性）→ Dijkstra 抓不到權重、票價算錯或回空。必須改用 `_infer_network()` 解析。 | SEG-6 |
| **N2** | 🟠 | `query_interchange_path` 現有 code 回傳 key 是 `stations` / `interchanges`；但正式流程與評分期望是 `path` / `interchange_points`。rewrite 時要用後者，否則 Live C4 對 key 失分。 | SEG-9 |
| **N3** | 🟡 | `query_station_connections` **沒有被 agent.py import**（agent 只 import 5 個函式）。代表它只會被 Live C6「直接呼叫」測到，不會經由聊天觸發。→ 不需改 agent（不是我們的檔案），但 Chien 要知道：這支函式的正確性只靠單元式直呼驗證。 | SEG-4（驗收備註） |
| **N4** | 🟡 | APOC `apoc.algo.dijkstra` 第 3 參數是「pipe 分隔的字串」`'METRO_LINK\|RAIL_LINK'`；shortest/cheapest **不要**把 `INTERCHANGE_TO` 放進去（否則會跨網亂走，違反 C1「跨網應 found=False」的預期）。 | SEG-5 / SEG-6 |
| **N5** | 🟡 | rail 與 metro 邊各自只有自己的票價欄位（metro=`fare_usd`、rail=`fare_standard_usd`/`fare_first_usd`）。Dijkstra 以某屬性為權重時，**該屬性必須存在於該路徑會走到的每一條邊**。因為 cheapest 只在「單一網路內」算（跨網走 interchange_path），所以只要 network 解析正確就安全 → 與 N1 同源，務必一起修。 | SEG-6 |
| **N6** | 🟡 | seed.cypher 要決定是「完整可獨立執行的鏡像」還是「代表性示意片段」。建議**代表性示意 + 明確註明權威 seeding 在 .py**（理由見 SEG-3）。 | SEG-3 |

---

## 1. 前置（不算 commit，動工前先做）

### PRE-1 開分支與環境
- `git checkout main && git pull origin main`
- `git fetch origin && git log HEAD..origin/main --oneline`（確認沒落後別人的 commit）
- `git checkout -b feature/Chien/neo4j-rewrite`
- 確認 `.env` 有 `NEO4J_URI=bolt://localhost:7688`（docker 對外是 7688，config.py 預設 7687 會連不上）
- `docker compose ps` → neo4j healthy

> 註：正式流程原本拆成 `neo4j-seeding` + `cypher-queries` 兩條分支。實務上一條 `feature/Chien/neo4j-rewrite` 即可，段內 commit 序列照樣乾淨。Chien 若想分兩條 PR 也行。

---

## 2. SEEDING 段落（seed_neo4j.py + seed.cypher）

### ─────────────────────────────────────────
### SEG-1 — 重寫 `seed_neo4j.py`：節點（MetroStation / NationalRailStation）
**檔案**：[skeleton/seed_neo4j.py](../skeleton/seed_neo4j.py)
**位置**：整個 `seed()`（目前 33–135 行），這段只先做「constraints + 兩種節點」。

**要做什麼**
1. 建 unique constraints（冪等）：
   - `CREATE CONSTRAINT IF NOT EXISTS FOR (s:MetroStation) REQUIRE s.station_id IS UNIQUE`
   - `CREATE CONSTRAINT IF NOT EXISTS FOR (s:NationalRailStation) REQUIRE s.station_id IS UNIQUE`
2. `MERGE` MetroStation（資料：`metro_stations.json`），節點屬性：
   - `station_id`、`name`、`lines`（**陣列**，JSON key 就叫 `lines`）、`is_interchange_national_rail`（bool）
3. `MERGE` NationalRailStation（資料：`national_rail_stations.json`），節點屬性：
   - `station_id`、`name`、`lines`（陣列）、`is_interchange_metro`（bool）、`interchange_metro_station_id`（字串或缺）

**注意陷阱**
- 移除舊的 `MATCH (n) DETACH DELETE n`？→ **保留**也可以（重置時方便），但既然全用 MERGE，第一行 DETACH DELETE 會讓「冪等」名存實亡。**建議移除 DETACH DELETE**，真要清空時改用 `docker compose down -v`（已在文件記錄、需三人協調）。請在程式碼留一行 comment 說明為何不在腳本內清庫。
- JSON 確認過的真實欄位名：metro 用 `is_interchange_national_rail` / `interchange_national_rail_station_id`；rail 用 `is_interchange_metro` / `interchange_metro_station_id`。**不要**自己發明 `metro_interchange_id`。

**驗收**
- `MATCH (n:MetroStation) RETURN count(n)` → 20
- `MATCH (n:NationalRailStation) RETURN count(n)` → 10

**commit**：`feat(graph): seed MetroStation/NationalRailStation nodes with constraints`

---

### ─────────────────────────────────────────
### SEG-2 — `seed_neo4j.py`：三種關係（METRO_LINK / RAIL_LINK / INTERCHANGE_TO + 票價）
**檔案**：[skeleton/seed_neo4j.py](../skeleton/seed_neo4j.py)
**位置**：接在 SEG-1 之後（取代舊的 71–128 行 CONNECTS_TO / INTERCHANGE_WITH 段）。

**要做什麼**
1. **METRO_LINK**（MetroStation→MetroStation，來源 metro 每站的 `adjacent_stations`），邊屬性：
   - `travel_time_min`、`line`
   - `fare_usd = round(1.0 + 0.5 * travel_time_min, 2)`（Q5/Q6：metro 單一票價，無 fare_class）
2. **RAIL_LINK**（NationalRailStation→NationalRailStation，來源 rail 每站 `adjacent_stations`），邊屬性：
   - `travel_time_min`、`line`
   - `fare_standard_usd = round(2.0 + 1.2 * travel_time_min, 2)`
   - `fare_first_usd    = round(2.0 + 2.0 * travel_time_min, 2)`
3. **INTERCHANGE_TO**（雙向兩條，MetroStation↔NationalRailStation），邊屬性：
   - `transfer_time_min = 5`（Q7 固定值）
   - 來源：metro 站若 `is_interchange_national_rail == true` 且有 `interchange_national_rail_station_id`，建 `(m)-[:INTERCHANGE_TO]->(nr)` 與 `(nr)-[:INTERCHANGE_TO]->(m)` 各一條。

**注意陷阱**
- JSON 的 `adjacent_stations` 是**單向各列一次**（A 列了 B、B 也列了 A）→ 用 `MERGE` 不會重複，方向各自成立，符合 Dijkstra 需求。
- 票價公式必須**寫進邊屬性**（不是查詢時才算）— 這正是 C2 / Q5=A 的核心。
- `MERGE (a)-[r:METRO_LINK {line:..., travel_time_min:...}]->(b)` 之後再 `SET r.fare_usd=...`；或一次帶齊屬性。擇一即可，注意 MERGE 的屬性會參與比對（建議 MERGE 只帶能唯一識別邊的 key，其餘用 SET）。

**驗收**
- `MATCH ()-[r:METRO_LINK]->() RETURN count(r)` → 約 40（雙向）
- `MATCH ()-[r:RAIL_LINK]->() RETURN count(r)` → 約 18
- `MATCH ()-[r:INTERCHANGE_TO]->() RETURN count(r)` → 換乘站數 × 2
- 抽查一條 RAIL_LINK：`fare_first_usd > fare_standard_usd` 必須成立

**commit**：`feat(graph): seed METRO_LINK/RAIL_LINK/INTERCHANGE_TO with fare and transfer attrs`

---

### ─────────────────────────────────────────
### SEG-3 — 補 `databases/graph/seed.cypher`（靜態評分雙保險，Q8 / N6）
**檔案**：[databases/graph/seed.cypher](../databases/graph/seed.cypher)（目前只有 deprecated 註解）

**要做什麼（決策：代表性鏡像）**
- 放入：兩條 constraint + 每種節點 ≥1 個 MERGE 範例 + 每種關係（METRO_LINK/RAIL_LINK/INTERCHANGE_TO）≥1 個 MERGE 範例，**屬性要齊全且與 .py 公式一致**（含 `fare_usd` / `fare_standard_usd` / `fare_first_usd` / `transfer_time_min`）。
- 檔頭明確註明：「權威 seeding 為 `skeleton/seed_neo4j.py`，本檔為 schema 可讀鏡像，供靜態閱讀與手動驗證」。

**為何不做「完整 30 節點 + 58 邊」literal 鏡像**
- 手寫全量易與 .py 不同步（改公式要改兩處），反而製造 bug。
- 評分對 seed.cypher 是「靜態看得到三種關係與屬性設計」即可（post-sync-review 評分風險表：Live A 看的是 label/relationship 命名）。
- 若 Chien 想要「完全可獨立執行的全量鏡像」，請改為由 .py 加一個 `--dump-cypher` 模式自動產生，避免手寫漂移（此為加分項，非必須）。

**驗收**：在 Neo4j Browser 貼上整檔可無錯誤執行（MERGE 冪等），且 `:schema` 能看到兩條 constraint。

**commit**：`feat(graph): add seed.cypher schema mirror for static grading`

---

## 3. QUERY 段落（queries.py）

> 開頭先處理 driver 與 import（SEG-4 內含）。每支函式一段、一 commit。
> **順序刻意由易到難**：station_connections → shortest → cheapest → delay_ripple → alternative → interchange。

### ─────────────────────────────────────────
### SEG-4 — `queries.py` 開頭重構：per-call driver + 移除舊 singleton
**檔案**：[databases/graph/queries.py](../databases/graph/queries.py)
**位置**：1–69 行（import 區、`_DRIVER` singleton、`_get_driver`、`example_count_nodes`、殘留 `# TODO`）。

**要做什麼**
1. 移除 module-level `_DRIVER` singleton（35 行）與 `_get_driver`（38–40 行）。
2. 改成 per-call：
   ```python
   import os
   from neo4j import GraphDatabase

   def _driver():
       # per-call for simplicity; production should use a module-level singleton
       uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
       auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "transitflow"))
       return GraphDatabase.driver(uri, auth=auth)
   ```
3. 保留 `_infer_network()`（43–56 行）——SEG-6 會用到，**它是 N1 修正的關鍵**。
4. 移除殘留 `# TODO: Implement...`（68 行）。

**注意陷阱（重要）**
- per-call driver **每支函式內務必用 `with`**：`with _driver() as driver: with driver.session() as session:` —— 不用 `with` 包 driver，per-call 會持續累積未關閉的連線池。這點現有 code（singleton）沒這問題，改 per-call 後一定要補。
- N3 備註：`query_station_connections` 不被 agent import，僅 Live C6 直呼測試 → 它的回傳格式要對，但不必擔心 agent 串接。

**驗收**：`python -c "from databases.graph.queries import _driver; _driver().verify_connectivity()"` 不報錯。

**commit**：`refactor(graph): switch queries to per-call driver, drop singleton and scaffold`

---

### ─────────────────────────────────────────
### SEG-5 — `query_station_connections`（Live C6 /2，暖身）
**檔案**：[databases/graph/queries.py:417-440](../databases/graph/queries.py#L417-L440)

**要做什麼**：把 `CONNECTS_TO` 改成無向 `-[r:METRO_LINK|RAIL_LINK]-`，移除回傳中的 `r.network`（新 schema 邊上沒有 network，C3 已指出）。
**回傳格式**：`list[dict]`，每筆 `{station_id, name, line, travel_time_min}`，按 `travel_time_min` 排序；空 → `[]`。

**注意陷阱**
- 用**無向** `-[r:...]-`，因為 adjacency 是雙向語意；用有向 `->` 只會拿到一半鄰居。
- 不要回傳 `r.network`（屬性已不存在）。需要分網時用關係型別 `type(r)` 或 station_id 前綴。

**commit**：`feat(graph): implement query_station_connections on new schema`

---

### ─────────────────────────────────────────
### SEG-6 — `query_shortest_route`（Live C1 /8，Dijkstra by time）
**檔案**：[databases/graph/queries.py:74-130](../databases/graph/queries.py#L74-L130)

**要做什麼**：relType 字串改 `'METRO_LINK|RAIL_LINK'`、節點 MATCH 拿掉 `:Station` label（用 `(o {station_id:$origin_id})`，跨 label 匹配），weight 屬性維持 `travel_time_min`。
**回傳格式**（維持現有，已對）：`{found, origin_id, destination_id, total_time_min, path:[{station_id,name}], legs:[{line,travel_time_min}]}`；無路徑 → `found=False`。

**注意陷阱（N4）**
- relType **只放** `'METRO_LINK|RAIL_LINK'`，**不要**加 `INTERCHANGE_TO` → 跨網（如 MS01→NR05）才會正確 `found=False`（符合 C1 checklist「不連通回 False、不 raise」）。
- 無 label 的 `MATCH (o {station_id:$x})` 可同時命中 MetroStation/NationalRailStation；可保留也可依 network 加 label，保留較通用。

**commit**：`feat(graph): implement query_shortest_route with APOC dijkstra (time)`

---

### ─────────────────────────────────────────
### SEG-7 — `query_cheapest_route`（Live C2 /7）★含 N1 關鍵修正★
**檔案**：[databases/graph/queries.py:135-208](../databases/graph/queries.py#L135-L208)

**要做什麼**
1. **改用圖內邊的票價屬性當 Dijkstra 權重**（取代舊的 Python `stops×係數` 估算）。
2. **N1 修正：network 解析**——不可用 `if network == "national_rail"` 判斷（agent 只會傳 `"auto"`）。正確做法：
   ```python
   net = network if network in ("metro", "national_rail") else _infer_network(origin_id)
   # _infer_network 回 "metro" / "national_rail" / "unknown"
   if net == "metro":
       weight_prop = "fare_usd"
   else:  # national_rail
       weight_prop = "fare_standard_usd" if fare_class == "standard" else "fare_first_usd"
   ```
   - 同時相容 agent 可能傳的 `"rail"`：把 `"rail"` 也映射到 `"national_rail"`。
3. weight_prop 已是**固定字串集合**之一（不含使用者原字串），可安全 f-string 進 Cypher：
   `CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', '{weight_prop}')`
4. 回傳 `total_fare_usd = weight`、legs 帶 `fare_usd: rel.{weight_prop}`。

**回傳格式**：`{found, origin_id, destination_id, total_fare_usd, fare_class, path, legs}`；無路徑 → `found=False, total_fare_usd=None`。

**注意陷阱（N1 + N5）**
- 若 network 解析錯，rail 路線會用 `fare_usd`（RAIL_LINK 沒這欄）→ APOC 抓不到權重，路徑/票價全錯。這是本段**最容易出錯之處**，務必用 `_infer_network`。
- C2 驗收必跑：`fare_class="first"` 的 `total_fare_usd` 要 **不等於** `"standard"`，證明 fare_class 真的影響權重（不是只影響顯示）。
- relType 同 N4，只放 `'METRO_LINK|RAIL_LINK'`。

**commit**：`feat(graph): implement query_cheapest_route with in-graph fare weighting`

---

### ─────────────────────────────────────────
### SEG-8 — `query_delay_ripple`（Live C5 /3）
**檔案**：[databases/graph/queries.py:352-412](../databases/graph/queries.py#L352-L412)

**要做什麼**：把 `:Station` / `CONNECTS_TO` 換成新 schema（無 label `(s {station_id:$sid})`、`-[:METRO_LINK|RAIL_LINK*1..{safe_hops}]-`）。`lines` 取自 `s.lines`。邏輯（hops=0 特判、`int(hops)` 防注入、f-string 嵌入上限）**保留現有正確結構**。
**回傳格式**：`list`，每筆 `{station_id, name, hops_away, lines_affected}`；hops=0 → 只回起點本身（`hops_away=0`，**不是空 list**）。

**注意陷阱**
- 可變長度上限 `*1..{safe_hops}` 必須 `safe_hops = max(0, int(hops))` 後才 f-string；`$param` 不能用在上限。
- 用**無向** `-[...]-`（延誤波及不分方向）。
- C5 必跑 `hops=0` 只回 MS01 本身那條 checklist。

**commit**：`feat(graph): implement query_delay_ripple on new schema (hops=0 handled)`

---

### ─────────────────────────────────────────
### SEG-9 — `query_alternative_routes`（Live C3 /7）
**檔案**：[databases/graph/queries.py:213-259](../databases/graph/queries.py#L213-L259)

**要做什麼**：路徑樣式改 `(o {...})-[:METRO_LINK|RAIL_LINK*1..10]-(d {...})`（無向），`WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)` 保留，`reduce` 累加 `travel_time_min`，`ORDER BY total_time_min LIMIT $max_routes`。
**回傳格式**：`list`，每筆 `{route:[{station_id,name}], total_time_min}`；空 → `[]`；任何回傳路徑都不得含 avoid。

**注意陷阱**
- 改無向 `-[...]-` 後，`*1..10` 在小圖上仍 OK；若怕路徑爆量可保守設 `*1..8`。先用 10，驗收若慢再降。
- agent 會把回傳包成 `{"route_number": i+1, "legs": r}`（agent.py:431）——這是 agent 端處理，**我們不動**，但要知道我們回的整個 dict 會被當成 `legs` 塞進去，所以回傳結構維持「list of dict」即可。

**commit**：`feat(graph): implement query_alternative_routes with station avoidance`

---

### ─────────────────────────────────────────
### SEG-10 — `query_interchange_path`（Live C4 /8）★含 N2 key 修正★
**檔案**：[databases/graph/queries.py:264-347](../databases/graph/queries.py#L264-L347)

**要做什麼**
1. 關係改 `-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-`（**無向**），`WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')`（確保真的跨網），`ORDER BY length(p) LIMIT 1`。
2. **N2 修正回傳 key**：改用 `path`（不是 `stations`）與 `interchange_points`（不是 `interchanges`），對齊評分與正式流程：
   ```python
   {
     "found": True,
     "path": [{"station_id","name", ("interchange": True 於換乘端點)}],
     "interchange_points": [{"from","to","transfer_time_min": 5}],
     "total_time_min": Σ(*_LINK 的 travel_time_min) + 換乘次數×5
   }
   # 無路徑 → {"found": False, "path": [], "interchange_points": [], "total_time_min": None}
   ```
3. Python 端：遇 `INTERCHANGE_TO` 邊，把兩端 node 標 `"interchange": True`，並 append 一筆 interchange_point。

**注意陷阱**
- `total_time_min` 只加 `*_LINK` 邊的 `travel_time_min`（INTERCHANGE_TO 邊沒有 `travel_time_min`，它是 `transfer_time_min`），換乘時間另外用「次數×5」加總——別把 `None` 加進去。
- `type(r)` 用關係物件的 `.type`（Python neo4j 是 `rel.type`）；屬性用 `rel["transfer_time_min"]`。
- 同網輸入（MS→MS）不應 raise：因 `WHERE any(... INTERCHANGE_TO)` 不成立 → 無匹配 → 回 `found=False`（符合 C4 checklist）。

**commit**：`feat(graph): implement query_interchange_path with INTERCHANGE_TO + correct keys`

---

## 4. 收尾段落

### ─────────────────────────────────────────
### SEG-11 — Inline「為什麼」註解（Code Quality /2，S2）
**檔案**：`queries.py` + `seed_neo4j.py`
**要做什麼**：補 3–5 條解釋 WHY（非 WHAT）的註解，例如：
- 為何 INTERCHANGE_TO 建雙向兩條邊（Dijkstra/無向遍歷都能走）
- 為何 `*1..N` 上限要 `int()` 後 f-string（Cypher 不接受 `$param` 當上限，且防注入）
- 為何 cheapest 用 `_infer_network` 解析而非比對字面值（agent 傳 auto）
- 為何 metro 不分 fare_class（Q6 單一票價）
- 為何 per-call driver（簡潔；production 改 singleton）

**commit**：`docs(graph): add rationale comments to seeding and queries`

---

### ─────────────────────────────────────────
### SEG-12 — 實跑驗證（不一定要 commit）
1. **需三人協調**後：`docker compose down -v && docker compose up -d`
2. `python skeleton/seed_neo4j.py` → 看節點/邊統計符合 SEG-1/2 驗收數字
3. 依 [Chien_graph_正式開發流程.md](Chien_graph_正式開發流程.md) 的 **Live Testing 自我驗證 Checklist（C1–C6）** 逐項跑過：
   - C1 跨網 `("MS01","NR05")` → `found=False` 不 raise
   - C2 `fare_class="first"` ≠ `"standard"`
   - C3 路徑不含 avoid、`max_routes=1` 只回 1 條
   - C4 `("MS01","NR05")` → `found=True`、`interchange_points` 非空、key 是 `path`/`interchange_points`
   - C5 `hops=0` 只回起點
   - C6 `("MS01")` 每筆有 `travel_time_min`

---

### ─────────────────────────────────────────
### SEG-13 — Q11：AI_SESSION_CONTEXT 新 schema 文字（Chien 出稿、蔡晟郁貼）
**不是改 code**。Chien 寫一段描述新 graph schema 的文字（節點 `MetroStation`/`NationalRailStation`；關係 `METRO_LINK`/`RAIL_LINK`/`INTERCHANGE_TO` 及各自屬性、票價欄位、`transfer_time_min=5`），交給蔡晟郁更新 `AI_SESSION_CONTEXT.md`（中英兩版）。
> 跨檔案邊界：我們不直接動 `AI_SESSION_CONTEXT.md`。

---

## 5. Commit 序列總表（交給 Sonnet 照順序跑）

| 段 | commit message |
|----|----------------|
| SEG-1 | `feat(graph): seed MetroStation/NationalRailStation nodes with constraints` |
| SEG-2 | `feat(graph): seed METRO_LINK/RAIL_LINK/INTERCHANGE_TO with fare and transfer attrs` |
| SEG-3 | `feat(graph): add seed.cypher schema mirror for static grading` |
| SEG-4 | `refactor(graph): switch queries to per-call driver, drop singleton and scaffold` |
| SEG-5 | `feat(graph): implement query_station_connections on new schema` |
| SEG-6 | `feat(graph): implement query_shortest_route with APOC dijkstra (time)` |
| SEG-7 | `feat(graph): implement query_cheapest_route with in-graph fare weighting` |
| SEG-8 | `feat(graph): implement query_delay_ripple on new schema (hops=0 handled)` |
| SEG-9 | `feat(graph): implement query_alternative_routes with station avoidance` |
| SEG-10 | `feat(graph): implement query_interchange_path with INTERCHANGE_TO + correct keys` |
| SEG-11 | `docs(graph): add rationale comments to seeding and queries` |

> SEG-12（驗證）、SEG-13（AI_SESSION_CONTEXT）不一定產生 commit。

---

## 6. 一句話交付指引（給 Chien）

> 把本檔的某一個 `SEG-N` 整段貼給 Sonnet，說「依此段規格實作並 commit」即可。
> **優先盯死的兩個雷**：SEG-7 的 N1（network 解析）、SEG-10 的 N2（回傳 key 名）—— 這兩個不修，code 跑得動但評分會默默失分。
