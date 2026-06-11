# TransitFlow 團隊分工規劃 (3人組)

本文件將 `README.zh-TW.md` 中所描述的 TransitFlow 專案任務，依據技術模組與關注點分離原則，劃分為三位團隊成員（成員 A、成員 B、成員 C）的工作職責與協作流程。

---

## 任務架構總覽

TransitFlow 的資料庫與 AI 架構由三個核心部分組成：
1. **關聯式資料庫 (PostgreSQL)**：負責結構化資料（車站、時刻表、訂位、付款等）。
2. **圖形資料庫 (Neo4j)**：負責鐵路運輸網路拓撲與路線計算。
3. **向量資料庫 (pgvector) 與 AI Agent**：負責政策 RAG 相似度檢索、LLM 工具路由與網頁 UI。

---

## 成員職責分工

### 🧑‍💻 成員 A：關聯式資料庫開發者 (Relational DB Specialist)
* **核心職責**：負責結構化資料的儲存設計、PostgreSQL 表格 Schema 建置與所有關聯式 SQL 查詢邏輯的實作。
* **要編輯與維護的檔案**：
  * [databases/relational/schema.sql](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/databases/relational/schema.sql) —— 設計並撰寫 Table DDL 定義。
  * [skeleton/seed_postgres.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/skeleton/seed_postgres.py) —— 實作 `seed_*` 系列函式，將 `train-mock-data/` 下的 JSON 檔案載入 PostgreSQL 中。
  * [databases/relational/queries.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/databases/relational/queries.py) —— 實作 13 個 SQL 查詢與寫入函式：
    * **唯讀查詢**：國鐵可用性查詢、國鐵票價計算、地鐵時刻表查詢、地鐵票價計算、剩餘座位查詢、使用者帳號資料、使用者所有訂票歷史、付款資訊查詢。
    * **寫入/交易操作**：執行訂票、取消訂票（需包含退費計算邏輯）。
    * **使用者與認證**：使用者註冊、使用者登入、取得密保問題、驗證密保答案、更新密碼。
* **開發與測試指令**：
  ```bash
  # 每次修改 schema.sql 後，重置並重啟 PostgreSQL
  docker compose down -v && docker compose up -d postgres pgadmin
  
  # 執行 Seeding 腳本導入 mock data
  python skeleton/seed_postgres.py
  ```

---

### 🧑‍💻 成員 B：圖形資料庫開發者 (Graph DB Specialist)
* **核心職責**：負責地鐵與國鐵運輸網路的拓撲設計，將鐵路路線與車站間的關係圖形化，並實作所有路徑規劃與延誤影響計算的 Cypher 查詢。
* **要編輯與維護的檔案**：
  * [databases/graph/seed.cypher](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/databases/graph/seed.cypher) —— 定義圖形拓撲結構，包含地鐵線路節點、國鐵車站節點，以及車站間的 directed edges (關係)。
  * [skeleton/seed_neo4j.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/skeleton/seed_neo4j.py) —— 實作 `seed()` 函式，讀取車站 JSON 並執行 Cypher MERGE 語句建置圖形資料。
  * [databases/graph/queries.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/databases/graph/queries.py) —— 實作 6 個 Cypher 查詢函式：
    * 尋找最短路徑：`query_shortest_route`
    * 尋找最便宜路徑：`query_cheapest_route`
    * 尋找替代路徑（避開故障車站）：`query_alternative_routes`
    * 跨系統轉乘路徑：`query_interchange_path`
    * 延誤波及範圍計算：`query_delay_ripple`
    * 列出車站的直接連接：`query_station_connections`
* **開發與測試指令**：
  ```bash
  # 執行 Neo4j Seeding 腳本建置圖形
  python skeleton/seed_neo4j.py
  ```
  * 可以使用瀏覽器開啟 [http://localhost:7475](http://localhost:7475) (neo4j / transitflow) 執行 `MATCH (n)-[r]->(m) RETURN n, r, m` 視覺化檢查圖形是否正確。

---

### 🧑‍💻 成員 C：向量檢索與 AI 系統整合工程師 (Vector & AI Integration Specialist)
* **核心職責**：負責退費與營運政策 RAG (檢裝增強生成) 的建立，AI Agent 工具的路由配置與註冊，以及 Gradio 網頁介面的調整、測試與協調。
* **要編輯與維護的檔案**：
  * [train-mock-data/](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/train-mock-data/) 下的政策 JSON 檔案 —— 擴充 `refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` 的內容，新增如遺失物、團體票、無障礙等政策。
  * [skeleton/seed_vectors.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/skeleton/seed_vectors.py) —— 負責執行向量 Seeding 腳本，呼叫 Embedding model 將政策 JSON 轉為向量並存入 PostgreSQL (pgvector)。
  * [skeleton/agent.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/skeleton/agent.py) —— 負責將成員 A 和成員 B 寫好的新 SQL/Cypher 查詢註冊為 AI 工具。包含：
    1. 匯入查詢函式。
    2. 在 `TOOLS` 清單加入 tool 定義以利 LLM 理解何時呼叫。
    3. 在 `TOOLS_SCHEMA` 中註冊 compact 簽名。
    4. 在 `_execute_tool` 中接上對應的 Python 呼叫邏輯。
  * [skeleton/ui.py](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/skeleton/ui.py) —— 修改 Gradio 聊天介面（例如自訂範例問題 `EXAMPLES`、調整 Markdown 說明文字等）。
* **開發與測試指令**：
  ```bash
  # 載入政策向量
  python skeleton/seed_vectors.py
  
  # 啟動 Gradio 聊天助理進行端到端測試
  python skeleton/ui.py
  ```

---

## 關鍵協作流程（黃金法則）

因為三個人的工作最終會被 AI Agent 整合，所以必須遵循以下協作規範：

1. **Schema-First 規則（最重要）**：
   * 在成員 A 與成員 B 動手寫任何 SQL 或 Cypher 查詢之前，**三人必須共同進行 Schema 設計會議**。
   * 同意 PostgreSQL 表格名稱、欄位名稱與 Neo4j 的 Node Label、Relationship 後，記錄在 [AI_SESSION_CONTEXT.zh-TW.md](file:///c:/Users/admin/OneDrive/%E6%A1%8C%E9%9D%A2/%E5%8A%9F%E8%AA%B2%E7%94%A8%E9%96%8B/AI_SESSION_CONTEXT.zh-TW.md) 中。
   * **絕不在沒有告知全隊的情況下修改 Schema 命名**，否則會破壞其他人的查詢功能。

2. **LLM 供應者的一致性**：
   * 三人必須協調好在 `.env` 中設定相同的 `LLM_PROVIDER` (Ollama 還是 Gemini)。
   * 如果使用 **Ollama**，`schema.sql` 中的 policy_documents embedding 欄位必須是 `vector(768)`。
   * 如果使用 **Gemini**，則必須修改為 `vector(3072)`。
   * 若切換了 LLM 供應者，所有人必須重新執行成員 C 負責的 `seed_vectors.py`，否則會發生 `embedding dimension mismatch` 錯誤。

3. **Git 工作串接流程**：
   * 成員 A/B 實作好新查詢函數後，發送 Pull Request (PR)。
   * 成員 C 在本地 `git pull` 取得最新函數，並在 `skeleton/agent.py` 中進行 AI 工具註冊。
   * 三人在每次 Git 更新後，若 `schema.sql` 有變動，應執行完整的重新同步流程：
     ```bash
     # 1. 重置 PostgreSQL
     docker compose down -v && docker compose up -d
     
     # 2. 三人依序執行各自負責的 Seed 腳本
     python skeleton/seed_postgres.py  (成員 A 的工作)
     python skeleton/seed_neo4j.py     (成員 B 的工作)
     python skeleton/seed_vectors.py   (成員 C 的工作)
     ```
