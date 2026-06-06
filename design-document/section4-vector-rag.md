# Section 4: Vector / RAG Design

## 4.1 Cosine Similarity
Cosine similarity 非常適合用來評估語意相似度，因為它是 **magnitude-independent**（不受向量長度影響）。它不是去測量兩個點之間的絕對距離，而是**測量 embedding space 中的方向相似度**。這代表即使文本長度或詞彙頻率不同，只要兩個文件表達的語意方向一致，就能獲得很高的相似度分數。

## 4.2 Retrieval-Augmented Generation (RAG) Pipeline
我們的 RAG pipeline 完整運作包含以下四個階段：
1. **Query Embedding**：當使用者輸入自然語言的問題時，系統首先會透過設定好的 LLM embedding 模型，將這段文字 query 轉換成一個高維度的數學向量。
2. **Similarity Search (pgvector)**：接著，將這個向量化的 query 與 PostgreSQL 資料庫中預先 embedding 好的政策文件 chunk 進行比對。這裡會使用 `pgvector` 擴充功能執行 cosine similarity 搜尋，找出在向量空間中最接近的 nearest neighbours。
3. **Retrieved Documents**：資料庫會回傳 top-K 個語意最相關的 document chunks 以及它們的 similarity scores。這些 chunks 包含了回答使用者問題所需的實際事實與知識。
4. **LLM Prompt and Answer**：最後，系統會將這些擷取出來的文本 chunks 注入到 LLM prompt 的 context window 內。LLM 會被指示只能根據這些提供的 context 來生成最終的回答，從而確保回應是有根據的，並有效防止 hallucination（幻覺）。

## 4.3 Embedding Dimensions and Seeding
不同的 LLM 供應商所產生的 embeddings 會有不同的維度大小：
- **Ollama**：使用 **768 維 (dimensions)**。
- **Gemini**：使用 **3072 維 (dimensions)**。

因為資料庫中的 vector index 在初始 seeding 過程建立時，就會嚴格綁定該 dimension 大小。所以如果在 **seeding 後切換 provider，會造成 dimension mismatch，導致 index 失效**。因此，如果改變了 LLM provider，就**必須重新 seed** vector database，以確保所有 document embeddings 的維度大小符合新的設定。
