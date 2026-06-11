# Live Testing Results — TransitFlow
> 測試日期：2026-06-05 | 測試者：蔡晟郁

---

## Section B — PostgreSQL Queries（/50）

### B1 `query_national_rail_availability` ✅ 通過

**問題：** "What national rail trains run from NR01 to NR05 on 2026-06-10?"

**Tool called：** `check_national_rail_availability({'origin_id': 'NR01', 'destination_id': 'NR05', 'travel_date': '2026-06-10'})`

**結果：** 2 班次回傳
- NR_SCH01（normal，NR1 line）：18 available seats，每天運行，first train 06:00
- NR_SCH05（express，NR1 line）：0 available seats，週一至五，first train 07:00

**評分項目：**
- ✅ 回傳有 schedule_id 和 available_seats
- ✅ 正確過濾方向（origin 在 dest 之前）
- ✅ 無 exception

---

### B1 補充（登入後重測）✅ 確認通過
- 登入帳號：alice.tan@email.com
- 結果同上，raw data 正確
- LLM 文字摘要有輕微誤判（NR_SCH05 路線描述錯），但 function 回傳值正確，不影響評分

---

### B2 `query_metro_schedules` ⚠️ LLM 選錯工具，Function 正確

**UI 測試：** LLM 呼叫 `search_policy` 而非 `query_metro_schedules`，幻覺回答 M1/M2/M3/M4
**直接呼叫：** `query_metro_schedules('MS01', 'MS09')` → 回傳 M2 line，stops_in_order 正確，有 base_fare_usd
**結論：** Function 本身 ✅，LLM tool selection ❌（模型問題，非程式碼問題）

### B3 `query_national_rail_fare` ⚠️ LLM 無回應，Function 正確

**UI 測試：** LLM 回傳「No data found」，未呼叫正確 tool
**直接呼叫：** `query_national_rail_fare('NR_SCH01', 'standard', 4)` →
- base_fare_usd: 2.50
- per_stop_rate_usd: 1.50
- total_fare_usd: 8.50（2.50 + 1.50×4 = 8.50 ✅ 算數正確）
**結論：** Function 本身 ✅，LLM tool selection ❌

### B4 `query_metro_fare` ✅ 通過

**Tool called：** `get_metro_fare({'origin_id': 'MS01', 'destination_id': 'MS09'})`
**結果：** base_fare_usd=0.80, per_stop_rate_usd=0.30, stops=4, total_fare_usd=2.00
**算數驗證：** 0.80 + 0.30×4 = 2.00 ✅
**LLM 文字：** 幻覺嚴重（算錯、還算了來回），但 raw data 正確，不影響評分

### B5 `query_available_seats` ✅ 通過

**Tool called：** `get_available_seats({'schedule_id': 'NR_SCH01', 'travel_date': '20230610', 'fare_class': 'standard'})`
**結果：** 12 個 standard class 座位（B01–B12），每個有 seat_id ✅
**LLM 文字：** 說「no available seats」，完全幻覺，raw data 正確

### B6 `query_user_profile` ⚠️ LLM 選錯工具，Function 正確

**UI 測試：** LLM 呼叫 `get_user_bookings({})` 而非 user profile tool
**直接呼叫：** `query_user_profile('alice.tan@email.com')` → user_id, full_name, email, year_of_birth=1990 ✅
**Unknown email：** 未測（預期回傳 None）

### B7 `query_user_bookings` ✅ 通過（B6 問題時意外測到）

**Tool called：** `get_user_bookings({})` → 正確帶入當前登入用戶 RU01
**結果：**
- national_rail: 4 筆（BK001 completed、BK-SXYM74 confirmed、BK020 cancelled、BK-DHKBGW cancelled）
- metro: 1 筆（MT009 completed）
- 兩個 key 都存在 ✅

### B8 `query_payment_info` ⚠️ LLM 選錯工具，Function 正確

**UI 測試：** LLM 呼叫 `search_policy` 並出現 error
**直接呼叫：** `query_payment_info('BK001')` → payment_id, amount_usd=8.50, method=credit_card, status=paid ✅
**Unknown ID：** `query_payment_info('BK999')` → `None` ✅（不是 exception）

### B9 `execute_booking` ⚠️ LLM 未呼叫 booking tool，Function 正確

**UI 測試：** LLM fallback 到 availability query，未執行訂票
**直接呼叫：** `execute_booking('RU01', 'NR_SCH01', 'NR01', 'NR05', '2026-06-20', 'standard', 'B04')`
- 成功：`(True, booking_dict)` ✅，booking_id=BK-6MXUOO，seat_id=B04，status=confirmed
- 重複訂同座位：`(False, 'Seat B04 is unavailable...')` ✅（不是 exception）
- booking + payment atomic：已在之前 code review 確認 ✅

### B10 `execute_cancellation` ⚠️ LLM 未呼叫 cancellation tool，Function 正確

**UI 測試：** LLM 回傳「No data found」
**直接呼叫：** `execute_cancellation('BK-6MXUOO', 'RU01')`
- 成功：`(True, {'booking_id': ..., 'refund_amount': 8.5, 'policy_note': 'Early cancellation'})` ✅
- 重複取消：`(False, 'Booking is already cancelled')` ✅（不是 exception）

---

## Section C — Neo4j Routing Queries（/35）

### C1 `query_shortest_route` ✅ 通過

**Tool called：** `find_route({'origin_id': 'MS01', 'destination_id': 'MS09', 'optimise_by': 'time'})`
**結果：** found=True，path=MS01→MS07→MS18→MS08→MS09，total_time_min=11，legs 各段時間正確
**驗算：** 2+2+4+3=11 ✅

### C2 `query_cheapest_route` ✅ 通過

**Tool called：** `find_route({'origin_id': 'NR01', 'destination_id': 'NR05', 'optimise_by': 'cost'})`
**Standard：** found=True，total_fare_usd=86.0，legs 各有 fare_usd，算數正確 ✅
**First class（直接呼叫）：** total_fare_usd=138.0，fare_class='first'，與 standard 不同 ✅

### C3 `query_alternative_routes` ⚠️ LLM 選錯工具，Function 正確

**UI 測試：** LLM 叫 `find_route`，回傳路徑還包含 MS07（應避開的站）
**直接呼叫：** `query_alternative_routes('MS01', 'MS09', avoid_station_id='MS07', max_routes=3)`
- 3 條路線，皆不含 MS07 ✅
- max_routes=1 → 只回傳 1 條 ✅

### C4 `query_interchange_path` ✅ 通過

**Tool called：** `find_route({'origin_id': 'MS01', 'destination_id': 'NR05', 'network': 'metro', 'optimise_by': 'time'})`
**結果：** found=True，path 含 MS01(metro)→MS07(interchange)→NR03(interchange)→NR04→NR05(rail)
**interchange_points：** MS07→NR03，transfer_time_min=5 ✅
**total_time_min：** 42，秒回 ✅

### C5 `query_delay_ripple` ⚠️ LLM 傳錯參數格式，Function 正確

**UI 測試：** LLM 把 station_id 包在 nested object 裡，KeyError: 'station_id'
**直接呼叫：** `query_delay_ripple('MS07', hops=2)` → 8 站，各有 hops_away ✅
**hops=0：** 只回傳 MS07 本身 ✅

### C6 `query_station_connections` ⚠️ LLM 選錯工具，Function 正確

**UI 測試：** LLM 叫 `search_policy`，回傳政策文件而非站點資訊
**直接呼叫：** `query_station_connections('MS01')` → 4 站（MS07/MS06/MS05/MS02），各有 travel_time_min ✅

---

## 總結

| 項目 | Function | UI/LLM |
|------|---------|---------|
| B1 國鐵班次 | ✅ | ✅ Tool 正確 |
| B2 捷運班次 | ✅ | ❌ 叫 search_policy |
| B3 國鐵票價 | ✅ | ❌ 無回應 |
| B4 捷運票價 | ✅ | ✅ Tool 正確 |
| B5 可用座位 | ✅ | ✅ Tool 正確，LLM 文字幻覺 |
| B6 用戶資料 | ✅ | ❌ 叫 get_user_bookings |
| B7 預訂記錄 | ✅ | ✅ 意外測到，正確 |
| B8 付款資訊 | ✅ | ❌ 叫 search_policy |
| B9 訂票 | ✅ | ❌ fallback 到 availability |
| B10 取消訂票 | ✅ | ❌ 無回應 |
| C1 最快路線 | ✅ | ✅ Tool 正確 |
| C2 最便宜路線 | ✅ | ✅ Tool 正確（fallback） |
| C3 替代路線 | ✅ | ❌ 叫 find_route 且含 MS07 |
| C4 跨網路換乘 | ✅ | ✅ Tool 正確 |
| C5 延誤漣漪 | ✅ | ❌ 參數格式錯誤 |
| C6 站點連線 | ✅ | ❌ 叫 search_policy |

**結論：所有 16 個 Function 本身皆正確。LLM（llama3.2:1b）tool selection 不穩定，TA 直接呼叫 Python function 可得滿分。**
