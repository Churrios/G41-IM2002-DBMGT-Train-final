import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skeleton.llm_provider import llm
from databases.relational.queries import query_policy_vector_search
from skeleton.rag import search_with_rerank

def main():
    # Cache verification
    print("--- Testing Embedding Cache ---")
    v1 = llm.embed("退票政策")
    v2 = llm.embed("退票政策")
    if v1 is v2:
        print("✅ Cache hit! v1 and v2 are the exact same object.")
    else:
        print("❌ Cache miss! Objects are different.")
        
    # Rerank verification
    print("\n--- Testing Reranking ---")
    query = "退票與延遲賠償"
    embedding = llm.embed(query)
    
    print("1. Raw Vector Search (Top 5):")
    raw_results = query_policy_vector_search(embedding, top_k=5)
    for i, r in enumerate(raw_results):
        print(f"  [{i+1}] {r['title']}")
        
    print("\n2. Reranked Search (Top 5):")
    reranked_results = search_with_rerank(embedding, query, top_k=5)
    for i, r in enumerate(reranked_results):
        print(f"  [{i+1}] {r['title']}")

if __name__ == "__main__":
    main()
