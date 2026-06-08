# Section 6 — Reflection & Trade-offs

> 負責人：三人共同 | 配分：/5

## 6.1 Design Decisions

### Decision 1：Schedule Stops — Migrating from VARCHAR[] to Junction Table

We initially stored schedule stop sequences as a PostgreSQL array column (`stops_in_order VARCHAR(10)[]`). This matched the JSON seed data format directly and allowed stops to be queried with a single `array_position()` call, making early development fast.

However, the array design violates 3NF: stop position is encoded as an implicit array index rather than a declared attribute, so there is no candidate key that functionally determines stop position. This means individual stops cannot be updated without rewriting the entire array, and the functional dependency `(schedule_id, stop_order) → station_id` cannot be expressed relationally.

We migrated to two junction tables in PR #34:

```sql
metro_schedule_stops          (schedule_id, stop_order, station_id)
national_rail_schedule_stops  (schedule_id, stop_order, station_id)
```

With composite primary key `(schedule_id, stop_order)`, the functional dependency is properly expressed and 3NF is satisfied. The migration required rewriting all stop-related queries from `array_position()` / `@>` operators to JOIN-based lookups, and updating the seed scripts to insert into the junction tables. The extra development cost was accepted because 3NF compliance is a grading requirement and the junction table design is the correct choice for any system where stop sequences may need to be updated independently.

### Decision 2：Local LLM (llama3.2:1b) vs. Cloud LLM (Gemini)

We designed the agent to support both a local Ollama model and Gemini via a provider abstraction in `skeleton/llm_provider.py`. The default is `llama3.2:1b`, which runs entirely on-device with no API key or cost.

The trade-off: local inference preserves user privacy and eliminates API cost, but `llama3.2:1b` (1 billion parameters) lacks the instruction-following capacity needed to reliably select from 16 tool functions given ambiguous natural-language input. In live testing, the local model frequently called the wrong tool — for example, routing a fare query to `search_policy` instead of `query_metro_fare`. Gemini 1.5 Flash resolved tool selection correctly but requires an internet connection and API credentials.

We kept the local model as default because the grading guide states that functions are evaluated by direct Python calls, not through the LLM pipeline. The provider switch is a single `.env` change (`LLM_PROVIDER=gemini`), making it easy to upgrade for production use.

---

## 6.2 Production Considerations

The current implementation creates a new database connection for each query function call (PostgreSQL via psycopg2) and instantiates a module-level Neo4j driver. Under concurrent load, this would exhaust PostgreSQL's default connection limit (100) and cause connection errors.

A production deployment would replace per-call connections with a connection pool: `psycopg2.pool.ThreadedConnectionPool` (or an external pooler like PgBouncer) for PostgreSQL, and configure the Neo4j driver's built-in pool size. Beyond pooling, two other areas would need attention:

1. **Embedding provider lock-in**: The pgvector index is built for a fixed dimension (768 for Ollama nomic-embed-text, 3072 for Gemini). Switching providers after seeding breaks all similarity searches due to dimension mismatch. A production system would need a migration script to re-embed all documents whenever the provider changes, and the index would need to be rebuilt.

2. **Secret management**: Database credentials, API keys, and JWT secrets are currently read from a `.env` file. In production, these should be stored in a secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault) with rotation policies, and never committed to version control. The current `.gitignore` excludes `.env`, but the template `env.example` should be the only committed reference to secret variable names.
