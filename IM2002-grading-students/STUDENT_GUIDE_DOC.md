# IM2002 — Student Guide: Design Document Evaluation · /100

This guide explains how your Database Design Document will be evaluated. The document
must use the **exact section headings** shown below. Sections with different headings
may still be graded if the content clearly matches the criterion, but matching headings
avoids any ambiguity.

Submit your design document as a PDF or Markdown file via EEClass.

---

## Mark Summary

| Section | Max |
|---------|-----|
| Section 1 — Entity-Relationship Diagram | 25 |
| Section 2 — Normalisation Justification | 20 |
| Section 3 — Graph Database Design Rationale | 25 |
| Section 4 — Vector / RAG Design | 15 |
| Section 5 — AI Tool Usage Evidence | 10 |
| Section 6 — Reflection & Trade-offs | 5 |
| **Total** | **100** |
| Task 6 Bonus — Section 7 (optional) | +15 |

---

## Section 1 — Entity-Relationship Diagram · /25

| Criterion | What earns full marks |
|-----------|-----------------------|
| All required entities represented in the diagram | Every entity needed to model the system is present in the diagram |
| Relationships shown with correct cardinality (1:N, M:N, etc.) | Every major relationship has a cardinality label directly on the diagram line |
| Attributes shown: at minimum PK, key FKs, and 2–3 representative data fields per entity | Each entity shows its PK, the FKs that link it to other entities, and at least two data attributes |
| Diagram is readable and professionally drawn (dbdiagram.io, draw.io, Lucidchart, or equivalent) | Clean layout; text is legible; a tool-generated diagram rather than a hand sketch |
| **Section 1 Total** | |

**Cardinality scoring (8 marks):** All major relationships correctly labelled = 8 ·
Most correct = 5–7 · Some missing or wrong = 2–4 · No cardinality shown = 0

> **Tip:** Cardinality labels must appear **on the diagram lines**, not only in a legend or text paragraph. A diagram that shows entity boxes and lines without cardinality notation scores 0 for that criterion.

---

## Section 2 — Normalisation Justification · /20

| Criterion | What earns full marks |
|-----------|-----------------------|
| Identifies and explains at least one 2NF or 3NF design decision (e.g., why schedule stops are in a junction table rather than an array column) | Identifies a real normalisation decision, names the normal form it achieves, and explains the functional dependency that motivated it |
| Discusses at least one deliberate de-normalisation trade-off with justification (or explains why full normalisation was preferred) | Either describes a de-normalisation choice with a performance or simplicity rationale, or explicitly argues that full normalisation was appropriate for this system |
| Discusses password hashing: algorithm chosen, why it was selected over alternatives, how salt is managed | Names the specific algorithm; explains *why* it is preferred over MD5/SHA-1 (cost factor, key stretching); explains how salt prevents rainbow-table attacks |
| Correct use of database terminology (functional dependency, candidate key, transitive dependency, etc.) | Terms used correctly and precisely, not just as decoration |
| **Section 2 Total** | |

**Normalisation scoring (8 marks):** Identifies a real 3NF decision with clear explanation = 7–8 ·
**Normalisation scoring:** Identifies a real 3NF decision with clear explanation = full marks · Identifies a decision but explanation is shallow = 20% deduction · Mentions normalisation but does not connect to the schema = 70% deduction · Missing = 0

**Password hashing scoring:** Names specific algorithm + explains why (not just "it is secure") + explains how salt works = full marks · Names algorithm without rationale = 50% deduction · Mentions hashing without algorithm = 80% deduction · Missing or plain-text = 0

> **Tip — password hashing:** Writing "we use argon2id because it is secure" earns 20% marks, not full. You must explain *why* argon2id is preferred over MD5/SHA-1. You must also explain how salt prevents two users with the same password from having the same hash (defeating rainbow-table lookups). Use appropriate examples in your explanation.

---

## Section 3 — Graph Database Design Rationale · /25

| Criterion | What earns full marks |
|-----------|-----------------------|
| Explains what data is stored as nodes, as relationships, and as properties — with justification for each choice | All three levels addressed with clear reasoning — not just "stations are nodes because they are things" |
| Argues why a graph database is better than a relational database for the routing use cases (shortest path, delay ripple) | Makes a concrete algorithmic argument (e.g., Dijkstra on a graph vs recursive CTEs on a relational table) |
| Describes at least two query types (e.g., shortest path + interchange path) and explains how the graph model enables them | Two distinct query types described with specific reference to how the node/relationship structure makes them expressible |
| Discusses node identity: which property uniquely identifies nodes and why | Names the property used as node identity (e.g., `station_id`) and explains why it was chosen |
| **Section 3 Total** | |

**Nodes/relationships/properties scoring:** All three levels addressed with clear reasoning = full marks · Describes the model but reasoning is thin = 20% - 50% deduction · Only describes structure without rationale = 80% deduction · Missing = 0

**Graph vs relational argument:** Makes a concrete algorithmic argument = full marks - 10% deduction · Makes the argument but at a surface level = 20% - 50% deduction · Asserts graph is better without evidence = 80% deduction · Missing = 0

> **Tip:** Asserting "graphs are faster" or "graphs are better for connected data" without a concrete algorithmic argument earns 20% marks. Explain the specific algorithm (e.g., Dijkstra, BFS) and contrast it with what would be required in SQL (e.g., recursive CTEs with accumulating path sets) to show *why* the graph model is superior for these query patterns.

---

## Section 4 — Vector / RAG Design · /15

| Criterion | What earns full marks |
|-----------|-----------------------|
| Explains what is embedded (policy documents) and why cosine similarity is appropriate for semantic search | Explains that cosine similarity is magnitude-independent and measures directional similarity in the embedding space — not just "it measures how similar two things are" |
| Describes the full RAG pipeline: query embedding → similarity search → retrieved documents → LLM prompt → answer | All four stages described in sequence with enough detail that a reader could implement each stage |
| Discusses the embedding dimension choice (768 for Ollama / 3072 for Gemini) and what happens if the provider is switched after seeding | States the actual dimension your implementation uses; explains that switching provider after seeding causes a dimension mismatch that makes the index unusable |
| **Section 4 Total** | |

> **Tip:** Explain the practical consequence of changing providers after seeding.

---

## Section 5 — AI Tool Usage Evidence · /10

**Requirement:** 3 to 5 examples. Each example must include all three fields: **Context**, **Prompt**, **Outcome**.

| Criterion | What earns full marks |
|-----------|-----------------------|
| 3–5 distinct examples covering different aspects (schema design, query writing, debugging, design rationale, etc.) | At least 3 examples; each covers a genuinely different aspect of the project |
| Each example contains all three required fields: context + prompt + outcome | All three fields present in every example |
| At least one example discusses a case where the AI output was wrong or needed correction | Describes the specific error, how it was identified, and what correction was made |
| Overall quality: prompts are specific and purposeful (not generic like "explain databases") | Prompts show that the AI was given meaningful project context |
| **Section 5 Total** | |

**Three-fields scoring (3 marks):** All 3 fields present in every example = 3 ·
**Three-fields scoring:** All 3 fields present in every example = full marks · 1–2 fields missing in some examples = deduction · Missing fields throughout = 0 mark

**Correction example scoring:** Describes a specific AI error and how it was identified and fixed · Missing = 0

> **Tip:** Every example must have all three fields — **Context** (what you were trying to do), **Prompt** (what you asked), and **Outcome** (what happened, whether it was useful, and what you did next). Examples missing any field lose marks regardless of how many examples are provided. At least one example must describe a case where the AI gave incorrect output and explain how you identified and corrected it.

---

## Section 6 — Reflection & Trade-offs · /5

| Criterion | What earns full marks |
|-----------|-----------------------|
| Identifies at least two specific design decisions and explains the reasoning behind each | Two decisions named with clear reasoning — not vague ("we thought it was better"), but specific (e.g., "we chose SERIAL over UUID because our system is single-region and integer joins are faster") |
| Discusses one aspect that would be different in a production system | Names a concrete production concern (schema migrations, connection pooling, secret management, indexing strategy, etc.) and explains why it would need to change |
| **Section 6 Total** | |

**Design decisions scoring (3 marks):** Two specific decisions with clear reasoning = 3 ·
**Design decisions scoring:** Two specific decisions with clear reasoning = 3 · Vague decisions without reasoning = 1–2 · Missing = 0

**Production difference scoring:** Identifies a concrete production concern with explanation = 2 · Mentions something production-related without depth = 1 · Missing = 0

---

## Task 6 — Optional Extension Bonus · Section 7 · up to +15

To be eligible for the bonus in any marking scheme, all four of the following must be present:

1. The extension touches database code — new schema, queries, or seed data. UI-only changes do not qualify.
2. Detailed inline comments explain every new database operation.
3. A **Section 7** in this design document covers motivation, schema changes, example queries, and testing evidence.
4. A **`TASK6.md`** file at the repo root lists every file modified or added, with specific function and table names. Each modified file must also have a `# TASK 6 EXTENSION:` comment near the top.

The Section 7 bonus marks in this scheme are awarded for the quality of the document section only.
The code and live components have their own independent bonus marks.

| Criterion | Max | What earns full marks |
|-----------|-----|-----------------------|
| **Motivation** — explains why this extension adds value to the TransitFlow assistant | 3 | Clear, specific argument for why the feature improves the system — not just "it adds more features" |
| **Database changes** — new tables, relationships, or vector entries described with schema snippets | 4 | Actual schema or Cypher shown for new structures; not a prose-only description |
| **Example queries** — SQL/Cypher/similarity search shown with expected output | 4 | At least one complete query shown with the output it produces |
| **Testing evidence** — screenshots, query output in pgAdmin/Neo4j Browser, or chat UI demo | 4 | Evidence that the extension was actually run and produced correct output |
| **Task 6 Doc Bonus Total** | **+15** | |

> If Section 7 is present but the code does not include `TASK6.md` or per-file comment markers, the live and code bonus sections will not be awarded — only this document bonus can be graded.
