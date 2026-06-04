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
