# Section 5 — AI Tool Usage Evidence

> 負責人：三人共同 | 配分：/10

> 要求：3–5 個範例，每個必須包含 **Context**、**Prompt**、**Outcome** 三個欄位
> 至少一個範例描述 AI 給出錯誤輸出，並說明如何發現與修正

---

## Example 1 — Interchange Station Schema Design

**Context:**
During relational schema design, we needed to model physical interchange stations where the metro and national rail networks meet (e.g., a station building that serves both systems). The question was whether to use a separate mapping table or FK references within the station tables themselves.

**Prompt:**
"We have `metro_stations` and `national_rail_stations` as separate tables because the two networks are operated differently. Some physical stations serve both networks. How should we model the interchange relationship in PostgreSQL — a separate junction table, or nullable FK columns within each station table?"

**Outcome:**
AI recommended bidirectional nullable FK columns: `metro_stations.interchange_nr_station_id → national_rail_stations` and `national_rail_stations.interchange_metro_station_id → metro_stations`, both with `ON DELETE SET NULL`. It argued that a junction table adds a join for a 1-to-at-most-1 relationship that is better expressed as a nullable FK. We adopted this verbatim. The `ON DELETE SET NULL` behaviour ensures removing one station record does not cascade-delete the other network's station, which would be incorrect.

---

## Example 2 — Separating Database Correctness from LLM Behaviour in End-to-End Testing

**Context:**
During end-to-end testing through the chatbot, several answers were wrong — the assistant claimed a station had no connections (C6), and once reported a booking as confirmed that did not exist in the database. We could not tell whether the database query functions were buggy or the LLM layer was misbehaving, and fixing the wrong layer would have wasted the time remaining before submission.

**Prompt:**
"Our chatbot gives wrong answers but we don't know whether the bug is in the database query functions or in the LLM layer. Design a test strategy that separates program correctness from LLM behaviour, and generate a direct-call test suite covering every graph, relational, and Task 6 function without polluting the seeded data."

**Outcome:**
AI proposed a dual-track method: a 49-assertion direct-call smoke suite exercising every query function against the live databases, run alongside scripted chatbot sessions, with every chatbot claim cross-checked by querying the database directly. Direct calls passed while the chatbot failed the same scenarios, proving the defects were LLM-side, which led to three targeted fixes (PR #59): wrapping `query_station_connections` output in a `{station_id, connections}` envelope so the answer LLM stops misattributing neighbours; normalising LLM-supplied severity words ("serious" → high) before they hit the `delay_events` CHECK constraint; and documenting that the single-turn agent cannot chain `get_available_seats` → `make_booking` (the "any seat" booking hallucination — the LLM fabricated a booking ID that direct DB queries proved absent). The AI-generated suite itself needed one correction before it could be trusted: it crashed on Windows' cp950 console when printing emoji status marks, fixed with `sys.stdout.reconfigure(encoding="utf-8")`.

---

## Example 3 — C4 Interchange Path Timeout Fix

**Context:**
`query_interchange_path` timed out (>30 s) for station pairs separated by many hops. The original query used variable-length relationship matching `*1..20`, which causes Neo4j to enumerate all paths exhaustively up to depth 20 — exponential in the worst case.

**Prompt:**
"My Neo4j Cypher query `MATCH p = (o)-[:METRO_LINK|RAIL_LINK|INTERCHANGE_TO*1..20]-(d)` times out on distant station pairs. How can I make it return a result in under a second?"

**Outcome:**
AI recommended replacing the exhaustive traversal with Neo4j's built-in `shortestPath()` function and reducing the depth bound to `*1..10`. `shortestPath()` uses BFS internally and returns the first path found rather than enumerating all paths, which reduces worst-case complexity from exponential to linear in the number of edges. After the fix, the same cross-network query (`query_interchange_path("MS01", "NR05")`) returned in <1 s with `found=True`, `total_time_min=42`. Fix committed in PR #30.

---

## Example 4 — AI Output Was Wrong: Vector Similarity Threshold

**Context:**
The RAG pipeline was returning weakly-related policy documents for some queries (e.g., a cancellation question retrieving a general fare document). We asked AI for a safe cosine similarity threshold to filter pgvector results.

**Prompt:**
"Our policy search using pgvector cosine similarity returns irrelevant documents. What threshold should we set so only semantically close documents are returned?"

**Outcome:**
AI recommended 0.3, claiming it was "a common starting point for semantic search with sentence-transformer embeddings." We set `VECTOR_SIMILARITY_THRESHOLD = 0.3` and tested with several queries. At 0.3, the pipeline still retrieved tangentially related documents because nomic-embed-text produces high-magnitude embeddings where even unrelated texts can score above 0.3. After empirical testing we raised the threshold to 0.5, which eliminated false positives while keeping all genuinely relevant results. The lesson: AI threshold suggestions are heuristics derived from different embedding spaces and must be validated against the actual model and data. The threshold is now configurable via environment variable so it can be tuned without code changes.

---

## Example 5 — Policy Document Chunking Strategy

**Context:**
Policy documents in `data/policies/` range from ~250 words (short rule summaries) to 2 000+ words (full refund policy). We needed to decide whether to embed each document as a single vector or split it into smaller chunks before embedding.

**Prompt:**
"Our policy documents vary from 250 to 2 000 words. For a RAG system where users ask specific policy questions, should we embed whole documents or chunk them? What are the trade-offs given that we are using nomic-embed-text (768-dimensional embeddings)?"

**Outcome:**
AI recommended embedding whole documents for this use case, with two justifications: (1) policy documents are self-contained conceptual units — chunking would separate conditions from their definitions and degrade retrieval quality; (2) nomic-embed-text handles paragraph-length inputs well and produces meaningful document-level representations. We did **not** adopt this fully: the longest policy documents exceed 2,000 words, and embedding each as a single vector dilutes its semantic focus. `seed_vectors.py` instead chunks content with `chunk_text()` (300 characters per chunk, 50-character overlap between adjacent chunks) and embeds each chunk separately — 101 chunks in `policy_documents` after seeding. The 50-character overlap addresses exactly the risk the AI raised: conditions split from their definitions at a chunk boundary retain context inside the overlap. Retrieval quality was confirmed during live testing via RAG policy questions (R1 delay-refund and R2 bicycle policy both passed, with answers grounded in the retrieved chunks rather than model generation).
