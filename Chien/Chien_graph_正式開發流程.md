# TransitFlow — Graph DB 正式開發流程（Chien 專用）

> 負責範圍：`skeleton/seed_neo4j.py`、`databases/graph/seed.cypher`、`databases/graph/queries.py`
> 對應分數：Task 3 /10（共享）、Task 4 /8、Task 5 /10、Live Section C /35 → **合計 /63**
> 文件狀態：**✅ 決策鎖定（2026-06-04）**

---

## 決策摘要（Q1–Q12 已定案）

| # | 問題 | 決定 |
|---|------|------|
| Q1 | Schema 標籤模型 | ✅ **選 A** — 分離 `MetroStation`/`NationalRailStation`，對齊評分標準 |
| Q2 | 關係命名 | ✅ `METRO_LINK` / `RAIL_LINK`（與 Q1 綁定） |
| Q3 | INTERCHANGE_TO 方向 | ✅ 命名 `INTERCHANGE_TO`，seeding 建雙向兩條邊，查詢用無向 `-[:INTERCHANGE_TO]-` |
| Q4 | 節點/邊屬性 | ✅ 節點存 `station_id, name, lines[]`（陣列） + `is_interchange_national_rail`；邊存 `travel_time_min` + 票價屬性（Q5） |
| Q5 | cheapest 票價來源 | ✅ **選 A** — seeding 寫入邊屬性：metro `fare_usd = base_fare_usd + per_stop_rate_usd × travel_time`；rail 存 `fare_standard_usd` / `fare_first_usd` 兩欄 |
| Q6 | metro fare_class | ✅ Metro 一律用單一票價，忽略 `fare_class` |
| Q7 | transfer_time_min 預設值 | ✅ 固定 **5 分鐘** |
| Q8 | seed.cypher 雙保險 | ✅ 補一份可讀 schema Cypher，讓評分 TA 靜態閱讀時直接看到 METRO_LINK/RAIL_LINK/INTERCHANGE_TO |
| Q9 | constraints/indexes | ✅ 建 unique constraints（`IF NOT EXISTS`，冪等） |
| Q10 | driver 模式 | ✅ 維持 **per-call `_driver()`**，加一行 comment 說明 production 會改 singleton |
| Q11 | AI_SESSION_CONTEXT 更新 | ✅ Chien 寫新 schema 段落文字，轉給蔡晟郁貼進去 |
| Q12 | Task 6 | ✅ 核心 /63 優先，Task 6 留後評估 |

---

## 現況確認（開始前必讀）

| 項目 | 狀態 |
|------|------|
| `skeleton/seed_neo4j.py` | ⚠️ 已有舊版（commit `89d214b`），**需重寫**為分離標籤模型 |
| `databases/graph/seed.cypher` | ⚠️ 空檔（標示 deprecated），**需補齊** schema Cypher |
| `databases/graph/queries.py` | ❌ 全部 6 個函式仍是 `raise NotImplementedError` |
| APOC plugin | ✅ docker-compose.yml 已啟用（Dijkstra 可用） |
| GDS plugin | ❌ 未安裝（不能用 gds.* 語法） |

---

## Phase 0 — 每次工作前的環境確認

```bash
# 1. 確認目前 branch
git branch

# 2. 確認 main 是否有其他人的新 commit
git fetch origin
git log HEAD..origin/main --oneline
# 若有新 commit → git merge origin/main

# 3. 確認 Docker 正常
docker compose ps
# neo4j 應顯示 healthy

# 4. 確認 .env 有設正確的 bolt 連接埠
# docker-compose.yml 對主機映射是 7688:7687
# config.py 預設是 bolt://localhost:7687 → 從主機跑腳本時會連不上！
# .env 必須有：NEO4J_URI=bolt://localhost:7688
```

---

## Phase 1 — 開分支

```bash
git checkout main
git pull origin main
git checkout -b feature/Chien/neo4j-seeding
```

---

## Phase 2 — Seeding（Task 3 /10 共享、Task 4 /8）

### Step 1：重寫 `skeleton/seed_neo4j.py`

完整邏輯：

1. **建 unique constraints（冪等）**
   ```cypher
   CREATE CONSTRAINT IF NOT EXISTS FOR (s:MetroStation) REQUIRE s.station_id IS UNIQUE
   CREATE CONSTRAINT IF NOT EXISTS FOR (s:NationalRailStation) REQUIRE s.station_id IS UNIQUE
   ```

2. **MERGE MetroStation 節點**（資料來源：`train-mock-data/metro_stations.json`）
   - 屬性：`station_id, name, lines[]（陣列）, is_interchange_national_rail`

3. **MERGE NationalRailStation 節點**（資料來源：`train-mock-data/national_rail_stations.json`）
   - 屬性：`station_id, name, lines[]（陣列）, metro_interchange_id`

4. **MERGE METRO_LINK 邊**（MetroStation ↔ MetroStation）
   - 屬性：`travel_time_min, line`
   - 票價屬性（Q5）：`fare_usd = 1.0 + 0.5 × travel_time_min`（metro 無 fare_class 之分）

5. **MERGE RAIL_LINK 邊**（NationalRailStation ↔ NationalRailStation）
   - 屬性：`travel_time_min, line`
   - 票價屬性（Q5）：
     - `fare_standard_usd = 2.0 + 1.2 × travel_time_min`
     - `fare_first_usd    = 2.0 + 2.0 × travel_time_min`

6. **MERGE INTERCHANGE_TO 邊（雙向兩條）**（MetroStation ↔ NationalRailStation）
   - 屬性：`transfer_time_min = 5`（固定值，Q7）
   - 方向：metro → rail **and** rail → metro 各建一條

7. **結尾印出節點/邊統計**做驗證

**Driver 寫法（per-call，加 comment 說明 production 改法）：**
```python
def _driver():
    # per-call for simplicity; production should use a module-level singleton
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "transitflow"))
    return GraphDatabase.driver(uri, auth=auth)
```

**commit:** `feat(graph): rewrite seed_neo4j with MetroStation/NationalRailStation and MERGE`

---

### Step 2：補 `databases/graph/seed.cypher`（雙保險，Q8）

放一份可讀的 schema + constraint Cypher，讓評分 TA 靜態閱讀時立即看到完整結構：

```cypher
// ── Constraints ──────────────────────────────────────────────────────
CREATE CONSTRAINT IF NOT EXISTS FOR (s:MetroStation)         REQUIRE s.station_id IS UNIQUE;
CREATE CONSTRAINT IF NOT EXISTS FOR (s:NationalRailStation)  REQUIRE s.station_id IS UNIQUE;

// ── MetroStation nodes ────────────────────────────────────────────────
MERGE (:MetroStation  {station_id: 'MS01', name: '...', lines: ['M1'], is_interchange_national_rail: false});
// ... (示意，完整資料由 seed_neo4j.py 動態載入)

// ── NationalRailStation nodes ─────────────────────────────────────────
MERGE (:NationalRailStation {station_id: 'NR01', name: '...', lines: ['NR1'], metro_interchange_id: 'MS01'});

// ── METRO_LINK ────────────────────────────────────────────────────────
MATCH (a:MetroStation {station_id:'MS01'}), (b:MetroStation {station_id:'MS02'})
MERGE (a)-[:METRO_LINK {travel_time_min: 3, line: 'M1', fare_usd: 2.5}]->(b);

// ── RAIL_LINK ─────────────────────────────────────────────────────────
MATCH (a:NationalRailStation {station_id:'NR01'}), (b:NationalRailStation {station_id:'NR02'})
MERGE (a)-[:RAIL_LINK {travel_time_min: 12, line: 'NR1', fare_standard_usd: 16.4, fare_first_usd: 26.0}]->(b);

// ── INTERCHANGE_TO (雙向) ─────────────────────────────────────────────
MATCH (m:MetroStation {station_id:'MS01'}), (r:NationalRailStation {station_id:'NR01'})
MERGE (m)-[:INTERCHANGE_TO {transfer_time_min: 5}]->(r)
MERGE (r)-[:INTERCHANGE_TO {transfer_time_min: 5}]->(m);
```

**commit:** `feat(graph): add seed.cypher schema mirror for static grading`

---

### Step 3：實跑驗證

```bash
# 重置 DB（需三人協調後執行）
# docker compose down -v && docker compose up -d

python skeleton/seed_neo4j.py
```

在 Neo4j Browser（http://localhost:7475）驗證：
```cypher
MATCH (n:MetroStation) RETURN count(n);          // 期望 20
MATCH (n:NationalRailStation) RETURN count(n);   // 期望 10
MATCH ()-[r:METRO_LINK]->() RETURN count(r);     // 期望 ~40（雙向各一條）
MATCH ()-[r:RAIL_LINK]->() RETURN count(r);      // 期望 ~18
MATCH ()-[r:INTERCHANGE_TO]->() RETURN count(r); // 期望 ~6（換乘站數 × 2）
```

---

## Phase 3 — Cypher Query Functions（Task 5 /10、Live C /35）

開新分支（或延用 seeding 分支完成後開）：
```bash
git checkout -b feature/Chien/cypher-queries
```

**Driver 寫法同上（per-call，加 comment）**，`databases/graph/queries.py` 開頭：
```python
import os
from neo4j import GraphDatabase

def _driver():
    # per-call for simplicity; production should use a module-level singleton
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7688")
    auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "transitflow"))
    return GraphDatabase.driver(uri, auth=auth)
```

---

### 函式 1：`query_station_connections` — 直接相鄰站點（最簡單，先暖身）

**評分：** Live C6 /2

**回傳格式：**
```python
[
    {"station_id": "MS05", "name": "Westfield", "line": "M1", "travel_time_min": 3},
    ...
]
# 空結果 → []，絕不 raise
```

**Cypher：**
```cypher
MATCH (s {station_id: $station_id})-[r:METRO_LINK|RAIL_LINK]-(n)
RETURN n.station_id AS station_id, n.name AS name,
       r.line AS line, r.travel_time_min AS travel_time_min
ORDER BY r.travel_time_min
```

**commit:** `feat(graph): implement query_station_connections`

---

### 函式 2：`query_shortest_route` — 最快路線（Dijkstra by travel_time）

**評分：** Live C1 /8

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

**Cypher（APOC dijkstra）：**
```cypher
MATCH (o {station_id: $origin_id}), (d {station_id: $dest_id})
CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', 'travel_time_min')
YIELD path, weight
RETURN
    [node IN nodes(path) | {station_id: node.station_id, name: node.name}] AS stations,
    [rel  IN relationships(path) | {line: rel.line, travel_time_min: rel.travel_time_min}] AS legs,
    weight AS total_time_min
```

**commit:** `feat(graph): implement query_shortest_route with APOC dijkstra`

---

### 函式 3：`query_cheapest_route` — 最低票價路線

**評分：** Live C2 /7

**回傳格式：**
```python
{
    "found": True,
    "total_fare_usd": 12.50,
    "fare_class": "standard",
    "path": [{"station_id": "NR01", "name": "Central Station"}, ...],
    "legs": [{"line": "NR1", "travel_time_min": 12, "fare_usd": 16.4}, ...]
}
# 無路徑 → {"found": False, "total_fare_usd": None, "fare_class": fare_class}
```

**Cypher（APOC dijkstra，rail standard 用 fare_standard_usd，first 用 fare_first_usd）：**
```python
# Python 端決定 weight property
weight_prop = "fare_usd"  # metro（fare_class 無差別）
if network == "national_rail":
    weight_prop = "fare_standard_usd" if fare_class == "standard" else "fare_first_usd"

cypher = f"""
MATCH (o {{station_id: $origin_id}}), (d {{station_id: $dest_id}})
CALL apoc.algo.dijkstra(o, d, 'METRO_LINK|RAIL_LINK', '{weight_prop}')
YIELD path, weight
RETURN
    [node IN nodes(path) | {{station_id: node.station_id, name: node.name}}] AS stations,
    [rel  IN relationships(path) | {{line: rel.line, travel_time_min: rel.travel_time_min,
     fare_usd: rel.{weight_prop}}}] AS legs,
    weight AS total_fare_usd
"""
```

> `weight_prop` 已在 Python 端驗證為固定字串之一，不含使用者輸入，f-string 安全。

**commit:** `feat(graph): implement query_cheapest_route with fare_class weighting`

---

### 函式 4：`query_delay_ripple` — 延誤波紋分析

**評分：** Live C5 /3

**回傳格式：**
```python
[
    {"station_id": "MS01", "name": "Central Square", "hops_away": 0, "lines_affected": ["M1","M2"]},
    {"station_id": "MS02", "name": "Riverside",      "hops_away": 1, "lines_affected": ["M1"]},
]
# hops=0 只回傳延誤站本身（hops_away=0）；空結果 → []
```

> ⚠️ **Cypher 陷阱：** `*1..$hops` 的上限不接受 `$param`，需 Python 端 `int()` 後 f-string 組入。

```python
safe_hops = max(0, int(hops))  # int() 轉型防注入

start = session.run(
    "MATCH (s {station_id: $sid}) RETURN s.station_id AS station_id, s.name AS name, s.lines AS lines",
    sid=delayed_station_id
).single()
if not start:
    return []

start_dict = {"station_id": start["station_id"], "name": start["name"],
              "hops_away": 0, "lines_affected": list(start["lines"] or [])}
if safe_hops == 0:
    return [start_dict]

cypher = f"""
MATCH (s {{station_id: $station_id}})-[:METRO_LINK|RAIL_LINK*1..{safe_hops}]-(affected)
RETURN DISTINCT
    affected.station_id AS station_id,
    affected.name AS name,
    min(length(shortestPath((s)-[:METRO_LINK|RAIL_LINK*]-(affected)))) AS hops_away,
    affected.lines AS lines_affected
ORDER BY hops_away
"""
result = session.run(cypher, station_id=delayed_station_id)
return [start_dict] + [dict(r) for r in result]
```

**commit:** `feat(graph): implement query_delay_ripple with hops=0 handling`

---

### 函式 5：`query_alternative_routes` — 備選路線

**評分：** Live C3 /7

**回傳格式：**
```python
[
    {"route": [{"station_id": "NR01", "name": "..."}, ...], "total_time_min": 50},
    {"route": [...], "total_time_min": 65},
]
# 空結果 → []；路徑不得包含 avoid_station_id
```

**Cypher：**
```cypher
MATCH p = (o {station_id: $origin_id})-[:METRO_LINK|RAIL_LINK*1..10]-(d {station_id: $dest_id})
WHERE NONE(n IN nodes(p) WHERE n.station_id = $avoid_station_id)
RETURN [n IN nodes(p) | {station_id: n.station_id, name: n.name}] AS route,
       reduce(t=0, r IN relationships(p) | t + r.travel_time_min) AS total_time_min
ORDER BY total_time_min
LIMIT $max_routes
```

**commit:** `feat(graph): implement query_alternative_routes with station avoidance`

---

### 函式 6：`query_interchange_path` — 跨網換乘路線

**評分：** Live C4 /8

**回傳格式：**
```python
{
    "found": True,
    "path": [
        {"station_id": "MS01", "name": "Central Square"},
        {"station_id": "NR01", "name": "Central Station", "interchange": True},
        ...
    ],
    "interchange_points": [{"from": "MS01", "to": "NR01", "transfer_time_min": 5}],
    "total_time_min": 25
}
# 無路徑 → {"found": False, "path": [], "interchange_points": [], "total_time_min": None}
```

**Cypher：**
```cypher
MATCH p = (o {station_id: $origin_id})-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-(d {station_id: $dest_id})
WHERE any(r IN relationships(p) WHERE type(r) = 'INTERCHANGE_TO')
RETURN nodes(p) AS path_nodes, relationships(p) AS path_rels
ORDER BY length(p)
LIMIT 1
```

Python 端：
- 標記換乘點（遇到 `INTERCHANGE_TO` 邊的兩端 node 設 `"interchange": True`）
- `total_time_min` = Σ travel_time_min（`*_LINK` 邊）+ 換乘次數 × 5

**commit:** `feat(graph): implement query_interchange_path with INTERCHANGE_TO traversal`

---

## Live Testing 自我驗證 Checklist（對照 STUDENT_GUIDE_LIVE.md Section C）

### C1 — query_shortest_route /8
- [ ] metro 內：`query_shortest_route("MS01", "MS09")` → `found=True`, `total_time_min` 有值, `path` 長度 > 1
- [ ] rail 內：`query_shortest_route("NR01", "NR05")` → 同上
- [ ] 不連通（跨網直傳）：`query_shortest_route("MS01", "NR05")` → `found=False`，不 raise

### C2 — query_cheapest_route /7
- [ ] standard：`query_cheapest_route("NR01", "NR05", fare_class="standard")` → `total_fare_usd` 有值
- [ ] first class：`query_cheapest_route("NR01", "NR05", fare_class="first")` → 值**不同於** standard

### C3 — query_alternative_routes /7
- [ ] 避開站：每條路徑都不含 avoid_station_id
- [ ] `max_routes=1`：只回傳 1 條
- [ ] 無路徑：回傳 `[]`，不 raise

### C4 — query_interchange_path /8
- [ ] 跨網：`query_interchange_path("MS01", "NR05")` → `found=True`，`interchange_points` 非空
- [ ] 同網輸入：不 raise（回傳 `found=False` 或嘗試找路）

### C5 — query_delay_ripple /3
- [ ] `query_delay_ripple("MS01", hops=2)` → list，每筆有 `hops_away`
- [ ] **`query_delay_ripple("MS01", hops=0)` → 只回傳 MS01 本身，`hops_away=0`**（不是空 list）

### C6 — query_station_connections /2
- [ ] `query_station_connections("MS01")` → list，每筆有 `travel_time_min`

---

## 技術陷阱備忘

| 陷阱 | 原因 | 解法 |
|------|------|------|
| `.env` 未設 NEO4J_URI | config.py 預設 7687，docker 對外是 7688 | `.env` 加 `NEO4J_URI=bolt://localhost:7688` |
| `*1..$hops` 語法錯誤 | Cypher 可變長度上限不接受 `$param` | Python 端 `int()` 後 f-string 組入 |
| `hops=0` 回傳空 list | `*1..0` 無匹配 | Python 端特判 `safe_hops == 0` 直接回傳起點 |
| APOC dijkstra relType 格式 | `apoc.algo.dijkstra` 第三參數是字串 | `'METRO_LINK\|RAIL_LINK'`（pipe 分隔字串） |
| fare_class f-string 注入 | `weight_prop` 含使用者輸入？ | `weight_prop` 只從固定 dict 取值，不含使用者原始字串 |
| INTERCHANGE_TO 方向 | seeding 建雙向，查詢可用無向 | `-[:INTERCHANGE_TO]-`（無箭頭） |

---

## Commit 序列快速參考

| 順序 | Commit message | 內容 |
|------|---------------|------|
| 1 | `feat(graph): rewrite seed_neo4j with MetroStation/NationalRailStation and MERGE` | seed_neo4j.py 重寫 |
| 2 | `feat(graph): add seed.cypher schema mirror for static grading` | seed.cypher 補齊 |
| 3 | `feat(graph): implement query_station_connections` | 函式 1 |
| 4 | `feat(graph): implement query_shortest_route with APOC dijkstra` | 函式 2 |
| 5 | `feat(graph): implement query_cheapest_route with fare_class weighting` | 函式 3 |
| 6 | `feat(graph): implement query_delay_ripple with hops=0 handling` | 函式 4 |
| 7 | `feat(graph): implement query_alternative_routes with station avoidance` | 函式 5 |
| 8 | `feat(graph): implement query_interchange_path with INTERCHANGE_TO traversal` | 函式 6 |
