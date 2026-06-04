"""
TransitFlow — pgvector Policy Document Seeder
Run once after starting Docker:
    python skeleton/seed_vectors.py

This script:
  1. Loads policy documents directly from train-mock-data/ JSON files
  2. Embeds each document using the configured LLM provider
  3. Stores the text + vector in PostgreSQL (policy_documents table)

Note: Gemini free tier has ~1500 requests/minute — this script makes ~13 calls, well within limits.

Students: To extend the assistant's knowledge, add entries to the JSON files in
train-mock-data/ and re-run this script.
"""

import json
import os
import sys
import time
import psycopg2
from functools import lru_cache

sys.path.insert(0, ".")

from skeleton.llm_provider import llm
from databases.relational.queries import store_policy_document

@lru_cache(maxsize=1000)
def _cached_embed_tuple(text: str) -> tuple:
    return tuple(llm.embed(text))

def safe_cached_embed(text: str) -> list[float]:
    return list(_cached_embed_tuple(text))

_DATA_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "train-mock-data")
)


def _load(filename):
    with open(os.path.join(_DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def _text(data):
    return json.dumps(data, indent=2, ensure_ascii=False)


def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """將長文本切分為帶重疊的語意片段。"""
    if not text:
        return []
    
    chunks = []
    start = 0
    text_len = len(text)
    
    while start < text_len:
        end = min(start + chunk_size, text_len)
        chunks.append(text[start:end])
        
        if end == text_len:
            break
            
        start += (chunk_size - overlap)
        
    return chunks


def build_documents():
    docs = []

    # refund_policy.json — one document per policy entry
    for policy in _load("refund_policy.json"):
        docs.append({
            "title": policy["label"],
            "category": "refund",
            "source_file": "refund_policy.json",
            "content": _text(policy),
        })

    # ticket_types.json — one document per ticket type
    for tt in _load("ticket_types.json"):
        docs.append({
            "title": f"Ticket Type: {tt['display_name']}",
            "category": "booking",
            "source_file": "ticket_types.json",
            "content": _text(tt),
        })

    # booking_rules.json — one document per network section
    br = _load("booking_rules.json")
    for section in ("national_rail", "metro", "general_rules"):
        if section in br:
            docs.append({
                "title": f"Booking Rules — {section.replace('_', ' ').title()}",
                "category": "booking",
                "source_file": "booking_rules.json",
                "content": _text({section: br[section]}),
            })

    # travel_policies.json — one document per network section
    tp = _load("travel_policies.json")
    for section in ("metro", "national_rail"):
        if section in tp:
            docs.append({
                "title": f"Travel Policies — {section.replace('_', ' ').title()}",
                "category": "conduct",
                "source_file": "travel_policies.json",
                "content": _text({section: tp[section]}),
            })

    return docs


def seed():
    documents = build_documents()
    print(f"📄 Embedding {len(documents)} policy documents using {llm.chat_provider}...\n")

    for i, doc in enumerate(documents):
        print(f"  [{i+1}/{len(documents)}] Processing: {doc['title']}")
        chunks = chunk_text(doc["content"])
        print(f"    -> Split into {len(chunks)} chunks")

        for j, chunk_content in enumerate(chunks):
            try:
                embedding = safe_cached_embed(chunk_content)

                if len(embedding) != llm.embed_dim:
                    print(f"    ⚠️  Unexpected embedding dim: {len(embedding)} (expected {llm.embed_dim})")
                    print(f"    Update GEMINI_EMBED_DIM or OLLAMA_EMBED_DIM in skeleton/config.py")
                    sys.exit(1)

                doc_id = store_policy_document(
                    title=f"{doc['title']} (Part {j+1}/{len(chunks)})" if len(chunks) > 1 else doc["title"],
                    category=doc["category"],
                    content=chunk_content,
                    embedding=embedding,
                    source_file=doc.get("source_file", ""),
                )
                print(f"    ✓ Stored chunk {j+1}/{len(chunks)} as document id={doc_id}")

            except psycopg2.Error as db_e:
                if "dimension" in str(db_e).lower():
                    print(f"\n    ⚠️  Database dimension mismatch! Schema likely expects vector(768) but received {len(embedding)} dimensions.")
                    print("    If you switched to Gemini, you must update `databases/relational/schema.sql` to `vector(3072)` and reset the database.")
                    sys.exit(1)
                print(f"    ✗ Database error on chunk {j+1}: {db_e}")
                raise
            except Exception as e:
                print(f"    ✗ Failed on chunk {j+1}: {e}")
                raise

            if llm.chat_provider == "gemini" and (i < len(documents) - 1 or j < len(chunks) - 1):
                time.sleep(0.5)

    print(f"\n✅ All {len(documents)} policy documents processed and stored.")
    print("   Test with a similarity search:")
    print("   >>> from skeleton.llm_provider import llm")
    print("   >>> from databases.relational.queries import query_policy_vector_search")
    print("   >>> results = query_policy_vector_search(llm.embed('can I get a refund for a delay?'))")
    print("   >>> print(results[0]['title'])")


if __name__ == "__main__":
    seed()
