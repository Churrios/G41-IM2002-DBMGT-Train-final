# Section 3 — 圖形資料庫設計理由

> 負責人：黃謙儒 | 配分：/25

本系統的雙軌路網（城市捷運 M1–M4 + 國鐵 NR1–NR2）以 **Neo4j 圖形資料庫**建模，
專責處理「路徑」類查詢：最短路徑、最便宜路徑、繞站替代路線、跨網換乘路徑、誤點漣漪分析。
關聯式資料庫（PostgreSQL）負責交易性資料（訂位、付款、座位），兩者各取所長。
本節說明圖形模型的節點 / 關係 / 屬性設計理由、為何路由查詢用 graph 優於 relational、
具體查詢類型，以及節點識別的選擇。

實際拓撲：**30 個節點**（20 個 MetroStation + 10 個 NationalRailStation）、
**66 條邊**（42 條 METRO_LINK + 18 條 RAIL_LINK + 6 條 INTERCHANGE_TO）。

---

## 3.1 Node / Relationship / Property 設計選擇

圖形模型的核心是決定「什麼當節點、什麼當關係、什麼當屬性」。我們的選擇如下。

### 節點（Node）：車站

我們把**車站**設計成節點，理由不只是「車站是一個實體」，而是車站在本系統中具備節點該有的三個特徵：

1. **被多條路線、多筆班次重複引用（多對多）**：一個車站（如 MS01 Central Square）同時屬於
   M1、M2 兩條捷運線，也被多筆 schedule 的停靠序列引用。節點天然支援「一個實體被多個關係指向」
   的多對多結構，不必像關聯式那樣靠 junction table 串接。
2. **是 pattern matching（圖形遍歷）的對象**：所有路由查詢的本質都是「從某站出發，沿著連線走到
   另一站」。車站必須是可被 `MATCH (s {station_id: ...})` 直接定位、並可往外擴展鄰居的單位。
3. **需要穩定的身分**：車站要能跨班次、跨網路被一致地參照（見 §3.4）。

#### 為何採「分離標籤」（split-label）而非單一 `Station`

我們把車站拆成兩種節點標籤 **`MetroStation`** 與 **`NationalRailStation`**，而不是用單一
`Station` 標籤加一個 `network` 屬性區分。理由：

- **對齊評分 / 測試標準**：Task 4 與 Live 測試以 label 名稱明文檢查兩種車站是否存在，
  分離標籤直接對應。
- **查詢可依網路限定**：路由查詢可用關係型別 `'METRO_LINK|RAIL_LINK'` 將遍歷限制在同一網路內，
  使「同網最短路徑」與「跨網換乘」成為兩種語意清楚的查詢，而非靠屬性過濾。
- **兩網屬性集本就不同**：捷運站有 `is_interchange_national_rail`，國鐵站有
  `is_interchange_metro` 與 `interchange_metro_station_id`，分離標籤讓各自的屬性集自然成形。

### 關係（Relationship）：車站之間的連線

車站間的連線設計成**關係**，分三種型別：

| 關係型別 | 連接 | 用途 |
|----------|------|------|
| `METRO_LINK` | `(MetroStation)→(MetroStation)` | 捷運區段 |
| `RAIL_LINK` | `(NationalRailStation)→(NationalRailStation)` | 國鐵區段 |
| `INTERCHANGE_TO` | `(MetroStation)↔(NationalRailStation)` | 跨網實體換乘 |

連線之所以適合做關係而非另一張表，是因為它具備關係的兩個本質：

1. **有方向性**：班次有行進方向；以有向邊建模，Dijkstra 可沿方向遍歷。
   （`INTERCHANGE_TO` 在 seeding 時刻意建**雙向兩條**有向邊，使換乘可雙向通行。）
2. **承載屬性**：每條連線本身帶有「通過這段要花多少時間、多少錢」的資訊，這是**邊的屬性**，
   不屬於任何單一車站。這正是圖形模型勝過關聯式 FK 的關鍵——relational FK 只能表達
   「A 與 B 有關聯」，無法在這個關聯**上**自然地掛載 `travel_time_min`、`fare_usd` 等屬性；
   圖形的關係則可以。

### 屬性（Property）：放在節點還是邊上

屬性的歸屬遵循「屬性描述的是誰」這個原則：

- **放在節點上**：`station_id`、`name`、`lines`、`is_interchange_*` ——這些描述的是車站本身。
- **放在邊上**：
  - `METRO_LINK`：`line`、`travel_time_min`、`fare_usd`
    （單一票價，`fare_usd = round(1.0 + 0.5 × travel_time_min, 2)`）
  - `RAIL_LINK`：`line`、`travel_time_min`、`fare_standard_usd`、`fare_first_usd`
    （國鐵分標準 / 頭等兩級票價）
  - `INTERCHANGE_TO`：`transfer_time_min`（固定 5 分鐘；換乘不走實體軌道，故無 `travel_time_min`）

把 `travel_time_min` 與票價放在**邊上**而非節點上，原因有二：(1) 這些是「通過某一區段」的成本，
本質上是區段（邊）的屬性而非端點（站）的屬性；(2) 它們是最短路徑演算法的**權重來源**——
`apoc.algo.dijkstra` 直接讀取邊上的權重屬性做計算（見 §3.2、§3.3）。
特別是票價在 seeding 時就寫進邊，使「最便宜路徑」能直接以 `fare_*_usd` 當權重跑 Dijkstra，
讓 fare_class 真正改變被選到的**路徑**，而不只是改變最後總額。

---

## 3.2 Graph vs Relational 論證

路由查詢（最短路徑、誤點漣漪）本質上是**加權圖上的圖遍歷問題**。我們主張圖形資料庫在此優於
關聯式資料庫，理由是具體的演算法差異，而非籠統的「graph 比較快」。

### 圖形作法：Dijkstra / BFS + index-free adjacency

Neo4j 以 **index-free adjacency** 儲存：每個節點直接持有指向其鄰居關係的指標，
因此「取得某站的所有鄰站」是 **O(1)**（與全圖大小無關），不需要任何 join。
在此基礎上：

- **最短路徑**用 `apoc.algo.dijkstra`（加權 Dijkstra）或 `shortestPath()`（無權 BFS）。
  Dijkstra 以優先佇列展開，複雜度約 **O((V + E) log V)**；BFS 找到第一條路徑即停。
- 演算法只觸碰「從起點實際可達」的子圖，不會掃描無關節點。

### 關聯式作法：recursive CTE 的代價

關聯式資料庫沒有原生圖遍歷，要在 SQL 表達「找最短路徑」必須用 **recursive CTE**
（遞迴共同表達式），把邊存成一張 `edges(from, to, weight)` 表後遞迴展開。其根本問題：

1. **每一層遞迴都要對 edge 表做一次 join**：第 k 層代表長度 k 的所有路徑，
   join 次數隨深度線性累加，但結果集大小可能隨深度**組合爆炸**。
2. **必須累積「已訪節點」路徑集以防環**：每條中間路徑都得攜帶它走過的節點清單，
   在每層遞迴中比對以避免無限繞圈，這帶來額外的儲存與比對成本。
3. **沒有「找到最短就停」的原生機制**：recursive CTE 會展開**所有**符合條件的路徑，
   最後才用 `MIN(total_weight)` 取最短——無法像 Dijkstra/BFS 那樣提早剪枝。

因此在節點稍多、路徑稍長時，relational 解法的中間結果會指數膨脹而超時。

### 本專案的實證

這個差異在我們自己的開發中具體發生過：`query_interchange_path` 最初用變長路徑
`-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-` 做**全列舉**（窮舉所有路徑再挑），
在僅 30 節點的圖上對較遠站對就 **>30 秒超時**——這正是「展開所有路徑」的組合爆炸。
改用 Neo4j 內建的 `shortestPath()`（BFS，找到第一條即回傳）後，同樣查詢 **<1 秒**完成。
同一個圖、同一個問題，演算法從「窮舉」換成「BFS 提早停止」就是數量級的差距——
這就是圖形模型適合路由查詢的根本原因。

---

## 3.3 查詢類型說明

以下說明兩種代表性查詢，以及節點 / 關係結構**如何讓它們得以表達**。

### 查詢一：同網最短路徑（`query_shortest_route`）

在同一網路內找出總旅行時間最短的路徑：

```cypher
MATCH (o {station_id: $origin_id}), (d {station_id: $dest_id})
CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', 'travel_time_min')
YIELD path, weight
RETURN [n IN nodes(path) | {station_id: n.station_id, name: n.name}] AS stations,
       weight AS total_time_min
```

**graph model 如何使其可表達**：
- 關係型別過濾 `'METRO_LINK|RAIL_LINK'` 讓遍歷只走「同網軌道邊」，**刻意排除**
  `INTERCHANGE_TO`，因此同網不可達時自然回 `found=False`，語意乾淨。
- `travel_time_min` 直接存在邊上，成為 Dijkstra 的權重參數——演算法不需要在查詢時計算成本。
- 把 `'travel_time_min'` 換成 `'fare_usd'` / `'fare_standard_usd'`，同一段 Dijkstra 立刻變成
  **最便宜路徑**查詢（`query_cheapest_route`），複用同一套圖結構。

### 查詢二：跨網換乘路徑（`query_interchange_path`）

從捷運站到國鐵站（或反向），必須跨越網路邊界：

```cypher
MATCH p = shortestPath(
            (o {station_id: $origin_id})
            -[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..10]-
            (d {station_id: $dest_id}))
WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
```

**graph model 如何使其可表達**：
- 關鍵在於**把三種關係型別混在同一個 pattern** 裡遍歷：軌道邊（`METRO_LINK`/`RAIL_LINK`）
  負責網內移動，`INTERCHANGE_TO` 邊負責跨越捷運↔國鐵的網路邊界。一條路徑可以「捷運走幾站 →
  經 INTERCHANGE_TO 換到國鐵 → 國鐵再走幾站」，全部在單一查詢中表達。
- `WHERE any(... INTERCHANGE_TO)` 保證回傳的確實是「有換乘」的跨網路徑。
- 同樣的需求在關聯式資料庫中必須跨 `metro_schedule_stops`、`national_rail_schedule_stops`
  與換乘對應表做多重 UNION，再包進 recursive CTE 才能勉強表達——圖形模型用一個 pattern 就解決。

> （第三種查詢 `query_delay_ripple` 用變長遍歷 `-[:METRO_LINK|RAIL_LINK*1..N]-` 配合
> `min(length(path))`，找出誤點站 N 跳之內受影響的所有車站，同樣是圖形遍歷的自然應用。）

---

## 3.4 Node Identity

我們以 **`station_id`** 作為節點的唯一識別，並對每種標籤建立 unique constraint：

```cypher
CREATE CONSTRAINT FOR (s:MetroStation)        REQUIRE s.station_id IS UNIQUE;
CREATE CONSTRAINT FOR (s:NationalRailStation) REQUIRE s.station_id IS UNIQUE;
```

選擇 `station_id`（如 `MS01`、`NR01`）作為節點身分的理由：

1. **來自來源資料的穩定外部鍵**：`station_id` 直接取自 mock data 的 JSON，是天然、穩定的識別碼，
   不需要另造代理鍵（surrogate key）。
2. **跨兩網全域唯一**：捷運站以 `MS` 前綴、國鐵站以 `NR` 前綴，命名空間不重疊，
   即使混在同一個跨網查詢裡也不會撞號。
3. **與 PostgreSQL 1:1 對應，跨庫查詢免轉換**：Neo4j 的 `station_id` 與關聯式
   `metro_stations.station_id` / `national_rail_stations.station_id` 完全相同，
   應用層拿到圖形回傳的 `station_id` 可直接到 PostgreSQL 查站名、班次等明細，
   兩個資料庫間不需要任何 ID 對照轉換。
4. **人類可讀**：便於除錯與在 Neo4j Browser 手動驗證。

unique constraint 還附帶建立索引，讓 `MATCH (s {station_id: ...})` 的起點定位是索引查找而非掃描，
使每次路由查詢都能快速錨定起訖節點。
