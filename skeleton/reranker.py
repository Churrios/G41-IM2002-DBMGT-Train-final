"""
TransitFlow — Cross-Encoder Reranker
=====================================
使用 sentence-transformers CrossEncoder 對向量搜尋結果做精確重排序。

用途：
  - 向量搜尋（ANN）速度快但精度有限；reranker 對 top-K 結果做精確比對
  - 模型為 lazy load，首次呼叫時載入，後續複用同一實例

跨檔案互動：
  - 被 skeleton/rag.py → search_with_rerank() 呼叫
  - 不直接依賴任何其他模組

使用方式：
  from skeleton.reranker import rerank
  ranked = rerank(query, passages)
"""

import logging

try:
    from sentence_transformers import CrossEncoder
    HAS_SENTENCE_TRANSFORMERS = True
except ImportError:
    HAS_SENTENCE_TRANSFORMERS = False
    logging.warning("sentence-transformers is not installed. Reranking will be disabled.")

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
        
    if not HAS_SENTENCE_TRANSFORMERS:
        # 優雅降級：直接回傳初步結果的前 top_k 筆
        return results[:top_k]

    model = _get_model()
    pairs = [(query_text, r["content"]) for r in results]
    scores = model.predict(pairs)
    ranked = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)
    out_results = []
    for score, r in ranked[:top_k]:
        new_r = r.copy()
        new_r["rerank_score"] = float(score)
        out_results.append(new_r)
    return out_results
