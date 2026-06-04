# TransitFlow — LLM & AI Fundamentals Tutorial

A practical guide to large language models, embeddings, and retrieval-augmented generation, grounded in the TransitFlow transit management system. Every concept here is demonstrated with real examples from the project code.

---

## Table of Contents

**Part 1 — Language Models**
1. [What is an LLM and How Does it Work](#1-what-is-an-llm-and-how-does-it-work)
2. [Tokens & Tokenization](#2-tokens--tokenization)

**Part 2 — Embeddings**
3. [What is an Embedding and How/Why it Works](#3-what-is-an-embedding-and-howwhy-it-works)

**Part 3 — RAG: Databases and LLMs Together**
4. [What DB Means to an LLM — Knowledge Cutoffs and RAG](#4-what-db-means-to-an-llm--knowledge-cutoffs-and-rag)
5. [How Databases Extend LLM Knowledge](#5-how-databases-extend-llm-knowledge)

**Part 4 — Prompt & Context Engineering**
6. [Prompt Engineering and Context Engineering](#6-prompt-engineering-and-context-engineering)

**Part 5 — Practical Tips**
7. [Practical Tips: LLMs, RAG, and Knowledge Engineering](#7-practical-tips-llms-rag-and-knowledge-engineering)
8. [What to Learn Next](#8-what-to-learn-next)

---

## Part 1 — Language Models

---

### 1. What is an LLM and How Does it Work

#### 1.1 The Problem LLMs Solve

Before LLMs, software understood language through rules and pattern matching. If a user typed "Can I cancel my ticket?", a rules-based system looked for the word "cancel" and triggered a cancellation flow. If they typed "I'd like to undo my booking", the same rule missed it entirely.

LLMs understand *meaning*, not just keywords. They can recognise that both phrasings mean the same thing, generate a coherent reply in natural language, and reason about multi-step questions they have never seen before.

#### 1.2 How an LLM is Trained

An LLM is trained on a massive corpus of text — books, websites, code, articles — with a single objective: **predict the next token** given everything before it.

```
Training objective: given this sequence, what comes next?

Input:  "The train departs from Central Station at"
Target:  "nine"   (the model should assign high probability to this word)

Input:  "The train departs from Central Station at nine"
Target:  "thirty"

Input:  "The train departs from Central Station at nine thirty"
Target:  "AM"
```

This sounds simple, but to predict the next token accurately across billions of diverse sentences, the model must learn grammar, facts, reasoning patterns, and common sense. The knowledge is not stored in a lookup table — it is compressed into hundreds of billions of numerical *weights* inside the network.

#### 1.3 The Transformer Architecture (Simplified)

The dominant architecture for LLMs is the **transformer**. You do not need to understand every detail, but the high-level picture matters:

```
ONE FORWARD PASS — turning tokens into an answer
─────────────────────────────────────────────────────────────────

  Input text: "What is the refund policy?"
        │
        ▼
  ┌──────────────┐
  │  Tokenizer   │   Text split into tokens (see section 2)
  └──────┬───────┘   "What", "is", "the", "refund", "policy", "?"
         │
         ▼
  ┌──────────────┐
  │  Embeddings  │   Each token → a vector (a list of numbers)
  │  Layer       │   representing its meaning in context
  └──────┬───────┘
         │
         ▼
  ┌──────────────────────────────────────┐
  │  Attention Layers  (×N, stacked)     │
  │                                      │
  │  Each token "looks at" every other   │
  │  token and decides which ones are    │
  │  relevant to understanding itself.   │
  │                                      │
  │  "policy" attends strongly to        │
  │  "refund" → these two are related    │
  └──────┬───────────────────────────────┘
         │
         ▼
  ┌──────────────┐
  │  Output      │   Probability over the entire vocabulary:
  │  Layer       │   P("The") = 0.12, P("For") = 0.31, P("Our") = 0.09 ...
  └──────┬───────┘
         │
         ▼
  Sample one token ("For") → append to sequence → repeat
```

The key innovation is **attention**: every token can directly influence every other token in the sequence. Earlier architectures processed text left-to-right in a chain, which made it hard to link words far apart. Attention makes long-range dependencies cheap to model.

#### 1.4 Why LLMs Hallucinate

An LLM does not look things up. It generates the most *plausible* continuation of the input based on patterns learned during training. If you ask it about TransitFlow's refund policy — a document it has never seen — it will generate a response that sounds like a refund policy, because that is what comes after "our refund policy states...". It has no way to know it is wrong.

```
HALLUCINATION — the model predicts plausible-sounding text, not facts

User: "What is TransitFlow's refund policy for delays over 30 minutes?"

Without grounding:
LLM generates → "For delays over 30 minutes, TransitFlow offers a 25% discount
                 on your next journey..."    ← plausible-sounding, entirely made up

With grounding (RAG — see section 4):
LLM reads retrieved policy → "For delays of 30–59 minutes, passengers receive
                               50% compensation. For 60–119 minutes, 100% refund."
                               ← accurate, because it came from the database
```

The solution is not to make the LLM smarter — it is to give it the right facts at query time. That is what Retrieval-Augmented Generation (RAG) does.

#### 1.5 TransitFlow Anchor: How `llm.chat()` Works

The project abstracts both Ollama (local) and Gemini (cloud) behind a single `llm.chat()` call:

```python
# skeleton/llm_provider.py  lines 181–194
def _ollama_chat(self, messages: list[dict], system_prompt: str) -> str:
    clean_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
    if system_prompt:
        clean_messages = [{"role": "system", "content": system_prompt}] + clean_messages
    payload = {
        "model": self._ollama_chat_model,   # e.g. "llama3.2:1b"
        "messages": clean_messages,
        "stream": False,
    }
    r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
    r.raise_for_status()
    return r.json()["message"]["content"]
```

The model receives a list of messages (the conversation history plus the current turn) and returns a string — the next assistant turn. The LLM does not retain memory between API calls; you pass the entire history every time.

---

### 2. Tokens & Tokenization

#### 2.1 What a Token Is

A token is the unit of text that an LLM reads and writes. Tokens are *not* words — they are subword fragments produced by an algorithm (BPE — Byte Pair Encoding) that balances vocabulary size against coverage.

```
TEXT → TOKENS
──────────────────────────────────────────────────────────
"TransitFlow"      → ["Trans", "it", "Flow"]          3 tokens
"refund"           → ["ref", "und"]                   2 tokens
"unrecognised"     → ["un", "rec", "ogn", "ised"]     4 tokens
"hello"            → ["hello"]                        1 token
"NR01"             → ["NR", "01"]                     2 tokens
"🚉"               → ["<0xF0>","<0x9F>","<0x9A>","<0x89>"]  4 tokens
"The"              → ["The"]                          1 token

"refund policy" → ["ref", "und", " policy"]           3 tokens
                          ↑
             note: a space before "policy" is
             often absorbed into the next token
```

Tokenization is done by a fixed vocabulary (typically 32k–128k entries) trained alongside the model. The same model always produces the same tokenization for the same text.

#### 2.2 Why Tokens Matter

**Context window** — the maximum number of tokens an LLM can process in a single call. Everything — system prompt, conversation history, retrieved documents, and the user message — must fit within this limit.

```
CONTEXT WINDOW BUDGET (example: 8,000 tokens)
────────────────────────────────────────────────────────────
┌─────────────────────────────────────────┐
│  System prompt           ~200 tokens    │
├─────────────────────────────────────────┤
│  Conversation history    ~600 tokens    │
├─────────────────────────────────────────┤
│  Retrieved policy docs   ~800 tokens    │  ← from pgvector
├─────────────────────────────────────────┤
│  User message            ~50 tokens     │
├─────────────────────────────────────────┤
│  LLM response (output)   ~200 tokens    │
├─────────────────────────────────────────┤
│  Remaining budget        ~6,150 tokens  │
└─────────────────────────────────────────┘

If the total exceeds 8,000 tokens → the API returns an error (or silently
truncates older history, depending on the provider).
```

**Cost** — cloud APIs charge per input + output token. A 3,072-dimensional embedding call and a 500-token chat response both cost money. Local models (Ollama) have zero per-call cost but run on your hardware.

**Rough size guide:**

| Amount of text | Approximate tokens |
|---|---|
| One short sentence | 10–20 tokens |
| One paragraph | 60–100 tokens |
| One page (500 words) | 650–750 tokens |
| One policy document (TransitFlow) | 200–400 tokens |
| This entire tutorial | ~8,000 tokens |

#### 2.3 TransitFlow Anchor: Why the Tool-Selection Prompt is Concise

The tool-selection prompt in `skeleton/agent.py` (lines 576–604) must be short and precise. It fires on every user turn and must leave room for the conversation history and the model's response:

```python
# skeleton/agent.py  lines 576–604
tool_selection_prompt = f"""Output only this JSON (no other text):
{{"tool_calls": [{{"name": "TOOL", "params": {{"KEY": "VALUE"}}}}]}}
Or if no tool needed: {{"tool_calls": []}}

STATIONS: Metro=MS01-MS20, Rail=NR01-NR10
USER: {current_user_email or "not logged in"}
...
JSON:"""
```

Every word is deliberate. The prompt is stripped to the minimum needed — any longer and it eats into the context budget available for history and retrieved data.

---

## Part 2 — Embeddings

---

### 3. What is an Embedding and How/Why it Works

#### 3.1 The Core Idea

An embedding converts a piece of text into a list of numbers — a **vector** — such that text with similar meaning produces numerically similar vectors. The vectors live in a high-dimensional space (768 or 3,072 dimensions in TransitFlow), and similarity in that space corresponds to similarity of meaning.

```
SEMANTIC SPACE — similar meaning → nearby vectors
──────────────────────────────────────────────────────────────────

"Can I get a refund?"         → [0.23, -0.41,  0.87, ..., 0.12]
"How do I cancel my ticket?"  → [0.21, -0.39,  0.85, ..., 0.14]
                                └─────── nearly identical ────┘  ← close in space

"What time does the M1 run?"  → [0.91,  0.13, -0.22, ..., 0.77]  ← far away

"Is there a delay on NR1?"    → [0.88,  0.15, -0.19, ..., 0.81]
                               └──────── close to each other ──┘  ← different topic,
                                                                        same neighbour region
```

This is why a user asking "Am I entitled to compensation for my delayed train?" can retrieve a document titled "Delay Compensation Policy" — even though no word in the question appears in the document title. The meanings are close; the vectors are close.

#### 3.2 How Embedding Models are Trained

An embedding model is trained with a technique called **contrastive learning**:

```
CONTRASTIVE LEARNING — training the embedding model
─────────────────────────────────────────────────────────────────

Training data:
  Positive pair (similar): ("refund for delay", "compensation for late train")
  Negative pair (different): ("refund for delay", "train departure time")

Training objective:
  Pull positives close → minimise distance between their vectors
  Push negatives apart → maximise distance between their vectors

  Before training:           After training:
  All vectors random          Similar text → nearby
  ┌──────────────┐            ┌──────────────┐
  │ · ·  · · ·   │            │  ●●●         │
  │  · ·  · ·    │     →      │         ▲▲   │
  │   · · · ·    │            │    ■■■       │
  └──────────────┘            └──────────────┘
                               ●● refund/cancel cluster
                               ▲▲ schedule/route cluster
                               ■■ conduct/policy cluster
```

The result is a model that understands meaning without being given explicit rules.

#### 3.3 Cosine Similarity — the Measurement

Vectors have direction and magnitude. For meaning comparison, direction is what matters — you want to know *how aligned* two vectors are, not how large they are.

**Cosine similarity** measures the angle between two vectors:

```
COSINE SIMILARITY — direction, not magnitude
────────────────────────────────────────────────────────────────

     ▲
     │            /  ← "Can I get a refund?" vector
     │           /
     │          / ← small angle → high cosine similarity (≈ 0.92)
     │         /
     │        /  ← "How do I cancel my ticket?" vector
     │       /
     │      /
     ─────────────────► (imagine 768 dimensions instead of 2)

     ▲
     │
     │
     │                 ← large angle → low cosine similarity (≈ 0.11)
     │     ────────────────────────► "What time does the M1 run?"
     │
     ─────────────────►

Score range: -1.0 (opposite) to 1.0 (identical direction)
Scores above 0.5 are considered similar in TransitFlow (see config.py line 45)
```

In pgvector, the `<=>` operator computes **cosine distance** (= 1 − cosine similarity). The query in TransitFlow converts it back to similarity:

```sql
-- databases/relational/queries.py  line 318
1 - (embedding <=> %s::vector) AS similarity
--   ↑ cosine distance          ↑ converted to similarity (higher = more similar)
```

#### 3.4 Dimensions — What 768 vs. 3,072 Means

| Model | Dimensions | Provider | Size |
|---|---|---|---|
| `nomic-embed-text` | 768 | Ollama (local) | ~274 MB |
| `gemini-embedding-001` | 3,072 | Gemini (cloud) | API call |

More dimensions give the model more "room" to encode nuance. But a larger embedding does not automatically mean better retrieval — it depends on what the model was trained on. The two models have different strengths; more dimensions just means each document vector takes more storage and each similarity computation is more expensive.

```python
# skeleton/config.py  lines 22–27
OLLAMA_EMBED_MODEL    = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_DIM      = 768

# skeleton/config.py  lines 18–20
GEMINI_EMBED_MODEL    = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_EMBED_DIM      = 3072
```

The database schema matches the provider:

```sql
-- databases/relational/schema.sql  lines 48
embedding   vector(768),
-- ↑ change to vector(3072) if switching to Gemini
```

#### 3.5 TransitFlow Anchor: Generating and Storing an Embedding

**Generating** (at query time):

```python
# skeleton/llm_provider.py  lines 196–203
def _ollama_embed(self, text: str) -> List[float]:
    r = requests.post(
        f"{OLLAMA_BASE_URL}/api/embeddings",
        json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embedding"]   # a list of 768 floats
```

**Storing** (at seed time, once):

```sql
-- databases/relational/queries.py  lines 345–350
INSERT INTO policy_documents (title, category, content, embedding, source_file)
VALUES (%s, %s, %s, %s::vector, %s)
```

**Indexing** — so similarity search is fast:

```sql
-- databases/relational/schema.sql  line 54
CREATE INDEX IF NOT EXISTS ON policy_documents USING hnsw (embedding vector_cosine_ops);
```

HNSW (Hierarchical Navigable Small World) is an approximate nearest-neighbour index. It finds the top-K similar vectors without checking every row — the same trade-off as a B-tree index, but for vectors instead of scalars. Without this index, every similarity query reads every row in the table.

---

## Part 3 — RAG: Databases and LLMs Together

---

### 4. What DB Means to an LLM — Knowledge Cutoffs and RAG

#### 4.1 The Knowledge Cutoff Problem

Every LLM has a **training cutoff**: a date after which it has seen no new information. More importantly, even before the cutoff, the model has never seen your private data — your company's refund policy, your train schedules, your users' bookings.

```
WHAT THE LLM KNOWS vs. WHAT IT DOESN'T KNOW
────────────────────────────────────────────────────────────────

LLM training data (public internet):          LLM blind spots:
  ✓ How trains generally work                  ✗ TransitFlow's specific policies
  ✓ Grammar and language understanding         ✗ Current fare prices
  ✓ Common refund policy structures            ✗ Seat availability right now
  ✓ General geography                          ✗ Any event after training cutoff
  ✓ How to write a professional reply          ✗ Your users' booking history
```

#### 4.2 Two Ways to Give an LLM New Knowledge

**Option 1: Fine-tuning** — retrain the model's weights on your data.

```
FINE-TUNING
─────────────────────────────────────────────
Base model weights
    +
Your policy documents (thousands of examples)
    ↓
Expensive GPU training (hours to days)
    ↓
New model that "knows" your policies

Problems:
  ✗ Expensive and slow
  ✗ When policies change → must retrain
  ✗ Model still hallucinates; it just
    hallucinates more confidently about
    your domain
  ✗ Hard to audit: where did this answer
    come from?
```

**Option 2: RAG — Retrieval-Augmented Generation** — retrieve the relevant facts at query time and inject them into the prompt.

```
RAG
─────────────────────────────────────────────
Base model weights (unchanged)
    +
Your policy documents in a database
    +
At query time: retrieve → inject → answer

Benefits:
  ✓ Policies updated in the DB → immediately
    reflected in answers
  ✓ Auditable: you can see exactly which
    document the answer came from
  ✓ Works with any LLM, no training needed
  ✓ Cheap: embed documents once, query many
```

#### 4.3 The RAG Pipeline — Step by Step

```
USER QUESTION: "What's the refund policy for a 45-minute delay?"
│
│  STEP 1: EMBED THE QUESTION
▼
llm.embed("What's the refund policy for a 45-minute delay?")
→ [0.18, -0.37, 0.82, ..., 0.09]   (768 floats)
│
│  STEP 2: VECTOR SIMILARITY SEARCH
▼
SELECT title, content, 1 - (embedding <=> query_vector) AS similarity
FROM policy_documents
ORDER BY embedding <=> query_vector
LIMIT 3;

Returns:
  ┌────────────────────────────────┬────────────┐
  │ title                          │ similarity │
  ├────────────────────────────────┼────────────┤
  │ Delay Compensation Policy      │   0.89     │  ← most relevant
  │ National Rail – Normal Service │   0.71     │
  │ Metro – Single Ticket          │   0.52     │
  └────────────────────────────────┴────────────┘
│
│  STEP 3: INJECT INTO LLM PROMPT
▼
"DATA FROM TRANSITFLOW DATABASE:

[search_policy]
title: Delay Compensation Policy
content: {delay_minutes: 30, compensation_pct: 50%,
          delay_minutes: 60, compensation_pct: 100%, ...}
similarity: 0.89

...

User asks: What's the refund policy for a 45-minute delay?

Answer using only the data above:"
│
│  STEP 4: LLM GENERATES ANSWER
▼
"For a 45-minute delay, you are entitled to 50% compensation,
 as it falls within the 30–59 minute delay category..."
```

#### 4.4 Why RAG Beats Keyword Search

A keyword search for "refund delay" finds documents that contain those exact words. A vector search finds documents that are *semantically related* — even if the words don't match.

```
QUERY: "Am I entitled to money back for my late train?"

KEYWORD SEARCH
──────────────────────────────────────────────────────────
Searches for: "entitled", "money", "back", "late", "train"
Misses:  "Delay Compensation Policy"   ← no exact word match
Misses:  "National Rail Refund Rules"  ← no exact word match
Finds:   "National Rail Train Schedule"  ← "train" matches! (wrong result)

VECTOR SEARCH (RAG)
──────────────────────────────────────────────────────────
Searches for: meaning of "Am I entitled to money back for my late train?"
Finds:   "Delay Compensation Policy"       similarity 0.87 ✓
Finds:   "National Rail – Normal Service"  similarity 0.72 ✓
Ignores: "National Rail Train Schedule"    similarity 0.31 ✗ (below threshold)
```

#### 4.5 TransitFlow Anchor: The `search_policy` Tool

When the agent decides a question is about policy, it calls `search_policy`. Here is the exact code path:

```python
# skeleton/agent.py  lines 384–395
elif tool_name == "search_policy":
    embedding = llm.embed(params["query"])        # Step 1: embed
    docs = query_policy_vector_search(embedding)  # Step 2: search
    result = [
        {
            "title":      d["title"],
            "category":   d["category"],
            "content":    d["content"][:800],     # truncated to save tokens
            "similarity": round(d["similarity"], 3),
        }
        for d in docs
    ]
```

And the SQL that runs inside `query_policy_vector_search`:

```python
# databases/relational/queries.py  lines 313–323
sql = """
    SELECT
        title,
        category,
        content,
        1 - (embedding <=> %s::vector) AS similarity
    FROM policy_documents
    WHERE 1 - (embedding <=> %s::vector) > %s   -- threshold: 0.5
    ORDER BY embedding <=> %s::vector            -- nearest first
    LIMIT %s                                     -- top_k: 3
"""
```

---

### 5. How Databases Extend LLM Knowledge

#### 5.1 Three Databases, Three Roles

TransitFlow uses three databases, each extending the LLM's knowledge in a different way:

```
LLM ALONE:  knows how language works, but nothing specific about TransitFlow
    │
    ├──► PostgreSQL ── structured facts (exact answers)
    │    Schedules, fares, seat availability, bookings, users, payments
    │    → Query by matching exact values (SQL WHERE clause)
    │    → Returns: "NR_SCH01 departs at 09:30, fare $8.50, 12 seats left"
    │
    ├──► pgvector  ── unstructured knowledge (fuzzy answers)
    │    Policy documents: refund rules, conduct policies, booking terms
    │    → Query by semantic similarity (cosine distance)
    │    → Returns: "Delay Compensation Policy: 50% for 30–59 min delays"
    │
    └──► Neo4j     ── graph knowledge (relationship answers)
         Station network: which stations connect, via which lines, at what cost
         → Query by graph traversal (shortest path algorithm)
         → Returns: "MS01 → MS05 → MS09, line M1, 12 minutes total"
```

| Database | Data type | Query style | Example question answered |
|---|---|---|---|
| PostgreSQL | Structured rows | SQL `WHERE` | "What are the fares on NR_SCH01?" |
| pgvector | Unstructured text | Cosine similarity | "Can I bring my dog on the metro?" |
| Neo4j | Relationships/graphs | Path traversal | "Fastest route from MS01 to MS14?" |

#### 5.2 Tool Calling — How the Agent Decides

The agent does not query all three databases for every question. It uses **tool calling**: it asks the LLM to read the question and select the right tool (and therefore the right database) to answer it.

```
USER: "What is the luggage policy on national rail?"
    │
    ▼
TOOL SELECTION PROMPT
  "Which tool should answer this?
   find_route | check_national_rail_availability |
   get_available_seats | search_policy | ..."
    │
    ▼
LLM SELECTS: search_policy  ("luggage policy" → policy document question)
    │
    ▼
search_policy QUERIES: pgvector  (semantic search → Travel Policies – National Rail)
    │
    ▼
LLM ANSWER: "On National Rail, you may bring up to 3 items of luggage..."
─────────────────────────────────────────────────────────────────────────
USER: "Is there a 9am train from NR01 to NR05?"
    │
    ▼
LLM SELECTS: check_national_rail_availability  (availability → schedule question)
    │
    ▼
QUERIES: PostgreSQL  (structured query on national_rail_schedules)
    │
    ▼
LLM ANSWER: "Yes, NR_SCH02 departs NR01 at 09:15, arrives NR05 at 10:05..."
─────────────────────────────────────────────────────────────────────────
USER: "Fastest route from Central Square to Airport?"
    │
    ▼
LLM SELECTS: find_route  (route → graph question)
    │
    ▼
QUERIES: Neo4j  (Dijkstra algorithm on the station graph)
    │
    ▼
LLM ANSWER: "Take line M1 from MS01 to MS09 (22 minutes)..."
```

The mapping of tools to databases is defined in `skeleton/agent.py`. The LLM routes the question; the databases supply the facts; the LLM writes the final answer.

#### 5.3 The Key Insight

> **LLMs are reasoning engines, not databases. You store facts in a database; you store reasoning in an LLM.**

An LLM is excellent at understanding what a user means, selecting the right approach, summarising retrieved data, generating natural-language responses, and handling follow-up questions. It is poor at storing exact facts reliably, performing arithmetic, and knowing things it was not told.

Databases are excellent at storing, indexing, and retrieving exact data. They do not understand language.

RAG combines the strengths of both:

```
DATABASE STRENGTHS        LLM STRENGTHS           RAG = BOTH
──────────────────────    ──────────────────────   ──────────────────────
✓ Exact fact storage      ✓ Language understanding ✓ Exact facts retrieved
✓ Fast retrieval          ✓ Reasoning              ✓ LLM writes the answer
✓ Up-to-date data         ✓ Natural output         ✓ System stays accurate
✗ Cannot generate text    ✗ Unreliable facts       (and up to date)
✗ Cannot understand query ✗ Knowledge cutoff
```

---

## Part 4 — Prompt & Context Engineering

---

### 6. Prompt Engineering and Context Engineering

#### 6.1 What a Prompt Actually Is

Every LLM call receives a **prompt** — the complete text the model reads before generating a response. In a chat-based system, the prompt is structured as a list of turns:

```
FULL PROMPT STRUCTURE (what the LLM actually receives)
──────────────────────────────────────────────────────────────────

┌────────────────────────────────────────────────────────────────┐
│  SYSTEM PROMPT                                                 │
│  Persona, rules, context that apply to every turn              │
│  "You are TransitFlow, a transit assistant..."                 │
├────────────────────────────────────────────────────────────────┤
│  USER TURN 1                                                   │
│  "What time does the M1 run?"                                  │
├────────────────────────────────────────────────────────────────┤
│  ASSISTANT TURN 1                                              │
│  "The M1 runs from 06:00 to 23:30 on weekdays..."              │
├────────────────────────────────────────────────────────────────┤
│  USER TURN 2  (current)                                        │
│  DATA FROM TRANSITFLOW DATABASE:                               │
│  [search_policy]                                               │
│  title: Delay Compensation Policy                              │
│  content: {30-59 min: 50%, 60-119 min: 100% ...}               │
│                                                                │
│  User asks: What's my refund for a 45-minute delay?            │
│                                                                │
│  Answer using only the data above:                             │
└────────────────────────────────────────────────────────────────┘
                        │
                        ▼
                  LLM GENERATES:
          "For a 45-minute delay you are entitled
           to 50% compensation..."
```

The LLM has no memory between sessions. Everything it needs to know must be in the prompt.

#### 6.2 The TransitFlow System Prompt

`SYSTEM_PROMPT` in `skeleton/agent.py` (lines 102–113) demonstrates several engineering decisions:

```python
SYSTEM_PROMPT = """You are TransitFlow, a transit assistant for a dual-network system.

Networks: City Metro MS01-MS20 (lines M1-M4) | National Rail NR01-NR10 (lines NR1-NR2)
Interchanges: Central=MS01/NR01 | Old Town=MS07/NR03 | Ferndale=MS15/NR07
Today: {today}

LOGIN RULE: Routes, fares, schedules, and policies work WITHOUT login for all users.
Only make_booking and cancel_booking need login...

When DATA FROM TRANSITFLOW DATABASE is provided, use it as the only source of truth.
Do not contradict it or say a route was not found if the data shows one.
For route results: list every station name in order, note any line changes,
and give the total travel time.
Always reply in the same language as the user.
""".format(today=date.today().isoformat())
```

Each line is doing deliberate work:

| Prompt element | Purpose | Technique |
|---|---|---|
| `"You are TransitFlow..."` | Sets persona and domain | Role/persona |
| `"Networks: City Metro MS01-MS20..."` | Gives the LLM the station ID scheme | Factual grounding |
| `"Today: {today}"` | Injects the current date at runtime | Dynamic context |
| `"When DATA FROM... provided, use it as the only source of truth"` | Prevents hallucination | Grounding constraint |
| `"Always reply in the same language as the user"` | Multilingual support | Behavioural rule |

#### 6.3 Five Core Prompt Engineering Techniques

**1. Grounding — giving the LLM facts to anchor its answer**

```
WITHOUT GROUNDING:
  User: "What's your refund for delays?"
  LLM:  "We offer a generous compensation scheme..."  ← invented

WITH GROUNDING:
  Prompt: "DATA FROM DATABASE: {delay_policy_json}
           Answer using only the data above."
  LLM:  "For 30–59 min delays: 50% refund. For 60+: 100%." ← accurate
```

**2. Role/Persona — defining who the LLM is**

```python
# Good: specific, purposeful
"You are TransitFlow, a transit assistant for a dual-network system."

# Avoid: vague
"You are a helpful assistant."
```

**3. Output Format Constraints — forcing structured output**

When the LLM's output is parsed by code, constrain the format tightly:

```python
# skeleton/agent.py  lines 576–578 — the tool-selection prompt
"""Output only this JSON (no other text):
{"tool_calls": [{"name": "TOOL", "params": {"KEY": "VALUE"}}]}
Or if no tool needed: {"tool_calls": []}"""
```

Without the format constraint, the LLM might explain its reasoning in prose before the JSON — which breaks the parser.

**4. Few-Shot Examples — showing the LLM what a good answer looks like**

```python
# skeleton/agent.py  lines 595–602
"""Examples:
"fastest route MS01 to MS14" -> {"tool_calls": [{"name": "find_route", ...}]}
"cheapest NR01 to NR05"      -> {"tool_calls": [{"name": "find_route", ..., "optimise_by": "cost"}]}
"refund policy"              -> {"tool_calls": [{"name": "search_policy", ...}]}
"hello"                      -> {"tool_calls": []}"""
```

Each example teaches the LLM the pattern without writing an explicit rule. Three to five examples are usually enough.

**5. Chain of Thought — asking the LLM to reason before answering**

For complex questions, ask the LLM to think step-by-step before giving a final answer:

```
WITHOUT CHAIN OF THOUGHT:
  "Is NR_SCH01 cheaper than MS_SCH01?"
  → LLM guesses

WITH CHAIN OF THOUGHT:
  "Think step by step, then give your final answer.
   Is NR_SCH01 cheaper than MS_SCH01?"
  → LLM: "NR_SCH01 base fare is $5.00 + $1.00/stop.
           MS_SCH01 base fare is $2.00 + $0.50/stop.
           For 3 stops: NR = $8.00, MS = $3.50.
           Therefore MS_SCH01 is cheaper."   ← more reliable
```

Chain of thought works because the model uses the reasoning text it generates as additional context for the final answer — it essentially "reads back" its own working.

#### 6.4 Context Engineering — What Gets Injected and When

Context engineering is about deciding what information to include in the prompt for each turn, not just what instructions to give.

TransitFlow injects different context depending on login state (`agent.py` lines 549–566):

```python
if current_user_email:
    contextual_prompt = SYSTEM_PROMPT + (
        f"\n\nLogged-in user: {user_display}. "
        "Answer personal booking queries for this user without asking for their email or ID."
    )
else:
    contextual_prompt = SYSTEM_PROMPT + (
        "\n\nNo user is currently logged in. "
        "If the user asks about personal bookings... tell them they must log in first."
    )
```

And injects retrieved database results into the user turn (`agent.py` lines 732–743):

```python
if tool_results:
    data_block = "\n\n".join(
        f"[{tr['tool']}]\n{_normalise_result(tr['tool'], tr['result'])}"
        for tr in tool_results
    )
    content = (
        f"DATA FROM TRANSITFLOW DATABASE:\n{data_block}"
        f"\n\nUser asks: {user_message}"
        f"\n\nAnswer using only the data above:"
    )
```

The phrase "Answer using only the data above" is the critical grounding constraint. Without it, the LLM might supplement retrieved data with hallucinated additions.

#### 6.5 Common Pitfalls

| Pitfall | Example | Fix |
|---|---|---|
| Conflicting instructions | "Be brief. Give a thorough detailed answer." | Choose one |
| No format constraint | LLM returns prose when you expect JSON | Add "Output only this JSON:" |
| Forgetting to include data | Retrieved doc not in prompt | Log full prompt to verify |
| Too many examples | 20 few-shot examples eat all the context budget | 3–5 is usually enough |
| Vague persona | "Be helpful and friendly" | Specify domain + constraints |
| Prompt too long | System prompt + history exceeds context window | Trim history; shorten prompts |

---

## Part 5 — Practical Tips

---

### 7. Practical Tips: LLMs, RAG, and Knowledge Engineering

#### 7.1 Chunking — How You Split Documents Affects Retrieval Quality

A "chunk" is the unit of text you embed and store. The right chunk size depends on how questions will be asked.

```
CHUNKING STRATEGIES
──────────────────────────────────────────────────────────────────────────────

STRATEGY          SIZE      PROS                    CONS
─────────────────────────────────────────────────────────────────────────────
Fixed window      512 tokens  Simple, predictable    May split mid-sentence;
                              Easy to implement      loses context at boundaries

Sentence-         1–5 sents   Preserves meaning      Variable size; harder
boundary                      within sentences        to implement

Paragraph /       1 section   Keeps related ideas    Chunks may be too long
section                       together               for short questions

One document      Whole doc   Simple; best when      Too much noise if doc is
(TransitFlow)                 each doc = one topic   large or covers many topics

──────────────────────────────────────────────────────────────────────────────
TransitFlow uses one JSON policy object per chunk — each is a single, coherent
topic (e.g., "Delay Compensation Policy") with no splitting needed.
```

**Rule of thumb:** if the answer to a likely question fits inside one chunk, the chunk size is right. If the answer often spans multiple chunks, make them larger.

#### 7.2 Similarity Threshold — Tuning the Acceptance Bar

TransitFlow uses a threshold of 0.5 (`skeleton/config.py` line 45):

```
VECTOR_SIMILARITY_THRESHOLD = 0.5

Similarity < 0.5 → document excluded from results
Similarity ≥ 0.5 → document returned to the LLM

WHAT HAPPENS AT DIFFERENT THRESHOLDS
──────────────────────────────────────────────────────────────────
Threshold 0.3  Too low  → Irrelevant documents included
                         → LLM answers with wrong information
                         → "Our cycling policy mentions delay compensation..."

Threshold 0.5  Balanced → Only relevant documents returned
                         → LLM has good signal to answer from

Threshold 0.8  Too high → Most questions return no results
                         → LLM says "I don't have that information"
                         → Even when the policy exists
```

Start at 0.5 and lower it if users are getting "no results found" for valid questions. Raise it if answers contain irrelevant information.

#### 7.3 Provider Portability — Same Code, Swappable Backend

TransitFlow's `llm_provider.py` abstracts Ollama and Gemini behind a single interface:

```python
# skeleton/llm_provider.py  lines 142–146
def embed(self, text: str) -> List[float]:
    if self._embed_provider == "ollama":
        return self._ollama_embed(text)
    return self._gemini_embed(text)
```

This means swapping from local (Ollama/llama3.2:1b) to cloud (Gemini) requires only a `.env` change — no code change. This pattern is worth copying in your own projects.

```
LLM_PROVIDER=ollama   → uses local model, free, ~1.3 GB RAM, slower
LLM_PROVIDER=gemini   → uses cloud API, costs per token, faster, higher quality
```

#### 7.4 The Embedding Consistency Rule

The embedding model used at **seed time** must match the model used at **query time**. If they differ, the query vector and document vectors live in different spaces — similarity scores become meaningless.

```
EMBEDDING CONSISTENCY — critical requirement
──────────────────────────────────────────────────────────────────

SEED TIME (once)          QUERY TIME (every user question)
─────────────────         ──────────────────────────────────
nomic-embed-text          nomic-embed-text  ✓  same space → similarity works
nomic-embed-text          gemini-embedding  ✗  different space → garbage scores

If you switch providers after seeding, you MUST:
  1. Drop the policy_documents table
  2. Update the embedding column size (vector(768) → vector(3072) or vice versa)
  3. Re-seed all documents with the new model
```

The schema comment in TransitFlow makes this explicit:

```sql
-- databases/relational/schema.sql  lines 45–47
-- 768-dim  → Ollama nomic-embed-text (default)
-- 3072-dim → Gemini gemini-embedding-001
-- If you switch LLM_PROVIDER to gemini, change to vector(3072) and reset the database.
```

#### 7.5 When RAG Fails — and What to Do

| Symptom | Likely cause | Fix |
|---|---|---|
| "I don't have that information" (policy exists) | Threshold too high, or wrong embedding model | Lower threshold; verify model consistency |
| Correct document found, wrong answer | LLM hallucinating despite grounding | Strengthen grounding: "Answer only using the data above, nothing else." |
| Completely unrelated document retrieved | Threshold too low | Raise threshold; improve chunk boundaries |
| Question answered correctly but slowly | Too many documents embedded without HNSW index | `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)` |
| Embedding call fails at query time | Provider not running / API key missing | Check Ollama service / `.env` file |

#### 7.6 When NOT to Use RAG

RAG is for **unstructured knowledge** that cannot be efficiently queried by other means. For structured, queryable data — use a database directly.

```
USE RAG                                   USE SQL / GRAPH INSTEAD
──────────────────────────────────────    ────────────────────────────────────────
"What is the refund policy?"              "What is the fare for NR_SCH01?"
  → Policy text, varies by question         → Exact number in a table

"Can I bring my dog on the metro?"        "What seats are available on 2026-06-01?"
  → Conduct policy, fuzzy match              → Structured query on bookings

"What are my rights if a train is late?"  "Show me my booking history."
  → Multiple policies, semantic match        → Filtered query on national_rail_bookings

TransitFlow embeds policy documents.      TransitFlow queries PostgreSQL directly
It does NOT embed schedule data,          for schedules, fares, seats, bookings.
fare data, or booking records.
```

Embedding structured data you could query with SQL is wasteful and less accurate — SQL gives exact answers; vector search gives approximate matches.

#### 7.7 Prompt Debugging — Log What the LLM Actually Receives

The most common RAG bug is a mismatch between what you think you are sending and what the LLM actually reads. TransitFlow has a `debug=True` flag for exactly this:

```python
# skeleton/agent.py
answer, history, debug_info = agent(user_message, history, debug=True)
print(debug_info)   # prints the full prompt, retrieved chunks, and tool calls
```

Always verify the full prompt, not just your code. Bugs hide in the assembly step — the join between retrieved chunks and user message.

#### 7.8 Cost Awareness

| Operation | Cost profile | Notes |
|---|---|---|
| Embed all policy documents | One-time cost at seed time | ~10 documents × small cost |
| Embed each user query | Per-request cost | Charged every time a user asks something |
| LLM chat (input tokens) | Per-token cost | Includes system prompt + history + retrieved docs |
| LLM chat (output tokens) | Per-token cost | Usually more expensive than input |
| HNSW index traversal | Free (local CPU) | No API call; runs inside PostgreSQL |

Practical implication: long system prompts and long conversation histories are expensive. Trim history aggressively in production, or use a summary model to compress old turns.

---

### 8. What to Learn Next

#### 8.1 Deeper LLM Understanding

If you want to understand *how* transformers actually work — not just use them:

| Resource | What it teaches |
|---|---|
| "Attention is All You Need" (Vaswani et al., 2017) | The original transformer paper — readable with the right background |
| 3Blue1Brown "Neural Networks" series (YouTube) | Visual, mathematical intuition — no code required |
| Andrej Karpathy "Let's build GPT from scratch" (YouTube) | Build a working GPT in ~2 hours of code — the fastest way to internalize how it works |
| Sebastian Raschka "Build a Large Language Model From Scratch" (book) | Thorough, code-first textbook — Python throughout |

#### 8.2 Better RAG

TransitFlow uses the simplest possible RAG: embed whole documents, retrieve top-K, inject. Production systems go further:

| Technique | What it adds |
|---|---|
| **Hybrid search** | Combine keyword (BM25) + vector search — catches both exact matches and semantic matches |
| **Re-ranking** | A second model scores retrieved chunks for relevance before passing to the LLM |
| **Chunking strategies** | Split large documents at sentence/paragraph boundaries; add overlap |
| **Metadata filtering** | Filter by category before similarity search (e.g., only search "refund" category) |
| **HyDE** (Hypothetical Document Embedding) | Generate a hypothetical answer, embed it, then search — often retrieves better chunks |
| **LangChain / LlamaIndex** | Python frameworks that implement all of the above with less boilerplate |

#### 8.3 Evaluating Your RAG

How do you know if your RAG is working? You measure it:

| Metric | What it measures | How to calculate |
|---|---|---|
| **Retrieval recall** | Are the right documents being returned? | Human-labelled set of questions → check if ground-truth doc in top-K |
| **Answer faithfulness** | Does the LLM answer from the retrieved context (not hallucinate)? | LLM-as-judge: "does this answer contradict the context?" |
| **Answer relevance** | Does the answer address the question? | LLM-as-judge or human evaluation |

The RAGAS library (Python) automates these evaluations.

#### 8.4 Fine-tuning vs RAG — When to Choose Each

```
USE RAG WHEN:                          USE FINE-TUNING WHEN:
──────────────────────────────────     ──────────────────────────────────
Data changes frequently               Data is stable for months/years
You need audit trails                 You need the model to adopt a
You have a small document corpus        specific style or tone
You cannot afford GPU training        You have thousands of labelled
You want to get started quickly         examples and GPU access
The data is proprietary                 and weeks of experimentation
                                       The LLM needs to learn a
                                         new domain vocabulary
```

In practice, RAG is the right starting point for almost all business applications. Fine-tune only after RAG is in production and you have identified specific failure modes that more training data would fix.

#### 8.5 The Agent Pattern — Extending What TransitFlow Already Does

TransitFlow is already an agent: it uses tool calling to route questions to different databases, executes tools, and synthesises answers. The next steps are:

- **Multi-step reasoning**: let the LLM call multiple tools in sequence, where the output of one informs the input to the next
- **Planning**: ask the LLM to produce a plan before executing any tools
- **Memory**: store summaries of past conversations to give the LLM context across sessions
- **Feedback loops**: let the LLM evaluate its own answer and retry if it is uncertain

#### 8.6 Suggested Learning Path

```
BEGINNER (start here)
──────────────────────────────────────────────────────────────────
□ Understand tokens, embeddings, and cosine similarity  ← this tutorial
□ Use the TransitFlow agent; trace a query end-to-end
□ Add a new policy document to policy_documents; verify it is retrieved
□ Change the similarity threshold; observe the effect
□ Write a simple RAG script with llm.embed() + query_policy_vector_search()

INTERMEDIATE
──────────────────────────────────────────────────────────────────
□ Add a new tool to the agent (e.g., weather lookup via an API)
□ Implement hybrid search: combine BM25 + pgvector in one query
□ Implement metadata filtering: only search within a category
□ Add conversation summarisation to compress history
□ Measure retrieval recall on a labelled test set

ADVANCED
──────────────────────────────────────────────────────────────────
□ Build Karpathy's GPT from scratch — understand attention fully
□ Run fine-tuning on a dataset relevant to a domain project
□ Implement a multi-step agent with planning (ReAct pattern)
□ Deploy a RAG system with caching, monitoring, and cost tracking
□ Evaluate answer faithfulness with an LLM-as-judge pipeline
```

---

## Quick Reference

### Key Vocabulary

| Term | One-line definition |
|---|---|
| **LLM** | A model trained to predict the next token; understands and generates language |
| **Token** | The unit an LLM reads — a subword fragment, not a full word |
| **Context window** | Maximum tokens the LLM can process in one call |
| **Embedding** | A list of numbers representing the meaning of a piece of text |
| **Cosine similarity** | Measure of how aligned two vectors are (1 = identical direction, 0 = unrelated) |
| **RAG** | Retrieval-Augmented Generation — retrieve relevant facts, inject into prompt, generate answer |
| **Hallucination** | When an LLM generates plausible-sounding but factually incorrect content |
| **Grounding** | Supplying factual data in the prompt so the LLM's answer is anchored to it |
| **Chunking** | Splitting documents into pieces before embedding |
| **HNSW** | Approximate nearest-neighbour index for fast vector similarity search |
| **Fine-tuning** | Retraining model weights on new data — expensive, powerful, brittle |
| **Tool calling** | LLM selects a function to call based on the user's intent; agent executes it |
| **System prompt** | Persistent instructions prepended to every conversation turn |

### TransitFlow File Map

| File | What it shows |
|---|---|
| `skeleton/config.py` | LLM provider, embedding model, dimensions, RAG settings |
| `skeleton/llm_provider.py` | How `embed()` and `chat()` call the LLM API |
| `skeleton/agent.py` | System prompt, tool-selection prompt, RAG pipeline, context injection |
| `skeleton/seed_vectors.py` | How policy documents are built, embedded, and stored |
| `databases/relational/schema.sql` | `policy_documents` table definition and HNSW index |
| `databases/relational/queries.py` | `query_policy_vector_search()` — the pgvector cosine search |
