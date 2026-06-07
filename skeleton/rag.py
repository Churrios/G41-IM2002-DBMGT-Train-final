"""
TransitFlow — RAG (Retrieval-Augmented Generation) Pipeline
============================================================
負責將使用者的自然語言查詢轉換為向量搜尋，並對結果重新排序。

用途：
  - 接收查詢字串，從 PostgreSQL pgvector 取回相關政策文件段落
  - 透過 reranker 對結果做二次排序，提升相關性

跨檔案互動：
  - 呼叫 databases/relational/queries.py → query_policy_vector_search()
  - 呼叫 skeleton/reranker.py → rerank()
  - 被 skeleton/agent.py → _execute_tool() 呼叫（search_policy tool）

使用方式：
  from skeleton.rag import search_with_rerank
  results = search_with_rerank("cancellation policy", top_k=5)
"""

from databases.relational.queries import query_policy_vector_search
from skeleton.reranker import rerank


def search_with_rerank(
    embedding: list[float],
    query_text: str,
    category: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """
    向量搜尋 + reranking 的完整流程。
    Args:
        embedding:  llm.embed(query_text) 的結果
        query_text: 使用者原始問題（給 reranker 用）
        category:   可選，限制搜尋的文件類別
        top_k:      最終回傳數量
    Returns:
        重排序後的 Top-k 政策文件
    """
    # 先拉 Top 20
    results = query_policy_vector_search(embedding, top_k=20)


    # Python 端 category 過濾（不動 SQL）
    if category:
        results = [r for r in results if r.get("category") == category]


    # Reranking
    return rerank(query_text, results, top_k=top_k)
