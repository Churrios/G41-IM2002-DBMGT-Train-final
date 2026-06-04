import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from skeleton.llm_provider import llm
from databases.relational.queries import query_policy_vector_search
from skeleton.rag import search_with_rerank

def main():
    print("\n========================================================")
    print(" 🚀 TRANSITFLOW ADVANCED RAG (CROSS-ENCODER) DEMO 🚀 ")
    print("========================================================\n")

    # Cache verification
    print("--- [Part 1] Testing Embedding Cache ---")
    v1 = llm.embed("退票政策")
    v2 = llm.embed("退票政策")
    if v1 is v2:
        print("✅ Cache hit! v1 and v2 are exactly the same object in memory.\n")
    else:
        print("❌ Cache miss! Objects are different.\n")
        
    # Rerank verification
    print("--- [Part 2] Testing Reranking (Live DB Query) ---")
    query = "退票與延遲賠償"
    print(f"User Query: '{query}'\n")
    
    try:
        embedding = llm.embed(query)
        
        print("🔍 1. Raw Vector Search (Top 5 using Cosine Similarity):")
        raw_results = query_policy_vector_search(embedding, top_k=5)
        if not raw_results:
            print("   ⚠️ No documents found. (Are vectors seeded?)")
        else:
            for i, r in enumerate(raw_results):
                sim = r.get('similarity', 0.0)
                print(f"  [{i+1}] (Sim: {sim:.3f}) {r['title']}")
                
        print("\n✨ 2. Reranked Search (Top 5 using Cross-Encoder):")
        reranked_results = search_with_rerank(embedding, query, top_k=5)
        if not reranked_results:
            print("   ⚠️ No documents found.")
        else:
            for i, r in enumerate(reranked_results):
                r_score = r.get('rerank_score', 0.0)
                print(f"  [{i+1}] (Rerank Score: {r_score:.3f}) {r['title']}")
                
        print("\n💡 Observe how the Cross-Encoder reordered the top results based on deeper semantic meaning!")
        
    except Exception as e:
        print(f"❌ Error during search: {e}")
        print("Make sure you have seeded the vectors (python skeleton/seed_vectors.py) and Ollama/Gemini is running.")

if __name__ == "__main__":
    main()
