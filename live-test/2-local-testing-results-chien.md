# Local Testing Results — TransitFlow（Chien）

> 測試日期：2026-06-09 ｜ 測試者：黃謙儒（Chien，Graph DB Engineer）
> 環境：Windows 10 Pro / PowerShell / Docker Desktop(WSL2)
> LLM：**Ollama (llama3.2:1b)** 與 **Gemini (gemini-3.1-flash-lite + gemini-embedding-001, 3072 維)** 兩輪
> 方法：UI（經 LLM）＋ 直接呼叫 Python function 雙軌，分離「函式正確性」與「LLM 行為」。
> 逐步測試流程與環境踩坑見 [local-testing-notes-chien.md](local-testing-notes-chien.md)。對照基準：[live-testing-results.md](live-testing-results.md)（蔡 06-05, Ollama）。

---

## Section B — PostgreSQL Queries（/50）

### B1 `query_national_rail_availability` ✅ 通過
- **問題：** `What national rail trains run from NR01 to NR05 on 2026-06-10?`
- **Gemini tool：** `check_national_rail_availability({origin_id:NR01, destination_id:NR05, travel_date:2026-06-10})`
- **結果：** 2 班次 — NR_SCH01（normal，18 席）、NR_SCH05（express，0 席）。LLM 文字準確（含「週三」、班距、行車時間）。
- **判定：** Tool ✅ / Function ✅ / LLM 文字 ✅。（NR_SCH05 的 0 席為 mock data 未配座位，非 bug）

### B2 `query_metro_schedules`（工具名 `check_metro_availability`）✅ 通過
- **問題：** `Which metro schedules serve both MS01 and MS09?`
- **Gemini tool：** `check_metro_availability({origin_id:MS01, destination_id:MS09})`
- **結果：** MS_SCH03（M2, eastbound），`stops_in_order=[MS06,MS01,MS07,MS18,MS08,MS09]`，含 MS01 與 MS09；LLM 正確算出兩站間 11 分。
- **判定：** Tool ✅ / Function ✅ / LLM ✅。（對照蔡 Ollama：曾誤叫 search_policy/find_route 並幻覺）

### B3 `query_national_rail_fare` ✅ 通過
- **問題：** `What is the standard class fare for schedule NR_SCH01 travelling 4 stops?`
- **Gemini tool：** `get_national_rail_fare({schedule_id:NR_SCH01, fare_class:standard, stops_travelled:4})`
- **結果：** base 2.5 + 1.5×4 = **8.5** ✅（LLM 此次傳 int 4）。
- **⚠️ 直接呼叫確認**：`query_national_rail_fare('NR_SCH01','standard','4')`（字串）→ **同樣 crash** `can't multiply sequence by non-int of type 'float'`。**B3 與 B4 是同一個未轉型 bug**（見問題清單 #1），B3 在 UI 過關純粹是 LLM 那次傳了 int。
- **判定：** Tool ✅ / Function ⚠️（int 正確、string crash）/ LLM ✅。

### B4 `query_metro_fare` 🔴 **Function crash（真 bug）**
- **問題：** `What is the metro fare from MS01 to MS09?`
- **Gemini tool：** `calculate_metro_fare({schedule_id:MS_SCH03, stops_travelled:"4"})` ← **參數是字串 "4"**
- **結果：** `error: can't multiply sequence by non-int of type 'float'`
- **root cause：** [databases/relational/queries.py:225](databases/relational/queries.py#L225) `round(base + per_stop * stops_travelled, 2)` 未把 `stops_travelled` 轉型；LLM 傳字串 `"4"` 時 `0.30 * "4"` 崩。**[queries.py:164](databases/relational/queries.py#L164) 國鐵 fare 同樣潛伏**（B3 僥倖收到 int 才沒爆）。
- **判定：** Tool ✅ / **Function 🔴**（一行修：`int(stops_travelled)`）。屬 relational（蔡）/ agent dispatch（蔣）健壯性 bug。

### B5 `query_available_seats` ✅ 通過
- **問題：** `Which standard class seats are available on schedule NR_SCH01 on 2026-06-10?`
- **Gemini tool：** `get_available_seats({schedule_id:NR_SCH01, travel_date:2026-06-10, fare_class:standard})`
- **結果：** 12 席 B01–B12，LLM 全列對。
- **判定：** Tool ✅ / Function ✅ / LLM ✅。（蔡 Ollama 曾文字幻覺「no seats」）

### B6 `query_user_profile` ⚠️ Tool 未觸發（fallback 搶走），Function 正確
- **問題（已登入 alice）：** `Show my user profile details`
- **Gemini tool：** `[]`（LLM 未選工具）→ **agent fallback 規則 #3（"show my"）搶成 `get_user_bookings`**
- **結果：** profile 工具未被呼叫；LLM 文字（Alice Tan / RU01 / email）取自登入 session，剛好正確。
- **判定：** Tool ❌（fallback 過度觸發）/ Function ✅（蔡直接呼叫驗證：user_id, full_name, email, year_of_birth=1990）。

### B7 `query_user_bookings` ✅ 通過（B6 fallback 時意外測到）
- **Gemini tool：** `get_user_bookings({})`（帶入當前 RU01）
- **結果（乾淨 seed）：** national_rail 2 筆（BK001 completed、BK020 confirmed）＋ metro 1 筆（MT009 completed），兩 key 皆存在 ✅。
- **判定：** Tool ✅ / Function ✅。（資料量與蔡不同，因本機 `down -v` 重灌為初始 seed）

### B8 `query_payment_info` 🔴 **未註冊成 agent 工具（整合缺口）**
- **問題：** `What is the payment information for booking BK001?`（登入前後皆試）
- **Gemini tool：** `search_policy(...)`（兩 provider 都選這個）→ 撞 sentence_transformers 未裝
- **root cause：** `query_payment_info` 存在於 [queries.py:360](databases/relational/queries.py#L360) 且正確，但 **agent.py 工具清單完全沒有 payment 工具**（`grep payment skeleton/agent.py` 無結果）→ LLM 無從選取，只能 fallback 到 search_policy。
- **判定：** Tool 🔴（無此工具可選）/ Function ✅（蔡直接呼叫：BK001 $8.50 paid；未知 ID 回 None）。**透過助理永遠到不了。**
- **後續（已修）：** 蔣已將 `query_payment_info` 註冊成 agent 工具（README 明列此為 `skeleton/agent.py` 允許的擴充）。待恢復測試後在 UI 重驗，並確認比照個人資料要求登入。

### B9 `execute_booking`（工具名 `make_booking`）✅ 通過
- **問題：** `Book seat B04 in standard class on schedule NR_SCH01 from NR01 to NR05 on 2026-06-20`
- **Gemini tool：** `make_booking({schedule_id, origin, destination, travel_date, fare_class, seat_id})` 六參數齊
- **結果：** 建立 **BK-COI6Y4**（RU01, seat B04, standard, $8.50, confirmed）✅。
- **邊界（直接呼叫）：** 重複訂同座位 → `(False, 'Seat B06 is unavailable...')`（不丟例外）✅。
- **判定：** Tool ✅ / Function ✅ / LLM ✅。（蔡 Ollama 曾 fallback 到 availability 未訂成）

### B10 `execute_cancellation`（工具名 `cancel_booking`）🔴 **Function crash（Windows 專屬真 bug）**
- **問題：** `Cancel my booking BK-COI6Y4`
- **Gemini tool：** `cancel_booking({booking_id:BK-COI6Y4})` ✅ 選對
- **結果：** `error: 'cp950' codec can't decode byte 0xe2 in position 63`
- **root cause：** [queries.py:536-537](databases/relational/queries.py#L536) `with open(_POLICY_PATH) as f: policies = json.load(f)` **漏 `encoding='utf-8'`**；`refund_policy.json` 為 UTF-8（含 0xe2 起始字元），繁中 Windows 預設 cp950 解碼失敗。
- **直接呼叫第一手確認**：在預設編碼（`locale.getpreferredencoding()=cp950`，即 UI 跑法）下 `execute_cancellation('BK001','RU01')` 於 `json.load` 崩，**且崩在檢查訂單狀態之前** → Windows 上任何取消都會掛，與訂單狀態無關。加 `PYTHONUTF8=1` 則被遮蔽（會正常取消）。蔡在 Mac（預設 utf-8）故未遇到。此 `open()` 亦在 try 外（Chien 06-04 code review 已標）。
- **判定：** Tool ✅ / **Function 🔴 on Windows**（一行修：`open(_POLICY_PATH, encoding='utf-8')`）。
- **取消邏輯本身正確（UTF-8 模式直接呼叫）：** 取消成功回 `(True, {refund_amount, policy_note})`；重複取消回 `(False, 'Booking is already cancelled')`（不丟例外）✅。**唯一缺陷就是該行編碼**，修 `encoding='utf-8'` 後 Windows 即全通。
- **副作用註記：** 直接呼叫驗證期間在 UTF-8 模式下 BK-COI6Y4 已**實際被取消**（refund 8.5），不再是 confirmed。

---

## Section — RAG / Policy Search（vector，蔣負責）

> 前提：先 `pip install sentence-transformers`（5.5.1）——**原 requirements.txt 漏宣告，未裝時 search_policy 全炸**（問題清單 #5）。裝後整條鏈路（Gemini embed 3072 → pgvector 搜尋 → CrossEncoder 重排）正常。

### RAG-1 政策：單車 ✅ 通過
- **問題：** `What is the company policy on travelling with a bicycle on national rail?`
- **Gemini tool：** `search_policy({query:"travelling with a bicycle on national rail"})`
- **結果：** 回 5 筆 *Travel Policies — National Rail*（sim 0.79–0.86），LLM 答案準確（折疊車免費/無尖峰限制/90cm、標準車尖峰禁行+$2、e-scooter 禁止）。
- **判定：** Tool ✅ / 檢索 ✅ / Rerank ✅ / LLM ✅。
- **效能註記：** **首次呼叫 ~60s**（CrossEncoder `ms-marco-MiniLM-L-6-v2` 在 CPU 冷啟動載入；torch 為 CPU 版）。模型載入後常駐，後續變快。

### RAG-2 政策：延誤補償 ✅ 通過（首次 LLM 拒答、重試正常）
- **問題：** `My train was delayed 45 minutes, what compensation am I entitled to?`
- **第一次：** LLM 送 `search_policy({query:"compensation delay"})`，**檢索有結果**（直接呼叫確認 top hit *Delay Compensation* sim 0.764 / rerank 5.187），但 LLM 文字回「no data found」——**一次性拒答變異**。
- **重試：** LLM 送 `search_policy({query:"compensation policy for delayed journeys"})`，回 RF005 規則，**LLM 正確套用 RF005_R1**：45 分（30–59 分區間）→ 50% 退費、28 天內申請、force majeure 不適用。
- **判定：** Tool ✅ / 檢索 ✅ / Rerank ✅ / LLM ⚠️（首次拒答、重試正確；模型變異，非檢索問題）。

---

## Section — Auth（register / login）

### login_user ✅ 通過
- UI 以 `alice.tan@email.com` / `alice1990` 登入成功（後續 B6–B10 皆在登入態）；`query_user_profile` 回 RU01 / Alice Tan。

### register_user ✅ 通過（含一次 email typo 排查）
- UI 註冊新帳號後登出再登入，回報「查無此 email」。
- **直接查 DB 確認**：帳號其實**註冊成功**——`user_id=RU3AF9BM`、`email=test@gmaill.com`、`is_active=True`、password 為 60 字元 bcrypt 雜湊；總用戶數 20→21。
- **root cause：非程式 bug，是輸入 typo**：註冊存的是 `test@gmaill.com`（兩個 L），登入打成 `test@gmail.com`（一個 L）→ 不匹配。
- **判定：** register_user ✅（正確寫入 + 密碼雜湊 + is_active）/ login_user ✅（比對 email 正確，不匹配即拒登，行為正確）。

---

## Section C — Neo4j Routing Queries（/35）

> 6 支 graph 函式均為 Chien 主責。直接呼叫結果全部正確（見 [local-testing-notes-chien.md](local-testing-notes-chien.md) §4）。

### C1 `query_shortest_route` ✅ 通過
- **問題：** `What is the fastest metro route from MS01 to MS14?`
- **Gemini tool：** `find_route({origin_id:MS01, destination_id:MS14, optimise_by:time})`
- **結果：** path MS01→MS07→MS18→MS08→MS12→MS14，total_time_min=**16**（2+2+4+4+4），LLM 文字也算對。
- **判定：** Tool ✅ / Function ✅ / LLM ✅。（蔡 Ollama / 本機 Ollama：optimise 帶 cost、文字算錯）

### C2 `query_cheapest_route` ✅ 通過
- **問題：** `What is the cheapest national rail route from NR01 to NR05?`
- **Gemini tool：** `find_route({origin_id:NR01, destination_id:NR05, optimise_by:cost})`
- **結果：** standard total_fare=**86.0**（16.4+23.6+20+26）；first（直接呼叫）=**138.0**，fare_class 真的切換。
- **判定：** Tool ✅ / Function ✅ / LLM ✅。

### C3 `query_alternative_routes` 🔴 **agent.py fallback 覆蓋正確選擇**
- **問題：** `If Old Town (MS07) is closed, what alternative metro routes exist from MS01 to MS09?`
- **Gemini tool：** `find_alternative_routes({origin_id:MS01, destination_id:MS09, avoid_station_id:MS07, network:metro})` ← **LLM 選對、參數全對**
- **但隨後：** `Fallback: route query → find_route({origin_id:MS07, destination_id:MS07})` → 退化結果「MS07→MS07, 0 分」
- **root cause：** [skeleton/agent.py:686](skeleton/agent.py#L686) fallback 規則 #1：問句含「route(s)」+ ≥2 站號即觸發，guard 只檢查「是否選了 find_route」，**未排除「已正確選 find_alternative_routes」**；且 `re.findall` 取站號時避開站 MS07 最先出現被當 origin。
- **直接呼叫：** `query_alternative_routes('MS01','MS09','MS07')` → **3 條，皆不含 MS07** ✅。
- **判定：** LLM ✅ / **agent.py 🔴** / Function ✅。
- **補註：** 指南原 C3 問句 `NR01→NR05 避 NR03` 在國鐵 NR1 線性鏈下永遠回 `[]`（正確但測不到去重），已改為此捷運問句。

### C4 `query_interchange_path` ✅ 通過
- **問題：** `How do I get from Central Square (MS01) to Stonehaven (NR05)?`
- **Gemini tool：** `find_route({origin_id:MS01, destination_id:NR05})`
- **結果：** path MS01→MS07(interchange)→NR03(interchange)→NR04→NR05；interchange MS07→NR03（transfer 5 min）；total=**42**；**3–4 秒回**。
- **判定：** Tool ✅ / Function ✅ / LLM ✅。秒回證明 `shortestPath(*1..10)` 逾時回退穩定。

### C5 `query_delay_ripple` ✅ 通過
- **問題：** `If MS05 is delayed, which stations are affected?`
- **Gemini tool：** `get_delay_ripple({station_id:MS05})` ← 正確帶 station_id（Ollama 此處把 schema 當參數而失敗）
- **結果：** MS05(0)、MS20/MS01(1)、MS07/MS06/MS02(2)，各帶 hops_away 與 lines_affected；**無 Cypher 語法錯**；`hops=0` 特判（直接呼叫）只回 MS05 ✅。
- **判定：** Tool ✅ / Function ✅。（raw 含已知輕微限制：起點 MS05 以 hops 2 自我重現）

### C6 `query_station_connections` ⚠️ Function 正確，LLM 文字誤讀
- **問題：** `Which stations directly connect to Central Square (MS01)?`
- **Gemini tool：** `get_station_connections({station_id:MS01})`
- **結果：** 4 鄰站 MS07(M2,2)、MS06(M2,3)、MS05(M1,3)、MS02(M1,3)，依時間排序 ✅；但 LLM 把「MS01 的鄰站」誤讀成「那 4 站各自的連線」而給否定答覆。
- **root cause（非函式錯）：** 回傳為**裸 list、未帶原點標記**（不像 find_route 有 origin_id），LLM 易混淆。可選優化：包成 `{"station_id":"MS01","connections":[...]}`。
- **判定：** Tool ✅ / Function ✅ / LLM 文字 ❌（輸出格式優化點，非 bug）。

---

## 總結

| 項目 | Function | Ollama UI | Gemini UI (3.1-flash-lite) |
|------|:---:|:---:|:---:|
| B1 國鐵班次 | ✅ | （蔡 ✅）| ✅ Tool 正確 |
| B2 捷運班次 | ✅ | （蔡 ❌ 幻覺）| ✅ Tool 正確 |
| B3 國鐵票價 | ✅ | （蔡 ❌ 兩步推理）| ✅ Tool 正確 |
| B4 捷運票價 | 🔴 crash | （蔡 ✅，傳 int）| ❌ string×float crash |
| B5 可用座位 | ✅ | （蔡 ✅）| ✅ Tool 正確 |
| B6 用戶資料 | ✅ | （蔡 ❌ 選 bookings）| ❌ fallback 搶成 bookings |
| B7 預訂記錄 | ✅ | （蔡 ✅）| ✅ Tool 正確 |
| B8 付款資訊 | ✅ | （蔡 ❌ search_policy）| ❌ **未註冊成工具** |
| B9 訂票 | ✅ | （蔡 ❌ fallback）| ✅ Tool 正確 |
| B10 取消訂票 | 🔴 crash(Win) | （蔡 ✅ on Mac）| ❌ Windows encoding crash |
| C1 最快路線 | ✅ | ⚠️ 參數錯 | ✅ Tool 正確 |
| C2 最便宜路線 | ✅ | （蔡 ✅）| ✅ Tool 正確 |
| C3 替代路線 | ✅ | ❌ schema 當參數 | ❌ agent.py fallback 覆蓋（LLM 選對）|
| C4 跨網換乘 | ✅ | ✅ | ✅ Tool 正確、秒回 |
| C5 延誤漣漪 | ✅ | ❌ schema 當參數 | ✅ Tool 正確 |
| C6 站點連線 | ✅ | （蔡 ❌ search_policy）| ⚠️ Tool 對、LLM 誤讀裸 list |

**結論：**
1. **Graph（Section C）6 支函式輸出全部正確**（兩 provider + 直接呼叫三方驗證）。UI 殘留兩現象（C3 agent.py fallback、C6 裸 list 誤讀）皆非 graph 函式問題。
2. **gemini-3.1-flash-lite 的 LLM 工具選擇遠優於 llama3.2:1b**：Section C 六題工具全選對（含 Ollama 失敗的 optimise/station_id）；Section B 十題中 6 題全綠。
3. 殘留問題集中在 **relational / agent / vector** 層（非 Chien 的 graph）。

---

## 🐞 發現的問題清單（依嚴重度）

| # | 問題 | 位置 | 層／負責 | 嚴重度 | 建議修法 |
|---|------|------|---------|:---:|---------|
| 1 | `query_metro_fare`（B4）**與** `query_national_rail_fare`（B3）未轉型 → `stops_travelled` 為字串時 string×float crash（**兩支均直接呼叫確認**）| [queries.py:225](databases/relational/queries.py#L225) / [:164](databases/relational/queries.py#L164) | relational（蔡）| 🔴 高 | `stops = int(stops_travelled)` 後再運算 |
| 2 | `execute_cancellation` open() 漏 `encoding='utf-8'` → Windows cp950 crash | [queries.py:536](databases/relational/queries.py#L536) | relational（蔡）| 🔴 高（Windows）| `open(_POLICY_PATH, encoding='utf-8')` |
| 3 | `query_payment_info` 未註冊成 agent 工具 → 助理無法觸及 ｜ **✅ 蔣已註冊修復**（README「Your Tasks」明列 `skeleton/agent.py` 可「Register new query functions as tools」，屬官方允許的純加法擴充；待恢復測試後 UI 重驗，並確認比照 booking/profile 要求登入）| skeleton/agent.py | agent（蔣）| ✅ 已修 | 在工具清單註冊 payment 工具 + dispatch 分支 |
| 4 | agent.py fallback 規則 #1 覆蓋正確的 `find_alternative_routes`（C3）；規則 #3 "show my" 搶走 profile（B6）｜ **團隊決議：保留為已知限制、不改**（改 fallback 屬「除非知道自己在做什麼否則勿動」的 skeleton 核心邏輯；此 fallback 是預設 Ollama 的 tool-use 兜底安全網，動它有回歸風險；底層函式皆正確、僅 UI 次佳，TA 直接呼叫不受影響）| [agent.py:686](skeleton/agent.py#L686), :708 | agent（蔣）| 🟠 中（暫不修）| 若要修：只加 narrow guard（已正確選到對應工具就不觸發），並於 Ollama+Gemini 雙 provider 重測；偏 Task 6 等級 |
| 5 | `requirements.txt` 漏 `sentence-transformers` → RAG（search_policy）全炸（**裝 5.5.1 後兩題 RAG 皆通過**，確認僅缺宣告）| [reranker.py:19](skeleton/reranker.py#L19) 頂層 import | vector（蔣）| 🟠 中 | 補進 requirements；或 import 失敗時優雅降級回向量相似度 |
| 6 | pgvector HNSW 索引上限 2000 維，與 Gemini 3072 維衝突 | [schema.sql](databases/relational/schema.sql) | relational（蔡）| 🟡 低 | 3072 時不建 HNSW（已註解），或改 `halfvec(3072)` cast 索引 |
| 7 | `query_station_connections` 回裸 list 無原點標記，LLM 易誤讀（C6）| [graph/queries.py](databases/graph/queries.py) | graph（Chien）| 🟡 低（優化）| 包成 `{"station_id":..., "connections":[...]}` |
| 8 | `query_delay_ripple` 起點以 hops 2 自我重現；`query_alternative_routes` 可變長度允許起點折返 | databases/graph/queries.py | graph（Chien）| 🟡 低 | 排除起點 / 加節點唯一性；TA 檢核點皆滿足，留待 Task 6 |

> #1–#6 皆非 Chien 的 graph 責任區；#7/#8 為 graph 的可選優化（非阻斷、TA 檢核皆過）。

---

## 本次測試衍生的設定／文件變更

1. **`.env`**：`LLM_PROVIDER=gemini`、`GEMINI_CHAT_MODEL=gemini-3.1-flash-lite`、`GEMINI_EMBED_MODEL=gemini-embedding-001`。（不進 git）
2. **`databases/relational/schema.sql`**（⚠️ 共用檔）：`vector(768)→vector(3072)`、註解 3072 維無法建的 HNSW 索引。→ **commit 前需與團隊討論**（用 Ollama 的隊友為 768 維會衝突）。
3. **[Chien_本地測試指南.md](Chien/Chien_本地測試指南.md)**：新增 Docker/Gemini 章節；修正 C3 測試問句（NR01→NR05 避 NR03 → MS01→MS09 避 MS07）。
4. 上述問題清單 #1–#6 屬他人共用檔，本次**僅記錄、未改碼**，留待團隊決定。