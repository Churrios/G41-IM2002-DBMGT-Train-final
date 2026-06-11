# Local Testing 測試流程紀錄（Chien）

> 測試日期：2026-06-09
> 環境：本機 Windows 10 Pro（MSI GL65 Leopard 10SFK, i7-10750H, 16GB RAM）/ PowerShell + Docker Desktop(WSL2)
> LLM：先 **Ollama (llama3.2:1b + nomic-embed-text)**，後 **Gemini (gemini-3.1-flash-lite + gemini-embedding-001, 3072 維)**
> 測試者：黃謙儒（Chien，Graph DB Engineer）
> 性質：這份是「**怎麼一步一步測的**」流程＋踩坑紀錄；最終結果與問題彙整見 [local-testing-results-chien.md](local-testing-results-chien.md)。

---

## 一、環境建置紀錄（首次在本機從零建立）

| 步驟 | 指令 / 動作 | 結果 | 踩到的坑與解法 |
|------|------------|------|----------------|
| 裝 Docker Desktop | `wsl --install --no-distribution` → 重開機 → 裝 Docker Desktop（WSL2 後端）| ✅ | 首次啟用 WSL2 一定要重開機；安裝完 `docker --version` 29.5.2 |
| 建立 venv | `python -m venv .venv --prompt transitflow` | ✅ | **中文資料夾名**會讓預設 `activate.ps1` 把 prompt 字串嵌壞 → 必須用 `--prompt` 指定純英文；Python 來自 Anaconda(`C:\Users\K\anaconda3`) |
| 啟用 venv | `.venv\Scripts\Activate.ps1` | ✅ | 報 `running scripts is disabled` → `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser` |
| 裝套件 | `pip install -r requirements.txt` | ✅ | 無紅字 |
| 建 .env | `Copy-Item .env.example .env` | ✅ | 預設 Ollama，先不改 |
| 裝 Ollama | `irm https://ollama.com/install.ps1 \| iex` | ✅ | 0.30.6；裝完當前視窗抓不到 `ollama`，要**開新視窗**或 `$env:PATH += ";...\Programs\Ollama"` |
| 拉模型 | `ollama pull llama3.2:1b` / `ollama pull nomic-embed-text` | ✅ | 1.3GB + 274MB |
| 起容器 | `docker compose up -d` | ⚠️→✅ | **Postgres 撞 port 5433**（WSL2 後 winnat 保留埠段）`bind: forbidden` → 系統管理員 `net stop winnat; net start winnat` 後重起即可 |
| 等 healthy | `docker compose ps` | ✅ | postgres / neo4j 皆 healthy |

> ⚠️ Docker Desktop 重啟後 winnat 會再次保留 5433，可能要再 restart 一次 winnat；一勞永逸可 `netsh int ipv4 add excludedportrange protocol=tcp startport=5433 numberofports=1`（系統管理員）。

---

## 二、Seeding 紀錄

| Seed | 指令 | 結果 |
|------|------|------|
| PostgreSQL | `python skeleton/seed_postgres.py` | ✅ 20 users / 20 metro / 10 rail / 8+50 metro sched(+stops) / 8+36 rail sched(+stops) / 72 seat layouts / 20 bookings / 24 travel / 40 payments / 30 feedback |
| Vectors | `python skeleton/seed_vectors.py` | ✅ 13 policy docs → **101 chunks**（Ollama 768 維 / Gemini 輪換後 3072 維） |
| Neo4j | `python skeleton/seed_neo4j.py` | ✅ **20 MetroStation, 10 NationalRailStation, 42 METRO_LINK, 18 RAIL_LINK, 6 INTERCHANGE_TO** |

**Neo4j Browser 體檢**（http://localhost:7475，`bolt://localhost:7688`，neo4j/transitflow）：
- `MATCH (n) RETURN labels(n)[0], count(*)` → 節點 30（20+10）✅
- `MATCH ()-[r]->() RETURN type(r), count(*)` → 邊 66（42/18/6）✅

---

## 三、測試帳號

- Email：`alice.tan@email.com`
- Password：`alice1990`
- 對應 `user_id = RU01`（Alice Tan）

---

## 四、Round 1 — Ollama (llama3.2:1b) 測試流程

> 方法：UI（http://localhost:7860）打開 debug panel 看實際工具呼叫；同時用 `.venv/Scripts/python.exe -c "..."` 直接呼叫 graph 函式對照。

### 直接呼叫驗證（繞過 LLM，確認函式本身）
逐一呼叫六支 graph 函式，輸出全部正確：
- `query_shortest_route('MS01','MS14')` → total_time_min=**16**，legs 2+2+4+4+4=16 ✅
- `query_cheapest_route('NR01','NR05','standard')` → **86.0**；`'first'` → **138.0**（fare_class 真的切換）✅
- `query_alternative_routes('NR01','NR05','NR03')` → **`[]`**（國鐵 NR1 線性鏈，避 NR03 後不連通，正確）
- `query_alternative_routes('MS01','MS09','MS07')` → **3 條，皆不含 MS07** ✅
- `query_interchange_path('MS01','NR05')` → total=**42**，MS07→NR03 換乘 ✅
- `query_delay_ripple('MS05',2)` → 起點+鄰域；`hops=0` → 只回 MS05 ✅
- `query_station_connections('MS01')` → 4 鄰站依時間排序 ✅

### UI（Ollama）逐題
| 問句 | 觀察 |
|------|------|
| `What is the fastest metro route from MS01 to MS14?` | LLM 帶 `optimise_by=cost`（應 time）、文字說「2 分鐘」（應 16）。函式資料正確。 |
| `How do I get from Central Square (MS01) to Stonehaven (NR05)?` | **秒回**、正確跨網、42 分。✅ |
| `If Old Town station (NR03) is closed, ...NR01 to NR05?` | LLM 把 **tool schema 當參數**傳、fallback 到 find_route。函式未被正確呼叫。 |
| `If MS05 is delayed, which stations are affected?` | LLM 同樣把 schema 當參數 → `KeyError 'station_id'`。函式未被呼叫。 |

**Round 1 結論**：6 函式直接呼叫全對；llama3.2:1b 的 tool-use 很不穩（schema 當參數、選錯 optimise、文字算錯），四題只有 C4 在 UI 上順利。**過程中發現指南 C3 問句（NR01→NR05 避 NR03）永遠回空、測不到去重，改用 MS01→MS09 避 MS07。**

---

## 五、Gemini 遷移流程（過程曲折，逐步記錄）

### 5.1 API key
- 申請：`https://aistudio.google.com/apikey`。**新版 AI Studio key 是 `AQ.Ab8...` 格式**（不是舊的 `AIzaSy...`，一度誤判格式錯）。
- key 與 **Antigravity（同帳號的 Gemini agent）共用配額**，是後面一直 429 的主因。

### 5.2 配額卡關（按「模型」分桶，逐一試出可用模型）
| 模型 | 結果 | RPD（每日）|
|------|------|-----------|
| `gemini-2.0-flash-lite`（config 預設）| ❌ 429 PerDay | 用光 |
| `gemini-2.5-flash-lite` | 一開始可，測幾題後也 429 | 20/20 用光 |
| `gemini-2.5-flash` | 可，但配額小 | 18 餘 |
| **`gemini-3.1-flash-lite`** | ✅ **最終採用** | **0/500（最多）** |
| `gemini-embedding-001`（embed）| ✅ 全程可用 | 額度獨立 |

→ 在 `.env` 設 `GEMINI_CHAT_MODEL=gemini-3.1-flash-lite`、`GEMINI_EMBED_MODEL=gemini-embedding-001`。

### 5.3 schema 768 → 3072（踩到 pgvector 索引上限）
1. 改 `databases/relational/schema.sql`：`vector(768)` → `vector(3072)`。
2. `docker compose down -v && up -d` 後 **Postgres 啟動失敗退出**：
   `ERROR: column cannot have more than 2000 dimensions for hnsw index`。
3. **pgvector HNSW/IVFFlat 上限 2000 維**，Gemini 3072 維超過 → 把該 `CREATE INDEX ... USING hnsw` **註解掉**（101 筆精確搜尋本就秒回）。
4. 再 `down -v && up -d`，Postgres healthy。

### 5.4 重灌 + 端到端驗證
- `seed_postgres` / `seed_neo4j` 正常；`seed_vectors` 走 Gemini，**101 chunks、無 429、無 dimension mismatch**。
- 驗證：`llm.embed(...)` 回 **3072 維**；`query_policy_vector_search` 對「delay refund」問句正確命中 *Delay Compensation* 文件。

> 過程小坑：透過 Bash 管線跑 seed_vectors 時 cp950 無法輸出 emoji（📄）中斷 → 設 `PYTHONUTF8=1 PYTHONIOENCODING=utf-8` 即可（純輸出編碼問題，非程式錯）。

---

## 六、Round 2 — Gemini (gemini-3.1-flash-lite) 測試流程

> UI 重啟後啟動訊息：`[LLM] Chat: Gemini (gemini-3.1-flash-lite) | Embed: Gemini (gemini-embedding-001)`。一題一題貼、看 debug panel。

### Section C（graph，六題）
| 問句 | 觀察 |
|------|------|
| `What is the fastest metro route from MS01 to MS14?` | ✅ `optimise_by=time`、total 16、五段全對、文字也算對 |
| `What is the cheapest national rail route from NR01 to NR05?` | ✅ `optimise_by=cost`、$86、四段票價對 |
| `If Old Town (MS07) is closed, what alternative metro routes exist from MS01 to MS09?` | LLM **選對** `find_alternative_routes`（參數全對），但 **agent.py fallback 蓋掉** → `find_route(MS07,MS07)` 退化結果 |
| `How do I get from Central Square (MS01) to Stonehaven (NR05)?` | ✅ 42 分、3–4 秒回 |
| `If MS05 is delayed, which stations are affected?` | ✅ 正確帶 `station_id`、無 Cypher 錯 |
| `Which stations directly connect to Central Square (MS01)?` | ✅ 工具/函式對；但 LLM 把「MS01 的 4 鄰站」誤讀成「那 4 站各自的連線」（裸 list 缺原點標記）|

### Section B（relational，十題；B6–B10 已登入 alice）
| 問句 | 觀察 |
|------|------|
| `What national rail trains run from NR01 to NR05 on 2026-06-10?` | ✅ 2 班次、座位數對 |
| `Which metro schedules serve both MS01 and MS09?` | ✅ MS_SCH03、stops_in_order 對 |
| `What is the standard class fare for schedule NR_SCH01 travelling 4 stops?` | ✅ $8.50（傳 int 4）|
| `What is the metro fare from MS01 to MS09?` | ❌ **crash**：`can't multiply sequence by non-int of type 'float'`（LLM 傳 `stops_travelled="4"` 字串）|
| `Which standard class seats are available on schedule NR_SCH01 on 2026-06-10?` | ✅ 12 席 B01–B12 |
| `Show my user profile details` | LLM 沒選工具 → fallback 規則 #3（"show my"）搶成 `get_user_bookings`；profile 工具沒被叫 |
| （承上，意外測到）| `get_user_bookings` ✅ 回 BK001/BK020/MT009（乾淨 seed）|
| `What is the payment information for booking BK001?` | ❌ LLM 叫 `search_policy`；查 agent.py 發現 **payment 根本沒註冊成工具** |
| `Book seat B04 ... NR_SCH01 ... NR01 to NR05 on 2026-06-20` | ✅ `make_booking` 六參數齊、建立 BK-COI6Y4 |
| `Cancel my booking BK-COI6Y4` | ❌ **crash（Windows）**：`'cp950' codec can't decode byte 0xe2`（execute_cancellation 的 open() 漏 utf-8）|

---

## 七、待測 / 未涵蓋

| 項目 | 狀態 |
|------|------|
| RAG `search_policy`（bicycle / delay 補償）| ✅ **已測**：`pip install sentence-transformers`(5.5.1) 後兩題皆通過（檢索+rerank 正確；首次 reranker CPU 冷啟動 ~60s；delay 題首次 LLM 拒答、重試正常）。詳見 results 檔 RAG 段。 |
| Auth register / login | ✅ **已測**：login(alice) 成功；register 新帳號成功寫入（RU3AF9BM, bcrypt, is_active）。一次「查無 email」係輸入 typo（註冊存 `test@gmaill.com` 兩個 L、登入打一個 L），非 bug。 |
| Section B 直接呼叫補測（B4/B6/B8/B10 函式層在傳對型別/Mac 下的行為）| 多數已由蔡 06-05 直接呼叫驗證；本次以 UI 行為為主 |
| Gemini 重測 B4/B6/B8（修工具/型別後）| 視團隊是否修 agent.py / queries.py |

---

## 八、已知問題 / 注意事項（彙整見 results 檔的「問題清單」）

1. **graph 函式 6 支全部正確**（兩 provider + 直接呼叫三方交叉驗證）。殘留問題都在 relational / agent / vector 層。
2. **agent.py fallback 會蓋掉正確的工具選擇**（C3、B6 都中招）——本為補救 llama3.2:1b 而寫，遇到強模型反成阻礙。
3. **relational 兩個會 crash 的 bug**：B4 `stops_travelled` 未轉型（string×float）、B10 `execute_cancellation` open() 漏 `encoding='utf-8'`（Windows）。
4. **B8 付款查詢函式沒接進 agent 工具**——助理無法觸及。
5. **requirements.txt 漏 `sentence-transformers`** → RAG 全炸。
6. **schema HNSW 索引 2000 維上限** vs Gemini 3072 維。
7. **Gemini 配額按模型分桶**，且與 Antigravity 共用——用 `gemini-3.1-flash-lite`（500 RPD）最穩。
8. graph 已知輕微限制（非阻斷）：`delay_ripple` 起點以 hops 2 自我重現、`alternative_routes` 可變長度允許起點折返。