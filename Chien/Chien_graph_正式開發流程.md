# TransitFlow — Graph DB 正式開發流程（Chien 專用）

> 負責範圍：`databases/graph/queries.py`（主力）、`skeleton/seed_neo4j.py`（已完成，需驗證）
> Branch：`feature/Chien/graph-queries`
> 對應分數：Task 3 /10（共享）、Task 4 /8、Task 5 /10、Live Section C /35 → **合計 /63**

---

## 現況確認（開始前必讀）

| 項目 | 狀態 |
|------|------|
| `skeleton/seed_neo4j.py` | ✅ 已 merge（commit `89d214b`），圖已建立 |
| 圖 schema | **Station + CONNECTS_TO + INTERCHANGE_WITH**（團隊定案） |
| `databases/graph/queries.py` | ❌ 全部 6 個函式仍是 `raise NotImplementedError` |
| APOC plugin | ✅ docker-compose.yml 已啟用（Dijkstra 可用） |
| GDS plugin | ❌ 未安裝（不能用 gds.* 語法） |

> ⚠️ **Task 4 評分風險**：評分標準 Task 4 會檢查 `METRO_LINK`、`RAIL_LINK`、`INTERCHANGE_TO` 等名稱。
> 現有 schema 使用 `CONNECTS_TO`/`INTERCHANGE_WITH`，Task 4 的節點標籤/關係命名項目可能扣分。
> 這是 **已知風險**，團隊已決定沿用現有 schema 不改。詳見附錄 Q1。

---

## Phase 0 — 每次工作前的環境確認

```bash
# 1. 確認目前 branch
git branch

# 2. 確認 main 是否有其他人的新 commit
git fetch origin
git log HEAD..origin/main --oneline
# 若有新 commit → git merge origin/main（或 rebase）

# 3. 確認 Docker 正常
docker compose ps
# neo4j 應顯示 healthy

# 4. 確認 .env 有設正確的 bolt 連接埠
# docker-compose.yml 對主機映射是 7688:7687
# config.py 預設是 bolt://localhost:7687 → 從主機跑腳本時會連不上！
# .env 必須有：NEO4J_URI=bolt://localhost:7688

# 5. 確認 seed 已跑完、圖有資料
# 在 Neo4j Browser（http://localhost:7475）執行：
#   MATCH (n:Station) RETURN count(n) AS nodes;         → 期望 30
#   MATCH ()-[r]->() RETURN count(r) AS edges;          → 期望 60+
#   MATCH ()-[r:INTERCHANGE_WITH]->() RETURN count(r);  → 期望 6
```

---

## Phase 1 — 開分支

```bash
# 從 main 開新分支（第一次）
git checkout main
git pull origin main
git checkout -b feature/Chien/graph-queries
```

---

## SYNC 1 前工作 — 函式 1–5

在 `databases/graph/queries.py` 實作下列 5 個函式，每個函式完成後立即 commit。

### 準備：queries.py 開頭改成 singleton driver

把現有 `_driver()` 函式替換成：

```python
from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# 模組載入時建立一次，所有查詢共用（production best practice）
_DRIVER = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD),
)

def _get_driver():
    return _DRIVER

def _infer_network(station_id: str) -> str:
    if station_id.upper().startswith("MS"):
        return "metro"
    elif station_id.upper().startswith("NR"):
        return "national_rail"
    return "unknown"
```

**commit:** `feat(graph): replace per-call driver with module-level singleton`

---

### 函式 1：`query_station_connections` — 直接相鄰站點（最簡單，先暖身）

**評分：** Live C6 /2

**回傳格式：**
```python
[
    {"station_id": "MS05", "name": "Westfield", "line": "M1", "travel_time_min": 3, "network": "metro"},
    ...
]
# 空結果 → []，絕不 raise
```

**Cypher：**
```cypher
MATCH (s:Station {station_id: $station_id})-[r:CONNECTS_TO]->(n:Station)
RETURN n.station_id AS station_id, n.name AS name,
       r.line AS line, r.travel_time_min AS travel_time_min, r.network AS network
ORDER BY travel_time_min
```

**commit:** `feat(graph): implement query_station_connections`

---

### 函式 2：`query_shortest_route` — 最快路線（Dijkstra by travel_time）

**評分：** Live C1 /8（metro 4 分、rail 4 分）

**回傳格式：**
```python
{
    "found": True,
    "origin_id": "MS01",
    "destination_id": "MS09",
    "total_time_min": 15,
    "path": [{"station_id": "MS01", "name": "Central Square"}, ...],
    "legs": [{"line": "M1", "travel_time_min": 3}, ...]
}
# 無路徑 → {"found": False, "path": [], "total_time_min": None}
```

**Cypher（用 APOC dijkstra）：**
```cypher
MATCH (o:Station {station_id: $origin_id}), (d:Station {station_id: $dest_id})
CALL apoc.algo.dijkstra(o, d, 'CONNECTS_TO', 'travel_time_min')
YIELD path, weight
RETURN
    [node in nodes(path) | {station_id: node.station_id, name: node.name}] AS stations,
    [rel in relationships(path) | {line: rel.line, travel_time_min: rel.travel_time_min}] AS legs,
    weight AS total_time_min
```

**實作重點：**
- `network="auto"` → 用 `_infer_network()` 推斷；但跨網路（MS→NR）時 agent.py 已在呼叫前自動改走 `query_interchange_path`，此函式只需處理同網路
- APOC 回傳是 path 物件，需解包成 stations list + legs list
- 查無結果時回傳 `{"found": False, "path": [], "total_time_min": None}`

**commit:** `feat(graph): implement query_shortest_route with APOC dijkstra`

---

### 函式 3：`query_delay_ripple` — 延誤波紋分析

**評分：** Live C5 /3

**回傳格式：**
```python
[
    {"station_id": "MS01", "name": "Central Square", "hops_away": 0, "lines_affected": ["M1","M2"]},
    {"station_id": "MS02", "name": "Riverside",      "hops_away": 1, "lines_affected": ["M1"]},
    ...
]
# hops=0 只回傳延誤站本身（hops_away=0）
# 空結果 → []
```

> ⚠️ **Cypher 陷阱：** `CONNECTS_TO*1..$hops` 裡的 `$hops` **不能** 直接用查詢參數，Cypher 不支援。
> 必須在 Python 端先 `int()` 轉型後用 f-string 組入 Cypher，或用 APOC `subgraphNodes`。

**推薦做法：在 Python 端 int() 驗證後內嵌，並特判 hops=0：**
```python
safe_hops = max(0, int(hops))  # 防止注入：int() 轉型確保是整數

# 取得起點資訊
start = session.run(
    "MATCH (s:Station {station_id: $sid}) RETURN s.station_id AS station_id, s.name AS name, s.lines AS lines_affected",
    sid=delayed_station_id
).single()
if not start:
    return []

start_dict = {"station_id": start["station_id"], "name": start["name"],
              "hops_away": 0, "lines_affected": list(start["lines_affected"] or [])}
if safe_hops == 0:
    return [start_dict]  # 評分 C5：hops=0 只回傳本站

# safe_hops 是 Python int，用 f-string 內嵌（已驗證安全）
cypher = f"""
MATCH (s:Station {{station_id: $station_id}})-[:CONNECTS_TO*1..{safe_hops}]->(affected:Station)
RETURN DISTINCT
    affected.station_id AS station_id,
    affected.name AS name,
    min(length(shortestPath((s)-[:CONNECTS_TO*]-(affected)))) AS hops_away,
    affected.lines AS lines_affected
ORDER BY hops_away
"""
result = session.run(cypher, station_id=delayed_station_id)
return [start_dict] + [dict(r) for r in result]
```

**commit:** `feat(graph): implement query_delay_ripple with hops=0 handling`

---

### 函式 4：`query_alternative_routes` — 避開特定站的備選路線

**評分：** Live C3 /7

**回傳格式：**
```python
[
    {"route": [{"station_id": "NR01", "name": "Central Station"}, ...], "total_time_min": 50},
    {"route": [...], "total_time_min": 65},
]
# 空結果 → []，路徑不得包含 avoid_station_id
```

**Cypher：**
```cypher
MATCH p = (o:Station {station_id: $origin_id})
          -[:CONNECTS_TO*1..10]->
          (d:Station {station_id: $dest_id})
WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)
RETURN [n IN nodes(p) | {station_id: n.station_id, name: n.name}] AS route,
       reduce(t=0, r IN relationships(p) | t + r.travel_time_min) AS total_time_min
ORDER BY total_time_min
LIMIT $max_routes
```

**實作重點：**
- `$max_routes` 在 Cypher 的 LIMIT 可以用參數（與 `*N` 的可變長度不同）
- 評分 C3 明確測試 `max_routes=1` 只回傳 1 條

**commit:** `feat(graph): implement query_alternative_routes with station avoidance`

---

### 函式 5：`query_interchange_path` — 跨網路換乘路線

**評分：** Live C4 /8

**回傳格式：**
```python
{
    "found": True,
    "stations": [
        {"station_id": "MS01", "name": "Central Square"},
        {"station_id": "NR01", "name": "Central Station", "interchange": True},
        ...
    ],
    "interchanges": [{"from": "MS01", "to": "NR01", "transfer_time_min": 3}],
    "total_time_min": 25
}
# 無路徑 → {"found": False, "stations": [], "interchanges": [], "total_time_min": None}
```

**Cypher：**
```cypher
MATCH p = (o:Station {station_id: $origin_id})
          -[:CONNECTS_TO|INTERCHANGE_WITH*1..20]->
          (d:Station {station_id: $dest_id})
WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_WITH')
RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
ORDER BY length(p)
LIMIT 1
```

**實作重點：**
- Python 端解析 `path_nodes` + `path_rels`，標記換乘點（遇到 `INTERCHANGE_WITH` 邊的兩端 node）
- `transfer_time_min` 固定估算 **5 分鐘**（JSON 沒有此欄位，用常數）
- `total_time_min` = 所有 CONNECTS_TO 邊的 travel_time_min 總和 + 換乘次數 × 5
- 同網路輸入（例如 MS→MS）：此函式仍嘗試找路，找不到就 `{"found": False, ...}`

**commit:** `feat(graph): implement query_interchange_path with INTERCHANGE_WITH traversal`

---

## 🔴 SYNC 1 — 推上 remote，等三人一起 merge

```bash
git push -u origin feature/Chien/graph-queries
# 通知蔡晟郁：函式 1–5 已 push，等你和蔣 ready 一起開 PR
```

**Sync 1 PR merge 順序**（由蔡晟郁協調）：
1. 蔡開 PR `feature/tsai/relational-queries` → main
2. 黃開 PR `feature/Chien/graph-queries` → main
3. 蔣開 PR `feature/jiang/vector-db` → main
4. **蔡先 merge → 黃 merge → 蔣 merge**

**Sync 1 後立即執行：**
```bash
git checkout feature/Chien/graph-queries
git merge main
# main 上現在有蔡的 query_metro_fare / query_national_rail_fare → 可以開始函式 6
```

---

## SYNC 2 前工作 — 函式 6

### 函式 6：`query_cheapest_route` — 最低票價路線

> **前置條件：** Sync 1 完成後，`git merge main` 取得蔡的 `query_metro_fare` / `query_national_rail_fare`。

**評分：** Live C2 /7（standard fare 4 分、fare_class 不同結果 3 分）

**回傳格式：**
```python
{
    "found": True,
    "total_fare_usd": 12.50,
    "fare_class": "standard",
    "path": [{"station_id": "NR01", "name": "Central Station"}, ...],
    "legs": [{"line": "NR1", "travel_time_min": 12}, ...]
}
# 無路徑 → {"found": False, "total_fare_usd": None, "fare_class": fare_class}
```

**實作邏輯：**
```python
from databases.relational.queries import query_metro_fare, query_national_rail_fare

def query_cheapest_route(origin_id, destination_id, network="auto", fare_class="standard"):
    # 1. 用 Dijkstra 找最短時間路線（同 query_shortest_route）
    # 2. stops_travelled = len(path) - 1
    # 3. 查票價：
    #    - metro → query_metro_fare(schedule_id, stops_travelled)
    #    - national_rail → query_national_rail_fare(schedule_id, fare_class, stops_travelled)
    #
    # ⚠️ 注意：fare functions 需要 schedule_id，但圖裡沒有 schedule_id。
    #    解法（待確認，見附錄 Q5）：
    #    Option A — 直接用 stops × 固定費率估算（fare_class 影響係數），不 import 蔡的函式
    #    Option B — 從 PostgreSQL 找同路線的代表 schedule 再呼叫蔡的函式
    #
    # 暫時用 Option A 實作，確保 fare_class 參數「明顯影響」結果，滿足 C2 評分：
    #    metro: total = 1.0 + stops * 0.5  （fare_class 無差別）
    #    rail standard: total = 2.0 + stops * 1.2
    #    rail first:    total = 2.0 + stops * 2.0  ← fare_class 影響這裡
    pass
```

**commit:** `feat(graph): implement query_cheapest_route with fare_class weighting`

---

## 🔴 SYNC 2 — 推上 remote，等蔡先 merge

```bash
git push origin feature/Chien/graph-queries
# 通知蔡晟郁：函式 6 已 push，等你 ready 一起開 PR
```

**Sync 2 merge 順序（重要）：**
1. 蔡先開 PR merge（因為黃的函式 6 import 蔡的 fare functions，蔡必須先進 main）
2. 黃 `git merge main` 後再 merge

---

## Live Testing 自我驗證 Checklist（對照 STUDENT_GUIDE_LIVE.md Section C）

### C1 — query_shortest_route /8
- [ ] metro 內：`query_shortest_route("MS01", "MS09")` → `found=True`, `total_time_min` 是數字, `path` list 長度 > 1
- [ ] rail 內：`query_shortest_route("NR01", "NR05")` → 同上
- [ ] 不連通的站對：`query_shortest_route("MS01", "NR05")` → `found=False`，不 raise（注意：agent 層已會轉 interchange_path，此函式直接傳跨網 ID 應 gracefully 回傳 not found）

### C2 — query_cheapest_route /7
- [ ] standard：`query_cheapest_route("NR01", "NR05", fare_class="standard")` → `total_fare_usd` 是數字
- [ ] first class：`query_cheapest_route("NR01", "NR05", fare_class="first")` → `total_fare_usd` **不同於** standard 的值

### C3 — query_alternative_routes /7
- [ ] 避開站：回傳 list，每條路徑都不包含 avoid 的 station_id
- [ ] `max_routes=1`：只回傳 1 條
- [ ] 不 raise，無路徑回傳 `[]`

### C4 — query_interchange_path /8
- [ ] 跨網：`query_interchange_path("MS01", "NR05")` → `found=True`，`interchanges` list 非空，stations 包含兩種網路的站
- [ ] 同網輸入：`query_interchange_path("MS01", "MS09")` → 不 raise（回傳 found=False 或嘗試找路）

### C5 — query_delay_ripple /3
- [ ] `query_delay_ripple("MS01", hops=2)` → list，每筆有 `hops_away` 欄位
- [ ] **`query_delay_ripple("MS01", hops=0)` → 只回傳 MS01 本身，`hops_away=0`**（不是空 list，不是鄰站）

### C6 — query_station_connections /2
- [ ] `query_station_connections("MS01")` → list，每筆有 `travel_time_min`，MS01 有 4 個鄰站

---

## 技術陷阱備忘

| 陷阱 | 原因 | 解法 |
|------|------|------|
| `.env` 未設 NEO4J_URI | config.py 預設 7687，docker 對外是 7688 | `.env` 加 `NEO4J_URI=bolt://localhost:7688` |
| `CONNECTS_TO*1..$hops` 語法錯誤 | Cypher 可變長度 `*N..M` 的 M 不接受 `$param` | Python 端 `int()` 轉型後 f-string 組入，或用 APOC maxLevel |
| `hops=0` 回傳空 list | 用 `*1..0` 時沒有匹配 | Python 端特判 `safe_hops == 0`，直接回傳起點 dict |
| `query_cheapest_route` 需要 schedule_id | fare 函式簽名要求，但圖裡沒有 | 見附錄 Q5；暫用 stops × 費率係數估算 |
| APOC 語法 | `apoc.algo.dijkstra(start, end, relType, weightProp)` | relType 是字串 `'CONNECTS_TO'`，weightProp 是字串 `'travel_time_min'` |
| Cypher injection | 不能在 Cypher 裡做字串拼接 | 全部用 `$param`；只有 `hops` 這個整數例外用 f-string（因為已 `int()` 驗證） |
| CONNECTS_TO 是有向邊 | JSON 的鄰接是雙向各列一條，seeding 也建雙向 | 查詢用 `-[:CONNECTS_TO]->` 就夠；但 interchange_path 的 CONNECTS_TO 同樣要注意方向 |

---

## Commit 序列快速參考

| 順序 | Commit message | 對應函式 |
|------|---------------|---------|
| 0 | `feat(graph): replace per-call driver with module-level singleton` | driver 改造 |
| 1 | `feat(graph): implement query_station_connections` | 函式 1 |
| 2 | `feat(graph): implement query_shortest_route with APOC dijkstra` | 函式 2 |
| 3 | `feat(graph): implement query_delay_ripple with hops=0 handling` | 函式 3 |
| 4 | `feat(graph): implement query_alternative_routes with station avoidance` | 函式 4 |
| 5 | `feat(graph): implement query_interchange_path with INTERCHANGE_WITH traversal` | 函式 5 |
| — | **🔴 SYNC 1 push + merge** | — |
| 6 | `feat(graph): implement query_cheapest_route with fare_class weighting` | 函式 6 |
| — | **🔴 SYNC 2 push + merge（蔡先）** | — |

---

## 附錄：待確認的 12 個問題（不影響立即開工，擱置等討論）

詳細背景見 [Chien_graph_開發規劃與待確認問題.md](Chien_graph_開發規劃與待確認問題.md)。

| # | 問題 | 影響 | 現有暫定做法 |
|---|------|------|------------|
| Q1 | 分離標籤 vs 單一 Station | Task 4 /8、Live A | **擱置**：現維持 Station，Task 4 有失分風險 |
| Q2 | METRO_LINK vs CONNECTS_TO | Task 4 | 同 Q1 |
| Q3 | INTERCHANGE_TO 命名/方向 | C4 | 現用 INTERCHANGE_WITH 雙向，可運作 |
| Q4 | 節點屬性集合 | Task 4 | 現有：station_id, name, network, lines[] |
| Q5 | cheapest 票價來源 | C2 | **暫用 stops × 係數估算**，fare_class 差異存在 |
| Q6 | metro fare_class | C2 | metro 忽略 class（只有 rail 有差異） |
| Q7 | transfer_time_min 預設 | C4 | 固定 5 分鐘 |
| Q8 | seed.cypher 是否補齊 | Task 4 靜態 | 可補一份僅供閱讀的 schema 說明 |
| Q9 | constraints/indexes | Code Quality | seeding 可加 IF NOT EXISTS constraint |
| Q10 | driver singleton vs per-call | Code Quality | **已採 singleton**（流程.md + SideNote 都推薦） |
| Q11 | AI_SESSION_CONTEXT 由誰更新 | 契約一致性 | 等決定後請蔡晟郁更新 |
| Q12 | Task 6 加分 | +15 bonus | 核心完成後再評估 |
