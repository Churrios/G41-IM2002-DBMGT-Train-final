# Side Note 2 — 正式環境中的向量資料庫最佳實務

> **免責聲明**
> 本文件是在多個 AI 工具協助下共同撰寫。雖然已盡力確保內容正確，但仍可能存在非預期錯誤。如果你發現任何錯誤，請[在 GitHub 提交 issue](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/issues)。

---

> **這是寫給誰的？**
> 這份 note 是給已經使用過本專案 pgvector RAG pipeline 的學生。
> 你已經看過 embeddings 如何儲存在 PostgreSQL 中，並用 cosine similarity 搜尋。現在讓我們看看正式環境系統如何在 scale 下正確處理這件事。

---

## 教學程式碼做了什麼？

TransitFlow 專案使用 **pgvector** extension，把政策文件以 embedding vectors 的形式存進 PostgreSQL。當使用者提問時，agent 會把問題轉成 embedding，接著執行這段 query：

```python
sql = """
    SELECT title, category, content,
           1 - (embedding <=> %s::vector) AS similarity
    FROM policy_documents
    WHERE 1 - (embedding <=> %s::vector) > %s
    ORDER BY embedding <=> %s::vector
    LIMIT %s
"""
```

`<=>` operator 是 pgvector 的 cosine distance。對小型 dataset 來說，這是完全有效的做法。但正式環境系統要處理數百萬份文件與每秒數千次 queries，需要用不同方式處理。

---

## 1. Dedicated Vector Databases vs pgvector

### 什麼是 vector database？

**Vector database** 是專門用來在 scale 下儲存、index 與搜尋 embedding vectors 的資料庫。PostgreSQL + pgvector 是在 relational database 上加入 vector capability；而專用 vector DB 則是從一開始就為這項任務設計。

### 什麼時候 pgvector 夠用？

pgvector 適合以下情況：
- 你的 document collection 很小（低於幾百萬）
- 你已經使用 PostgreSQL，不想再加入另一套系統
- 你需要在同一個 database 中結合 vector search 與 relational queries

這正是 TransitFlow 的情況，因此 pgvector 在這裡是正確工具。

### 什麼時候需要 dedicated vector database？

當你的 use case 包含：
- 數千萬 vectors
- Sub-millisecond search latency requirements
- 跨多台 servers 的 horizontal scaling
- 內建支援 real-time vector updates

最常用的 dedicated vector databases 包含：

| Database | 最適合 | Hosted option? |
|---|---|---|
| **Pinecone** | Fully managed、zero infrastructure | Yes（cloud-only） |
| **Qdrant** | High performance、open-source、Rust-based | Yes + self-host |
| **Weaviate** | Combined vector + keyword search、multi-modal | Yes + self-host |
| **ChromaDB** | Local development and prototyping | Self-host only |

```python
# 範例：使用 Qdrant 而不是 pgvector
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

client = QdrantClient(url="http://localhost:6333")

# 建立 collection（相當於 table）
client.create_collection(
    collection_name="policy_documents",
    vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
)

# Search
results = client.search(
    collection_name="policy_documents",
    query_vector=embedding,
    limit=5,
)
```

### 延伸閱讀
- [pgvector — GitHub repository and documentation](https://github.com/pgvector/pgvector)
- [Pinecone — official documentation](https://docs.pinecone.io/)
- [Qdrant — official documentation](https://qdrant.tech/documentation/)
- [Weaviate — official documentation](https://docs.weaviate.io/weaviate)
- [ChromaDB — official documentation](https://docs.trychroma.com/)

---

## 2. Indexing：沒有 index 時搜尋為什麼會很慢

### 教學程式碼的問題

教學程式碼沒有在 `embedding` column 上做任何 **indexing**。每次搜尋都會執行 full table scan，也就是把 query vector 和 table 中每一列逐一比較。這稱為 **exact nearest neighbour**（exact NN）search。

對 100 份政策文件來說，這很快。對 1000 萬份文件來說，每次 query 會花好幾秒。

### 正式環境解法：Approximate Nearest Neighbour（ANN）indexing

ANN indexes 用極小的準確率犧牲，換取巨大的速度提升。pgvector（以及大多數 vector databases）最常使用的兩種演算法是：

#### HNSW — Hierarchical Navigable Small World

這是大多數 applications 的預設與最佳選擇。它會在 vectors 上建立 multi-layer graph structure。即使 collection 很大，search 仍然很快。

```sql
-- 在 PostgreSQL + pgvector 的 embedding column 上新增 HNSW index
CREATE INDEX ON policy_documents
USING hnsw (embedding vector_cosine_ops);
```

#### IVFFlat — Inverted File with Flat quantisation

把 vectors 分成 clusters（lists），只在最相關的 clusters 中搜尋。它比 HNSW 建立更快，但準確率稍低。

```sql
CREATE INDEX ON policy_documents
USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

**經驗法則：** 除非你的 collection 非常大且 memory constraints 很緊，否則使用 HNSW。

### 延伸閱讀
- [pgvector HNSW and IVFFlat indexing（GitHub README）](https://github.com/pgvector/pgvector)

---

## 3. 選擇 Embedding Model

### 教學程式碼怎麼做

教學程式碼會在 database layer 外部產生 embeddings（透過 `skeleton/llm_provider.py` 中的 `llm.embed()`），並把產生出的 float list 傳進 query。這是正確的，model 應該存在於 database layer 外部。

### 正式環境選 model 時什麼最重要

在正式環境中，embedding model 的選擇會影響 accuracy、speed 與 cost。主要選項是：

#### Option A — Hosted API（OpenAI、Cohere 等）
你把 text 送到外部 API，並取得 embedding 回來。不需要 GPU，容易使用，但會按 token 計費，而且增加 network latency。

```python
import openai

response = openai.embeddings.create(
    model="text-embedding-3-small",
    input="What is the delay repay policy?"
)
embedding = response.data[0].embedding  # 1536 個 floats 的 list
```

#### Option B — Local model（Sentence Transformers）
你在自己的機器或 server 上執行 open-source model。沒有 API cost，完全 offline，但需要更多 compute。

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embedding = model.encode("What is the delay repay policy?")
```

**重要：** 你在 index time 用來 *embed documents* 的模型，**必須和** search time 用來 embed queries 的模型相同。混用模型會產生沒有意義的結果。

### 延伸閱讀
- [Sentence Transformers — documentation and pretrained models](https://www.sbert.net/)
- [HuggingFace NLP Course — Semantic Search with Embeddings](https://huggingface.co/learn/nlp-course/chapter5/6)

---

## 4. Chunking：如何切分文件很重要

### 問題

教學程式碼把每份政策文件儲存成一個大型 text block。如果使用者詢問 minimum fare rule，整份 railcard guide（500+ words）會以一個 chunk 回傳。LLM 接著必須讀完整份內容，才能找出那一句相關文字。

在正式環境中，你會先把 documents **chunk** 成較小片段，再對它們做 embedding。每個 chunk 涵蓋一個連貫概念。

### 常見 chunking strategies

#### Fixed-size chunking
每 N 個 characters 或 tokens 切分 text，並保留少量 overlap 來維持 boundaries 之間的 context。

```python
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap   # overlap 確保 boundary 處不會遺失 context
    return chunks
```

#### Recursive / semantic chunking
先依自然邊界切分（paragraphs → sentences → words）。只有當 chunk 仍然太大時，才繼續切得更小。這會比 fixed-size splitting 產生更有意義的 chunks。

#### Chunk size 經驗法則

| Use case | Recommended chunk size |
|---|---|
| Short factual Q&A | 100–200 tokens |
| Policy / legal documents | 300–500 tokens |
| Long-form content | 500–1000 tokens |

### 延伸閱讀
- [LangChain — Build a RAG application（official tutorial）](https://docs.langchain.com/oss/python/langchain/rag)

---

## 5. Metadata Filtering

### 教學程式碼怎麼做

教學程式碼會搜尋所有 policy documents，不管 category。若使用者詢問 refund，search 可能回傳 accessibility guide，只因為它剛好和 query vector 相似。

### 正式環境解法：先用 metadata pre-filter

大多數 production vector databases 支援 **metadata filters**。你可以在執行 vector similarity comparison 前，先把搜尋範圍縮小到特定 category、date range 或其他任何欄位。

```python
# 範例：使用 Qdrant 時，只搜尋 "refund" category
from qdrant_client.models import Filter, FieldCondition, MatchValue

results = client.search(
    collection_name="policy_documents",
    query_vector=embedding,
    query_filter=Filter(
        must=[FieldCondition(key="category", match=MatchValue(value="refund"))]
    ),
    limit=5,
)
```

在 pgvector 中，你可以在 vector comparison 前加入簡單的 `WHERE` clause 達成：

```sql
SELECT title, content, 1 - (embedding <=> %s::vector) AS similarity
FROM policy_documents
WHERE category = 'refund'                           -- 先做 metadata filter
  AND 1 - (embedding <=> %s::vector) > %s
ORDER BY embedding <=> %s::vector
LIMIT %s
```

---

## 6. Reranking

### 什麼是 reranking？

Vector search 回傳 top K results 後，**reranker** 會使用更準確但較慢的 model，也就是 **cross-encoder**，對這些結果重新評分。初始 vector search 很快，並且撒一張大網。Reranker 接著從那張網中挑出最佳結果。

可以把它想成兩個階段：
1. **Vector search** — 快速取回 top 20 candidates（fast、approximate）
2. **Reranker** — 逐一將每個 candidate 與 query 一起讀取並重新評分 20 筆，最後回傳最佳 5 筆（slow、accurate）

```python
import cohere

co = cohere.Client("your-api-key")

# Step 1：用 vector search 取回 candidates（top 20）
candidates = query_policy_vector_search(embedding, top_k=20)

# Step 2：根據原始問題 rerank candidates
reranked = co.rerank(
    model="rerank-english-v3.0",
    query="What is the delay repay policy?",
    documents=[c["content"] for c in candidates],
    top_n=5,
)
```

Reranking 可以大幅改善 long-form questions 的結果品質，或改善初始 vector search 回傳語意相似但其實不相關的結果。

### 延伸閱讀
- [Cohere Rerank — API reference](https://docs.cohere.com/reference/rerank)

---

## 7. Embedding Cache

### 問題

在教學程式碼中，每次 agent 回答問題時，都會重新 embed query。如果同一個問題被問兩次，model 就會執行兩次，浪費時間與 API cost。

### 正式環境解法：cache embeddings

對你預期會重複出現的 queries，可以把 embedding cache 在 Redis 或簡單的 in-memory store：

```python
import hashlib, json
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_cached_embedding(text: str) -> tuple[float, ...]:
    embedding = llm.embed(text)           # 只有第一次出現時才呼叫 model
    return tuple(embedding)               # tuples 可以 hash，lists 不行
```

在 production 中，Redis 比 `lru_cache` 更推薦，因為它能在 server restarts 後保留資料，而且可由多個 processes 共享。

---

## Summary

| Topic | Teaching Code | Production Approach |
|---|---|---|
| **Vector storage** | PostgreSQL 中的 pgvector | Dedicated DB（Qdrant、Pinecone、Weaviate）或帶 HNSW index 的 pgvector |
| **Search type** | Full table scan（exact NN） | ANN index（HNSW 或 IVFFlat） |
| **Document size** | 每份 document 一個 chunk | 每份 document 多個較小 chunks |
| **Filtering** | 只有 similarity threshold | Metadata filter + similarity threshold |
| **Result quality** | Top K raw results | 由 cross-encoder rerank 後的 Top K |
| **Embedding compute** | 每次 query 重新 embed | Cached（lru_cache 或 Redis） |

---

## Recommended Starting Points

| Resource | 你會學到什麼 |
|---|---|
| [pgvector GitHub](https://github.com/pgvector/pgvector) | PostgreSQL 的 HNSW/IVFFlat indexing |
| [Sentence Transformers docs](https://www.sbert.net/) | 在本機執行 embedding models |
| [HuggingFace NLP Course — Semantic Search](https://huggingface.co/learn/nlp-course/chapter5/6) | End-to-end embedding + search tutorial |
| [LangChain RAG tutorial](https://docs.langchain.com/oss/python/langchain/rag) | 包含 chunking 與 retrieval 的完整 RAG pipeline |
| [Qdrant documentation](https://qdrant.tech/documentation/) | 從零開始使用 purpose-built vector database |
| [Cohere Rerank API](https://docs.cohere.com/reference/rerank) | 用 reranking 改善 RAG result quality |
