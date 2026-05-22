# Side Note 3 — 正式環境中的圖形資料庫最佳實務

> **免責聲明**
> 本文件是在多個 AI 工具協助下共同撰寫。雖然已盡力確保內容正確，但仍可能存在非預期錯誤。如果你發現任何錯誤，請[在 GitHub 提交 issue](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/issues)。

---

> **這是寫給誰的？**
> 這份 note 是給已經在本專案中使用過 Neo4j 的學生。
> 你已經寫過 Cypher queries 來尋找火車路線並建立車站連線模型。現在讓我們看看正式環境系統如何正確管理 graph databases。

---

## 教學程式碼做了什麼？

TransitFlow 專案使用 **Neo4j** 來建模實體鐵路網路。Stations 是 **nodes**，它們之間的 rail connections 是 **relationships**。Cypher queries 會尋找 shortest path、避開 closed stations，並讓 delay information 在 network 中 ripple。

教學程式碼會像這樣為每個 query 建立新的 driver：

```python
def _driver():
    """Return a Neo4j driver. Caller is responsible for closing."""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict:
    with _driver() as driver:           # 這裡建立 new driver
        with driver.session() as session:
            result = session.run(cypher, ...)
    # driver 在這裡關閉，connection pool 下一次 call 又會被拆掉重建
```

這在 single-user teaching environment 中可以運作。但在 production 中，它有幾個問題，這份 note 會解釋並修正。

---

## 1. Driver Management：整個 App 共用一個 Driver

### 什麼是 Neo4j driver？

Neo4j Python driver 不只是一個 connection，它是一個 **connection pool manager**。當你用 `GraphDatabase.driver(...)` 建立 driver 時，它會：
- 開啟一組到 Neo4j 的 TCP connections
- 管理 clustered Neo4j deployments 的 routing
- 處理 authentication 與 TLS

### 教學程式碼的問題

每個 query function 都呼叫 `_driver()`，這會建立新 pool，然後立刻銷毀它。這和每次 query 都開一個新的 `psycopg2.connect()` 是同樣問題：每次 call 都有昂貴的 setup cost。

### 正式環境解法：singleton driver

在 application start 時**只建立一次** driver，並讓每個 query 重複使用它：

```python
from neo4j import GraphDatabase
from skeleton.config import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# Module load 時建立一次，所有 queries 共用
_DRIVER = GraphDatabase.driver(
    NEO4J_URI,
    auth=(NEO4J_USER, NEO4J_PASSWORD),
    max_connection_pool_size=50,     # 要保持多少 connections open
)

def query_shortest_route(origin_id: str, destination_id: str, network: str = "auto") -> dict:
    with _DRIVER.session() as session:    # 從 pool 借用，不建立 new driver
        result = session.run(cypher, ...)
        return dict(result.single()) if result else {"found": False}

# 在 web framework 中，app shutdown 時關閉 driver：
# _DRIVER.close()
```

Driver 內建 pool，代表你不需要像 PgBouncer 那樣的外部工具。Neo4j 的 Python driver 原生處理 connection reuse。

### 延伸閱讀
- [Neo4j Python Driver — Connection and authentication（官方文件）](https://neo4j.com/docs/python-manual/current/)
- [Neo4j Python Driver — Advanced connection options](https://neo4j.com/docs/python-manual/current/connect-advanced/)

---

## 2. Explicit Transactions

### 教學程式碼怎麼做

每個 query 都直接使用 `session.run()`，這會以 **auto-commit mode** 執行。每個 statement 都是自己的 transaction，會獨立完整成功或失敗。

對 read queries 來說，這可以接受。對 write operations，例如插入 new booking 或更新 station status，auto-commit 沒有辦法在多個相關 changes 中某一步失敗時 rollback 全部變更。

### 正式環境解法：explicit transactions

Neo4j driver 有三種 transaction modes：

#### Auto-commit（教學程式碼，read 沒問題）
```python
session.run(cypher, params)
```

#### Managed transactions（writes 推薦）
```python
def create_station_tx(tx, station_id, name, lines):
    tx.run(
        "MERGE (s:MetroStation {station_id: $station_id}) SET s.name = $name, s.lines = $lines",
        station_id=station_id, name=name, lines=lines,
    )

with _DRIVER.session() as session:
    session.execute_write(create_station_tx, "MS21", "New Quarter", ["M2"])
    # transient errors 會自動 retry，exceptions 會 rollback
```

#### Explicit transactions（用於複雜 multi-step operations）
```python
with _DRIVER.session() as session:
    with session.begin_transaction() as tx:
        tx.run("MATCH (s:NationalRailStation {station_id: $sid}) SET s.active = false", sid="NR03")
        tx.run("MATCH (:NationalRailStation {station_id: $sid})-[r:RAIL_LINK]-() SET r.active = false", sid="NR03")
        tx.commit()   # 兩個 changes 一起 commit；若發生 error，兩者都不會套用
```

### 延伸閱讀
- [Neo4j Python Driver — Transactions（官方文件）](https://neo4j.com/docs/python-manual/current/transactions/)

---

## 3. Indexes and Constraints

### 問題

教學程式碼會執行像這樣的 queries：

```cypher
MATCH (s:Station {code: $code}) ...
```

如果 `Station.code` 上沒有 index，Neo4j 必須掃描**每一個 Station node**，才能找到 code 符合的那個。20 個 stations 時很快；20,000 個時就慢到無法接受。

### 正式環境解法：定義 indexes 與 constraints

在 production 中，你會在 schema setup scripts 中定義 indexes 與 constraints，而不是在 query code 裡定義。

#### Unique constraint（也會建立 index）
```cypher
// 設定 database 時執行一次
CREATE CONSTRAINT metro_station_id_unique
FOR (s:MetroStation)
REQUIRE s.station_id IS UNIQUE;

CREATE CONSTRAINT nr_station_id_unique
FOR (s:NationalRailStation)
REQUIRE s.station_id IS UNIQUE;
```

之後，`MATCH (s:MetroStation {station_id: "MS01"})` 會使用 index，而且不管 stations 有多少，都是 O(1) time。

#### Range index（用於 non-unique properties）
```cypher
CREATE INDEX metro_station_name_index
FOR (s:MetroStation)
ON (s.name);
```

#### Relationship index
```cypher
CREATE INDEX metro_link_line_index
FOR ()-[r:METRO_LINK]-()
ON (r.line);
```

### 延伸閱讀
- [Neo4j Cypher Manual — Indexes](https://neo4j.com/docs/cypher-manual/current/indexes/)
- [Neo4j Cypher Manual — Constraints](https://neo4j.com/docs/cypher-manual/current/constraints/)

---

## 4. Graph Data Modelling

### 什麼是 graph data modelling？

當你設計 relational database 時，你會思考 tables 與 foreign keys。當你設計 graph database 時，你會思考 **nodes**、**relationships** 與 **properties**。

Graph modelling 中最重要的決策是：**什麼應該是 node，什麼應該是 relationship？**

#### TransitFlow model（簡化版）
```text
(:MetroStation {station_id, name, lines[]})
    -[:METRO_LINK {line, travel_time_min, base_fare_usd, per_stop_rate_usd}]->
(:MetroStation {station_id, name, lines[]})

(:NationalRailStation {station_id, name, lines[]})
    -[:RAIL_LINK {line, travel_time_min, standard_fare_usd, first_fare_usd}]->
(:NationalRailStation {station_id, name, lines[]})

(:MetroStation)-[:INTERCHANGE_TO {transfer_time_min}]->(:NationalRailStation)
```

這是一個好的 model，因為：
- Stations 是 entities（它們有自己的 identity 與 properties）
- Transit links 是 relationships（它們只存在於兩個 stations *之間*）
- Fare data 儲存在 edges 上，可在不 join PostgreSQL 的情況下執行 cost-weighted Dijkstra
- Route-finding algorithms 會自然地 traverse relationships

#### 常見 modeling mistake：把 relationships 做成 nodes

初學者可能會這樣 modeling interchange：

```text
(:MetroStation)-[:HAS_INTERCHANGE]->(:Interchange)-[:CONNECTS_TO]->(:NationalRailStation)
```

但如果 interchange 只是連接兩個 stations，直接 relationship 會更乾淨：

```text
(:MetroStation)-[:INTERCHANGE_TO {transfer_time_min: 5}]->(:NationalRailStation)
```

經驗法則：**如果某個東西精確連接兩個東西並且有 properties，它是 relationship，不是 node。**

### 延伸閱讀
- [Neo4j — What is a graph database?（Getting Started）](https://neo4j.com/docs/getting-started/graph-database/)
- [Neo4j — Graph data modelling guide](https://neo4j.com/docs/getting-started/data-modeling/)

---

## 5. Graph Algorithms（GDS Plugin）

### 教學程式碼使用什麼

教學程式碼使用 Cypher 內建的 `shortestPath()`，它會尋找 hop 數最少的 path。對簡單 route finding 來說，這是正確的。

```cypher
MATCH path = shortestPath((start)-[:RAIL_LINK*]-(end))
```

### 正式環境會加入什麼：Graph Data Science library

Neo4j 的 **Graph Data Science（GDS）** plugin 提供一組進階 graph algorithms，遠比單靠 Cypher expressions 能計算的內容更強大：

#### Weighted shortest path（Dijkstra's algorithm）
內建的 `shortestPath()` 會計算 hops。Dijkstra 會尋找讓某個 numeric weight 最小的 path，例如 travel time 或 fare。TransitFlow 專案為此使用 **APOC** plugin（`apoc.algo.dijkstra`），它必須在 `docker-compose.yml` 中啟用。GDS 提供更 feature-complete 的替代方案：

```cypher
MATCH (start:MetroStation {station_id: 'MS01'}),
      (end:MetroStation   {station_id: 'MS14'})
CALL gds.shortestPath.dijkstra.stream('metro-network', {
    sourceNode: start,
    targetNode: end,
    relationshipWeightProperty: 'travel_time_min'
})
YIELD path
RETURN path
```

#### PageRank — 找出最重要的 stations
辨識 network 中最 central 的 stations（高流量 interchange hubs）：

```cypher
CALL gds.pageRank.stream('metro-network')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).name AS station, score
ORDER BY score DESC
LIMIT 10
```

#### Community detection — 找出自然 clusters
把彼此之間連線比與 network 其他部分連線更密集的 stations 分組。這對辨識 line clusters 或 service zones 很有用：

```cypher
CALL gds.louvain.stream('metro-network')
YIELD nodeId, communityId
RETURN gds.util.asNode(nodeId).name AS station, communityId
ORDER BY communityId
```

這些 algorithms 若用 SQL 重現會**極度複雜**。它們是針對 network-type problems 選擇 graph database 的核心理由。

### 延伸閱讀
- [Neo4j Graph Data Science library — official documentation](https://neo4j.com/docs/graph-data-science/current/)

---

## 6. Cypher Query Organisation

### 和 SQL 相同的問題

就像 relational `queries.py` 會把 SQL inline 存放一樣，教學 graph code 也會把 Cypher 以 strings inline 儲存。到了 scale，同樣的替代方案也適用：

- **Centralise queries** 到專用 module 中（`databases/graph/queries.py` 已經做得不錯）
- **Repository pattern** — 用 class 包裝 query functions，讓 tests 可以換成 fake
- **Parameterise everything** — 教學程式碼已經正確做到這點（使用 `$param` syntax，從不 string formatting）

教學程式碼已經避免了最大的 Cypher security risk：**Cypher injection**。永遠不要把 values 直接 format 進 Cypher string：

```python
# DANGEROUS — 絕對不要這樣做
cypher = f"MATCH (s:MetroStation {{station_id: '{user_input}'}}) RETURN s"

# SAFE — 一律使用 parameters
cypher = "MATCH (s:MetroStation {station_id: $station_id}) RETURN s"
session.run(cypher, station_id=user_input)
```

### 延伸閱讀
- [Neo4j Cypher Manual — Introduction](https://neo4j.com/docs/cypher-manual/current/)

---

## 7. 何時使用 Graph Database，何時使用 Relational Database

這是 database design 中最重要的問題之一。以下情境適合使用 graph database：

| Scenario | 為什麼 graph 勝出 |
|---|---|
| **Route finding**（shortest path、avoid a node） | Graph traversal 是原生能力；SQL 需要 recursive CTEs |
| **Ripple / impact analysis**（一個 station 的 delay 影響其他 stations） | N-hop traversal 在 Cypher 中只要一行；在 SQL 中很慢 |
| **Recommendations**（搭過這條 route 的人也搭過...） | 跨數百萬 nodes 的 relationship patterns 很快 |
| **Fraud detection**（shared accounts、common addresses） | Detecting connected subgraphs 是 graph theory 的核心 |
| **Knowledge graphs**（entities and their relationships） | Flexible schema 很自然合適 |

Relational database 仍然適合：
- 具有清楚 schema 的 tabular、structured data（bookings、pricing、users）
- Aggregation-heavy queries（SUM、GROUP BY、window functions）
- 一次修改多列的 transactions

**TransitFlow 同時使用兩者是有原因的**：route network 是 graph problem；booking history 是 relational problem。針對每項問題使用正確工具，正是真實正式環境系統會做的事。

---

## 8. Neo4j 的替代方案

Neo4j 是最廣泛使用的 graph database，但不是唯一選項：

| Database | Key difference |
|---|---|
| **Amazon Neptune** | AWS 上的 fully managed；同時支援 property graphs 與 RDF（knowledge graphs） |
| **ArangoDB** | Multi-model：graph + document + key-value 在同一個 engine 中 |
| **TigerGraph** | 為 very large-scale graphs（數十億 edges）打造；用於 fraud detection |
| **Apache AGE** | PostgreSQL 的 graph extension（像 pgvector，但用於 graphs） |

對大多數不需要 AWS lock-in 的 applications，Neo4j Community Edition（free and open-source）是標準起點。

### 延伸閱讀
- [Amazon Neptune — official page](https://aws.amazon.com/neptune/)
- [ArangoDB — official site](https://arango.ai/)

---

## Summary

| Topic | Teaching Code | Production Approach |
|---|---|---|
| **Driver lifecycle** | 每個 query 建立 new driver | Singleton driver，整個 app 共用 |
| **Transactions** | 透過 `session.run()` auto-commit | Writes 使用 managed 或 explicit transactions |
| **Indexes** | 未定義 | 在 setup scripts 中使用 `CREATE CONSTRAINT` / `CREATE INDEX` |
| **Path algorithms** | 內建 `shortestPath()`（hop count） | GDS Dijkstra（weighted）、PageRank、community detection |
| **Cypher location** | Functions 中的 inline strings | Centralised module + repository pattern |
| **Security** | Parameterised（正確） | Parameterised，不要把 user input string-format 進 Cypher |

---

## Recommended Starting Points

| Resource | 你會學到什麼 |
|---|---|
| [Neo4j Python Driver Manual](https://neo4j.com/docs/python-manual/current/) | Python 中的 driver setup、sessions 與 transactions |
| [Neo4j Cypher Manual](https://neo4j.com/docs/cypher-manual/current/) | 完整 Cypher language reference |
| [Neo4j — What is a graph database?](https://neo4j.com/docs/getting-started/graph-database/) | Concepts：nodes、relationships、properties |
| [Neo4j — Graph data modelling](https://neo4j.com/docs/getting-started/data-modeling/) | 如何設計 graph schema |
| [Neo4j GDS Library](https://neo4j.com/docs/graph-data-science/current/) | PageRank、Dijkstra、community detection 等 |
| [Neo4j Cypher — Indexes and Constraints](https://neo4j.com/docs/cypher-manual/current/indexes/) | 如何讓 queries 變快 |
