# Section 4: Vector / RAG Design

## 4.1 Embedding 對象與 Cosine Similarity
在本系統中，被轉換為 embedding 的對象是**政策文件 (Policy Documents)**，包含各類票務與退費規則。

在比對使用者查詢與政策文件時，**Cosine similarity** 非常適合用來評估語意相似度，因為它是 **magnitude-independent**（不受向量長度影響）。它不是去測量兩個點之間的絕對距離，而是**測量 embedding space 中的方向相似度**。這代表即使文本長度或詞彙頻率不同，只要兩個文件表達的語意方向一致，就能獲得很高的相似度分數。

## 4.2 Retrieval-Augmented Generation (RAG) Pipeline
我們的 RAG pipeline 完整運作包含以下四個階段，確保系統能給出有憑有據的回答：
1. **Query Embedding**：當使用者輸入自然語言的問題（例如問退票規則）時，系統首先會透過設定好的 LLM embedding 模型（預設使用 Ollama 的 `nomic-embed-text`），將這段文字轉換成一個高維度（768維）的數學向量。
2. **Similarity Search (pgvector)**：接著，將這個向量化的 query 與 PostgreSQL 資料庫中 `policy_documents` 資料表內預先計算好的文件 embedding 進行比對。這裡會使用 `pgvector` 的 `<=>` 運算子來執行 cosine similarity 搜尋，找出在向量空間中最接近的 nearest neighbours，並設定適當的 threshold（例如 0.5）來過濾無關文件。
3. **Retrieved Documents**：資料庫會依據 similarity scores 降冪排序，回傳 top-K 個最相關的 document chunks（如退款政策段落）。這些 chunks 包含了回答使用者問題所需的實際事實、條文與知識。
4. **LLM Prompt and Answer**：最後，系統會將這些擷取出來的文本 chunks，連同使用者的原始問題，一併注入到 LLM (例如 `llama3.2:1b` 或 Gemini) 的 Prompt context window 內。LLM 的 System Prompt 會嚴格指示它「只能根據提供的 context 來生成最終回答」，從而確保回應是有實體文件根據的，有效防止 Hallucination（幻覺）。

## 4.3 Embedding Dimensions and Seeding
不同的 LLM 供應商所產生的 embeddings 會有不同的維度大小：
- **Ollama**：使用 **768 維 (dimensions)**。
- **Gemini**：使用 **3072 維 (dimensions)**。

因為資料庫中的 vector index 在初始 seeding 過程建立時，就會嚴格綁定該 dimension 大小。所以如果在 **seeding 後切換 provider，會造成 dimension mismatch，導致 index 失效**。因此，如果改變了 LLM provider，就**必須重新 seed** vector database，以確保所有 document embeddings 的維度大小符合新的設定。
