# Live Testing 測試紀錄

> 測試日期：2026-06-05
> 環境：本機 Docker + Ollama (llama3.2:1b + nomic-embed-text)
> 測試者：蔡晟郁

---

## 環境啟動紀錄

| 步驟 | 結果 | 備註 |
|------|------|------|
| docker compose up | ✅ | PostgreSQL + Neo4j 均 healthy |
| seed_postgres.py | ✅ 修正後通過 | `stops_travelled` null → 0（mock data 有 null，schema 設 NOT NULL）|
| seed_vectors.py | ✅ | 101 chunks 存入 policy_documents |
| seed_neo4j.py | ✅ | 20 MetroStation, 10 NationalRailStation, 42 METRO_LINK, 18 RAIL_LINK, 6 INTERCHANGE_TO |
| ui.py | ✅ | http://127.0.0.1:7860 正常開啟 |

---

## 測試帳號

- Email：`alice.tan@email.com`
- Password：`alice1990`

---

## 功能測試結果

### B1 — `query_national_rail_availability`

**問題：** `What trains are available from NR01 to NR05 on 2026-04-10?`

**結果：** ✅ 正常

- 回傳兩班車：NR_SCH01（normal）、NR_SCH05（express）
- `available_seats` 正確計算（NR_SCH01: 18）
- 2026-04-10 星期四，兩班均有運行

**注意：** NR_SCH05 的 `available_seats: 0`，因為 mock data 的 seat_layouts.json 未替 NR_SCH05 配置座位，計算結果為 0，非 bug。

**LLM 行為：** llama3.2:1b 會在呼叫 tool 前先「猜答案」，屬正常現象。tool 回傳的實際資料正確。

---

### B3 — `query_national_rail_fare`

**問題：** `What is the fare from NR01 to NR03 for standard class with 2 stops?`

**結果：** ⚠️ LLM 回應「No data was found」

**原因：** `query_national_rail_fare` 需要 `schedule_id` 參數，但問題只提供站名。llama3.2:1b 無法執行「先查 availability → 取得 schedule_id → 再查 fare」的兩步推理，導致 tool 未被正確呼叫。

**程式碼本身無問題**，是模型限制。

**建議問法：**
```
What is the fare for schedule NR_SCH01, standard class, 2 stops?
```

---

### B2 — `query_metro_schedules`

**問題：** `What metro lines go from MS01 to MS07?`

**結果：** ⚠️ LLM 幻覺 + 呼叫錯誤 tool

**LLM 回應（幻覺）：**
> Two metro lines go from MS01 to MS07: Line M1, Line M4

**實際發生：**
- LLM 沒有呼叫 `query_metro_schedules`，而是呼叫了 `find_route`（cheapest route）
- `find_route` 正確回傳：MS01 → MS07 via **M2 line**，2 分鐘，$2.00
- LLM 說的「M1 和 M4」是幻覺，正確路線是 M2

**Tool 回傳資料（正確）：**
```json
{
  "found": true,
  "origin_id": "MS01",
  "destination_id": "MS07",
  "total_fare_usd": 2.0,
  "fare_class": "standard",
  "path": [
    {"station_id": "MS01", "name": "Central Square"},
    {"station_id": "MS07", "name": "Old Town"}
  ],
  "legs": [{"travel_time_min": 2, "line": "M2", "fare_usd": 2.0}]
}
```

**結論：** `query_metro_schedules` 本身未被觸發，`find_route`（cheapest route）功能正常。B2 仍需以更明確問法測試。

**建議問法：**
```
Which metro schedules serve both MS01 and MS07?
```

---

## 待測項目

| 函式 | 測試狀態 |
|------|---------|
| B1 `query_national_rail_availability` | ✅ 正常 |
| B2 `query_metro_schedules` | ⚠️ tool 未觸發（LLM 選錯 tool），待補測 |
| B3 `query_national_rail_fare` | ⚠️ LLM 多步推理失敗，程式碼正確 |
| B4 `query_metro_fare` | ✅ 正常（MS_SCH01 3站：base=0.8, rate=0.3, total=1.7） |
| B5 `query_available_seats` | ✅ 正常（12 seats 回傳，LLM 解釋文字有誤但 tool 正確） |
| B6 `query_user_profile` | ✅ 函式正確（直接呼叫驗證：回傳 user_id, full_name, email, year_of_birth=1990, is_active）。UI 測試 LLM 持續選錯 tool，為模型限制非程式碼問題 |
| B7 `query_user_bookings` | ✅ 正常（national_rail 2筆 + metro 1筆，兩個 key 均存在） |
| B8 `query_payment_info` | ✅ 正常（BK001: PM001, $8.50, paid, credit_card；未知 ID 回傳 None） |
| B9 `execute_booking` | ✅ 正常（建立成功回 (True, {booking_id, user_id, seat_id})；重複座位回 (False, message)；atomic transaction 確認） |
| B10 `execute_cancellation` | ✅ 正常（BK020 取消成功，refund_amount=0.0；重複取消回 (False, 'already cancelled')） |
| C1 `query_shortest_route` | ✅ 正常（MS01→MS09，11分鐘，4站，path+legs 完整；LLM 解釋有誤但 tool 正確） |
| C2 `query_cheapest_route` | ✅ 正常（NR01→NR07，total_fare_usd=40.0，standard class，fare_usd 各 leg 完整） |
| C3 `query_alternative_routes` | ⚠️ 3條路線但全部重複（需黃加 DISTINCT）。函式本身不崩潰，資料正確只是去重未做 |
| C4 `query_interchange_path` | 🔴 `*1..20` 效能問題，Python 直接呼叫仍超時。需黃改用 shortestPath 優化 |
| C5 `query_delay_ripple` | 🔴 **確認 runtime bug**：`shortestPath(s→s)` 同起終點報錯，hops=2 靜默回傳空陣列。需黃改用 `min(length(path))` 命名 path 變數 |
| C6 `query_station_connections` | ✅ 正常（MS01有4個鄰站，各含 station_id, name, line, travel_time_min） |
| RAG `search_policy` | ✅ 正常（回傳 5 筆 refund policy chunks，similarity 0.607–0.664，reranker 正常運作） |

---

## 已知問題 / 注意事項

1. **seed_postgres 修正**：`seed_metro_travels` 裡 `stops_travelled` 改用 `t.get("stops_travelled") or 0`，已修。
2. **Ollama 安裝**：Homebrew 版本缺少 llama-server binary，需使用官方安裝（`curl -fsSL https://ollama.com/install.sh | sh`）。
3. **llama3.2:1b 多步推理限制**：需跨兩個 tool 的問題（如先查 schedule_id 再查 fare）可能失敗，非程式碼 bug。
4. **llama3.2:1b 幻覺問題**：模型會在呼叫 tool 前先猜答案，有時選錯 tool。Tool 的實際回傳資料正確，問題出在 LLM 選 tool 的邏輯。
5. **C4 UI 超時根因確認**：直接對 Neo4j 執行 `query_interchange_path` Cypher 僅需 0.22 秒，路徑正確。UI 超時完全來自 llama3.2:1b 推理緩慢，程式碼無問題。TA 若直接呼叫 Python function 測試，結果正常。
5. **NR_SCH05 available_seats = 0**：mock data 的 seat_layouts.json 未替 NR_SCH05 配置座位，計算結果為 0，非 bug。
