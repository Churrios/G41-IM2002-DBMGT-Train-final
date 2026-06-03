# Sync 1 前的 Sonnet Prompts（逐一複製使用）

## 你的執行順序

1. **你自己先跑**（不用 Sonnet）：
   ```bash
   cd "c:\Users\K\Desktop\1142資料庫管理期末專題"
   git checkout main
   git pull origin main
   git checkout -b feature/Chien/graph-queries
   ```

2. 依序把下面 Prompt 0 → 5 貼給 Sonnet，每次確認 commit 成功後再給下一個。

---

## Prompt 0 — Driver Singleton + Helper Functions

```
請閱讀 `databases/graph/queries.py`，然後做以下兩件事：

1. 把現有的 `_driver()` 函式改成**模組級別 singleton**：
   - 建立一個模組層級的 `_DRIVER` 變數（使用 GraphDatabase.driver(...)），讓整個模組共用同一個 driver，而不是每次查詢都重新建立。
   - 提供一個 `_get_driver()` 函式回傳這個 singleton。
   - 注意：singleton driver 不能用 `with _DRIVER as driver:` context manager 語法（那樣退出時會關閉整個 driver）。所有查詢應直接用 `with _get_driver().session() as session:` 取 session。
   - 在 `example_count_nodes()` 中也要改成用新的寫法。

2. 新增一個 `_infer_network(station_id: str) -> str` helper 函式，依照 station_id 的前綴推斷網路類型：
   - `MS` 開頭 → `"metro"`
   - `NR` 開頭 → `"national_rail"`
   - 其他 → `"unknown"`

完成後用以下 commit message 提交：
`feat(graph): replace per-call driver with module-level singleton`

只修改 `databases/graph/queries.py`，不動其他任何檔案。
```

---

## Prompt 1 — query_station_connections

```
請閱讀 `databases/graph/queries.py`，然後實作 `query_station_connections` 函式。

**圖的資料結構：**
- 節點標籤：`Station`，屬性：`station_id`, `name`, `network`, `lines`
- 關係：`CONNECTS_TO`（有向），屬性：`line`, `travel_time_min`, `network`

**函式要求：**
- 找出指定 `station_id` 的所有直接相鄰站（只要一跳的 CONNECTS_TO 鄰居）
- 回傳 `list[dict]`，每筆包含 `station_id`, `name`, `line`, `travel_time_min`, `network`
- 結果按 `travel_time_min` 排序
- 無結果或出錯時回傳 `[]`，**不能 raise exception**
- 使用 `_get_driver().session()` 取得 session（已是 singleton）
- Cypher 參數用 `$param` 語法，不可字串拼接

完成後用以下 commit message 提交：
`feat(graph): implement query_station_connections`

只修改 `databases/graph/queries.py`，不動其他檔案。
```

---

## Prompt 2 — query_shortest_route

```
請閱讀 `databases/graph/queries.py`，然後實作 `query_shortest_route` 函式。

**圖的資料結構：**
- 節點標籤：`Station`，屬性：`station_id`, `name`
- 關係：`CONNECTS_TO`（有向），屬性：`line`, `travel_time_min`

**技術環境：**
- Neo4j 已啟用 APOC plugin（docker-compose.yml 有設定），可使用 `apoc.algo.dijkstra`
- 使用 `_get_driver().session()` 取得 session

**函式要求：**
- 用 Dijkstra 演算法（加權 by `travel_time_min`）找出最快路徑
- `network` 參數可用 `_infer_network()` helper 輔助判斷，但此函式只需處理同網路查詢（跨網路的情況 agent 層會另外處理）
- 找到路徑時回傳：
  ```
  {
    "found": True,
    "origin_id": ...,
    "destination_id": ...,
    "total_time_min": <數字>,
    "path": [{"station_id": ..., "name": ...}, ...],
    "legs": [{"line": ..., "travel_time_min": ...}, ...]
  }
  ```
- 無路徑或出錯時回傳 `found=False` 的同樣結構，**不能 raise exception**
- 所有 Cypher 參數用 `$param` 語法

完成後用以下 commit message 提交：
`feat(graph): implement query_shortest_route with APOC dijkstra`

只修改 `databases/graph/queries.py`，不動其他檔案。
```

---

## Prompt 3 — query_delay_ripple

```
請閱讀 `databases/graph/queries.py`，然後實作 `query_delay_ripple` 函式。

**圖的資料結構：**
- 節點標籤：`Station`，屬性：`station_id`, `name`, `lines`
- 關係：`CONNECTS_TO`（有向）

**函式要求：**
- 找出距離延誤站 `delayed_station_id` 在 `hops` 跳以內的所有站點
- 回傳 `list[dict]`，每筆包含 `station_id`, `name`, `hops_away`, `lines_affected`
- **重要評分規則**：`hops=0` 時只回傳延誤站本身（`hops_away=0`），不是空 list，也不是鄰站
- 結果按 `hops_away` 排序
- 無結果或出錯時回傳 `[]`，**不能 raise exception**
- 使用 `_get_driver().session()` 取得 session

**⚠️ 關鍵技術限制：**
Cypher 的可變長度路徑語法 `[:CONNECTS_TO*1..N]` 中的上限 N **不能直接使用查詢參數 `$hops`**（Cypher 語法不支援）。
你必須在 Python 端先把 `hops` 轉成整數（防止注入），再把這個整數值嵌入 Cypher 字串中。
請自己決定最安全、最正確的做法。

完成後用以下 commit message 提交：
`feat(graph): implement query_delay_ripple with hops=0 handling`

只修改 `databases/graph/queries.py`，不動其他檔案。
```

---

## Prompt 4 — query_alternative_routes

```
請閱讀 `databases/graph/queries.py`，然後實作 `query_alternative_routes` 函式。

**圖的資料結構：**
- 節點標籤：`Station`，屬性：`station_id`, `name`
- 關係：`CONNECTS_TO`（有向），屬性：`travel_time_min`

**函式要求：**
- 找出從 `origin_id` 到 `destination_id`、且**不經過** `avoid_station_id` 的多條路線
- 回傳最多 `max_routes` 條路線，按總時間由短到長排序
- 每條路線格式：`{"route": [{"station_id": ..., "name": ...}, ...], "total_time_min": <數字>}`
- **評分重點**：`max_routes` 參數必須被嚴格遵守（測試會用 `max_routes=1`）
- 無結果或出錯時回傳 `[]`，**不能 raise exception**
- 使用 `_get_driver().session()` 取得 session
- 所有 Cypher 參數用 `$param` 語法

完成後用以下 commit message 提交：
`feat(graph): implement query_alternative_routes with station avoidance`

只修改 `databases/graph/queries.py`，不動其他檔案。
```

---

## Prompt 5 — query_interchange_path

```
請閱讀 `databases/graph/queries.py`，然後實作 `query_interchange_path` 函式。

**圖的資料結構：**
- 節點標籤：`Station`，屬性：`station_id`, `name`, `network`
- 關係一：`CONNECTS_TO`（有向），屬性：`travel_time_min`, `line`
- 關係二：`INTERCHANGE_WITH`（有向，但捷運↔國鐵雙向各一條），無屬性，連接換乘站

**函式要求：**
- 找出跨越捷運與國鐵邊界的路線（必須經過至少一條 `INTERCHANGE_WITH` 邊）
- 回傳格式：
  ```
  {
    "found": True,
    "stations": [{"station_id": ..., "name": ..., "interchange": True/False}, ...],
    "interchanges": [{"from": ..., "to": ..., "transfer_time_min": 5}, ...],
    "total_time_min": <數字>
  }
  ```
  - 換乘點的 station 要有 `"interchange": True`
  - `transfer_time_min` 固定用 **5 分鐘**（來源資料沒有這個欄位）
  - `total_time_min` 要把換乘時間也加進去
- 同網路輸入（如 MS→MS）或無路徑時：回傳 `found=False` 的同樣結構，**不能 raise exception**
- 使用 `_get_driver().session()` 取得 session
- 所有 Cypher 參數用 `$param` 語法

完成後用以下 commit message 提交：
`feat(graph): implement query_interchange_path with INTERCHANGE_WITH traversal`

只修改 `databases/graph/queries.py`，不動其他檔案。
```

---

## Sync 1 準備完成後的指令（你自己跑）

```bash
git push -u origin feature/Chien/graph-queries
# 通知蔡晟郁：函式 1–5 已 push，等你和蔣 ready 一起開 PR
```

---

## 注意事項

- 每個 prompt 給 Sonnet 前，先確認上一個 commit 已成功（`git log --oneline -3`）
- Sonnet 如果沒有刪掉 `raise NotImplementedError`，叫它重做
- Prompt 3（delay_ripple）最容易出錯——確認 Sonnet 有正確處理 `$hops` 不能當參數這件事，以及 `hops=0` 的特殊情況
- Prompt 5（interchange_path）確認 Sonnet 有標記換乘點且把換乘時間加進總時間
