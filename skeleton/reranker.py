from sentence_transformers import CrossEncoder


_MODEL = None  # lazy load


def _get_model() -> CrossEncoder:
    global _MODEL
    if _MODEL is None:
        _MODEL = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _MODEL


def rerank(query_text: str, results: list[dict], top_k: int = 5) -> list[dict]:
    """
    對初步搜尋結果重排序。
    Args:
        query_text: 使用者原始問題（文字，非 embedding）
        results:    query_policy_vector_search 回傳的 list[dict]
        top_k:      最終回傳數量
    Returns:
        重排序後的 Top-k 結果
    """
    if not results:
        return []
    model = _get_model()
    pairs = [(query_text, r["content"]) for r in results]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)
    return [r for _, r in ranked[:top_k]]
