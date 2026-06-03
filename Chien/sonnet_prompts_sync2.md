# Sync 2 — Sonnet Prompt（逐一複製使用）

## 你的執行順序

1. **main 已 merge 完畢**（上一步已完成，不用再跑）
2. 把下面 Prompt 6 貼給 Sonnet，確認 commit 成功後 push。

---

## Prompt 6 — query_cheapest_route

```
請閱讀 `databases/graph/queries.py`，然後實作 `query_cheapest_route` 函式（目前是 raise NotImplementedError）。

**圖的資料結構：**
- 節點標籤：`Station`，屬性：`station_id`, `name`
- 關係：`CONNECTS_TO`（有向），屬性：`travel_time_min`

**可用的外部 fare 函式（已在 main 上）：**
```python
from databases.relational.queries import query_metro_fare, query_national_rail_fare

# query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]
# 回傳 {"base_fare_usd": ..., "per_stop_rate_usd": ..., "total_fare_usd": ...}
# 若 schedule_id 不存在回傳 None

# query_national_rail_fare(schedule_id: str, fare_class: str, stops_travelled: int) -> Optional[dict]
# 回傳 {"fare_class": ..., "base_fare_usd": ..., "per_stop_rate_usd": ..., "total_fare_usd": ...}
# fare_class: "standard" 或 "first"
# 若 schedule_id 不存在回傳 None
```

**重要限制：** 圖裡的節點沒有 `schedule_id` 屬性，無法直接呼叫上面的 fare 函式。
請用以下 proxy 公式計算票價（fare_class 必須明顯影響結果，評分關鍵）：
- metro（無論 fare_class）：`total_fare_usd = 1.0 + stops_travelled × 0.5`
- national_rail standard：`total_fare_usd = 2.0 + stops_travelled × 1.2`
- national_rail first：`total_fare_usd = 2.0 + stops_travelled × 2.0`

其中 `stops_travelled = len(path) - 1`（路徑站數減一）。

**函式要求：**
- 用 APOC dijkstra（加權 by `travel_time_min`）找最快路線，再計算票價
- 用 `_infer_network(origin_id)` 判斷網路類型
- 回傳格式：
  ```
  {
    "found": True,
    "total_fare_usd": <數字>,
    "fare_class": <fare_class 參數值>,
    "path": [{"station_id": ..., "name": ...}, ...],
    "legs": [{"line": ..., "travel_time_min": ...}, ...]
  }
  ```
- 無路徑或出錯時回傳 `found=False` 的同樣結構，`total_fare_usd=None`，**不能 raise exception**
- 使用 `_get_driver().session()` 取得 session
- 刪除現有的 `raise NotImplementedError` 和所有 CYPHER HINT 註解

完成後用以下 commit message 提交：
`feat(graph): implement query_cheapest_route with fare_class weighting`

只修改 `databases/graph/queries.py`，不動其他任何檔案。
```

---

## Sync 2 完成後的指令（你自己跑）

```bash
git push origin feature/Chien/graph-queries
# 通知蔡晟郁：函式 6 已 push，等你 ready 一起開 PR
# 記得：蔡先 merge → 你再 merge
```
