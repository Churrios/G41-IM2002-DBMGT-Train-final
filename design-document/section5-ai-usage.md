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

## Example 2 — C3 Alternative Routes Deduplication

**Context:**
`query_alternative_routes` was returning duplicate route arrays — different Cypher path objects that represented the same station sequence but had different internal identities. The grading guide required returning distinct routes, so deduplication by content (not object identity) was needed.

**Prompt:**
"My Cypher query uses `MATCH p = (o)-[...]->(d)` and returns multiple paths. Many results have the same station sequence but different object identities, so `DISTINCT p` does not remove them. How can I deduplicate by actual station ID sequence?"

**Outcome:**
AI suggested extracting an explicit list from the path using `[n IN nodes(p) | n.station_id]` into a named variable (`WITH [...] AS route`), then applying `RETURN DISTINCT route, total_time_min`. Because `route` is a plain list of strings, `DISTINCT` compares by value and correctly collapses duplicates. This fix was committed in PR #30 and verified by calling `query_alternative_routes("MS01", "MS09", avoid_station_id="MS07", max_routes=3)`, which returned 3 distinct routes with no duplicates.

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
AI recommended embedding whole documents for this use case, with two justifications: (1) policy documents are self-contained conceptual units — chunking would separate conditions from their definitions and degrade retrieval quality; (2) nomic-embed-text handles paragraph-length inputs well and produces meaningful document-level representations. It noted chunking would be more appropriate for long narrative documents (e.g., Wikipedia articles) where different sections answer different questions. We adopted this approach: `seed_vectors.py` embeds `title + "\n\n" + content` as a single string per document. Retrieval quality was confirmed during live testing (C1, C2 both ✅).
