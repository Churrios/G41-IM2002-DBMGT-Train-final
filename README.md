# TransitFlow — Intelligent Rail Assistant

## For marking schemes and what to submit for your final project, please refer to [https://github.com/NCUIM-Lab710-Teaching/IM2002-grading-students/](https://github.com/NCUIM-Lab710-Teaching/IM2002-grading-students/tree/main).

---

## Table of Contents

1. [What Is This Project?](#what-is-this-project) — overview of TransitFlow and what you will build
2. [The Three Databases](#the-three-databases--and-why-each-one) — why PostgreSQL, pgvector, and Neo4j are each used
3. [How Does It Actually Work?](#how-does-it-actually-work--the-full-pipeline) — end-to-end pipeline walkthrough with a real example, including the LLM normalisation step and a RAG explainer
4. [Prerequisites](#prerequisites) — Docker, Python, and LLM requirements
5. [Setup](#setup-do-this-once) — one-time installation and startup steps (includes virtual environment instructions)
6. [Browse the Databases](#browse-the-databases) — log into pgAdmin and Neo4j Browser to inspect your data
7. [Working as a Team](#working-as-a-team) — keeping database state in sync across teammates
8. [Try These Queries](#try-these-queries) — sample questions to verify everything is working
9. [Project Structure](#project-structure) — file and folder layout at a glance
10. [Real-World vs Educational Structure](#how-this-structure-differs-from-a-real-production-application) — how this project differs from a production codebase, and why
11. [The databases/ Folder](#the-databases-folder--plug-and-play-components) — what to edit in each module and how changes take effect
12. [Raw Data](#raw-data--study-these-before-designing-the-databases) — source files to study before designing your schema
13. [Your Tasks](#your-tasks) — the four course tasks you need to complete
14. [Advanced — Extending the Agent or UI](#advanced--extending-the-agent-or-ui) — adding tools to the agent or modifying the UI (proceed with care)
15. [Switching Between Ollama and Gemini](#switching-between-ollama-and-gemini) — how to change the LLM provider and what to do after switching
16. [Useful URLs](#useful-urls-when-docker-is-running) — quick reference for local service addresses
17. [Troubleshooting](#troubleshooting) — common errors and how to fix them
18. [Python Virtual Environments](#python-virtual-environments) — what venv is, why to use it, and how to set it up

---

## What Is This Project?

TransitFlow is a working AI chat assistant for a fictional dual-network transit operator. You can type questions like:

- *"Are there any trains from Central Station (NR01) to Ferndale (NR07) today?"*
- *"My train was delayed 45 minutes — what compensation am I entitled to?"*
- *"What's the quickest metro route from MS01 to MS09 if MS05 is closed?"*

The assistant answers by **querying three different types of database** and combining the results into a helpful reply. Your task is to understand those databases, study the raw data, design the schema, populate the databases, and extend them.

---

## The Three Databases — and Why Each One

This project is designed to show *when* you'd reach for each database type — and *why* one type isn't enough.

| Database | What It's Best At | What It Stores in TransitFlow |
|---|---|---|
| **PostgreSQL** (Relational) | Structured records with exact relationships — numbers, dates, foreign keys | Metro and national rail stations, schedules, seat layouts, fares, users, national rail bookings, metro trips, payments |
| **PostgreSQL + pgvector** (Vector) | Finding documents by *meaning*, not exact words | Company policy documents — refund rules, railcard guides, accessibility info |
| **Neo4j** (Graph) | Finding paths and connections through a network | The physical rail network — stations as nodes, rail links as edges |

**Why can't we just use one database?** No single database type does everything well:

- SQL is great for *"How many seats are left on the 07:00 NR1 service (NR_SCH01)?"* but awkward for *"What's the fastest route from London to Exeter, changing at any station?"*
- A graph database handles route-finding naturally — that's exactly what it's designed for — but it can't do the maths needed for smart document search.
- A vector database can find the right refund policy even if the user asks in an unexpected way, matching by *meaning* rather than keywords. But it can't manage seat bookings.

Using three databases isn't over-engineering. It's picking the right tool for each job.

---

## How Does It Actually Work? — The Full Pipeline

Here is exactly what happens from the moment a user sends a message to the moment they see an answer. We'll trace a real example end to end.

> **User types:** *"I was on the 07:00 from Central (NR01) to Stonehaven (NR05) on 2026-04-02 and it was delayed 45 minutes. Can I get compensation?"*

---

### Step 1 — The question arrives at the web interface

The user types into a Gradio chat interface (the code for this lives in `skeleton/ui.py`). The message is handed to the agent.

---

### Step 2 — The LLM reads the question and picks which databases to query

`skeleton/agent.py` sends the question to an **LLM** (Large Language Model — the AI brain, either Google Gemini or a local Ollama model). The LLM is shown a list of available **tools** — think of tools as labelled buttons, each connected to a database query function. The LLM decides which buttons to press.

For this question, the LLM selects:

```
Tool 1: get_user_bookings()
Tool 2: search_policy(query="compensation for delayed train 45 minutes")
```

This technique — letting the LLM choose which functions to call — is called **tool use** or **function calling**. The LLM doesn't query the database itself; it just issues instructions that the Python code then executes.

> **Ollama vs Gemini tool routing:** When using Ollama, the agent uses the model's native tool-calling API (`ollama_tool_call` in `llm_provider.py`), which is more reliable than asking a small model to produce JSON. When using Gemini, the agent sends a structured JSON routing prompt. Both paths produce the same list of tool calls.

> **Login-aware routing:** If a user is logged in, the agent injects their name, email, and user ID into the system prompt. Auth-gated tools (`get_user_bookings`, `make_booking`, `cancel_booking`) use the logged-in identity automatically — the LLM never needs to ask the user for their email or ID.

---

### Step 3 — The tools query the real databases

Each tool maps to a Python function in `databases/relational/queries.py` or `databases/graph/queries.py`:

**`get_user_bookings`** → runs SQL against the `national_rail_bookings` table in PostgreSQL

```sql
SELECT b.booking_id, b.travel_date, b.departure_time::text,
       b.amount_usd, b.status,
       orig.name AS origin_name, dest.name AS destination_name, ...
FROM national_rail_bookings b
JOIN national_rail_stations orig ON orig.station_id = b.origin_station_id
JOIN national_rail_stations dest ON dest.station_id = b.destination_station_id
WHERE b.user_id = 'RU01'
ORDER BY b.travel_date DESC
```

Returns raw JSON: *`[{"booking_id": "BK001", "travel_date": "2026-04-02", ...}]`*

**`search_policy`** → converts the question to a vector, then runs a similarity search against `policy_documents` in PostgreSQL (pgvector)

```sql
SELECT title, content,
       1 - (embedding <=> '[...query vector...]') AS similarity
FROM policy_documents
ORDER BY similarity DESC
LIMIT 3
```

Returns raw JSON: *`[{"title": "Delay Compensation Policy", "content": "RF005: 30–59 minutes...", ...}]`*

---

### Step 4 — Raw results are normalised to structured readable text

The raw JSON from every tool is passed through a **Python flattener** (`_normalise_result` in `agent.py`) that recursively converts any JSON structure to indented key-value text. For example, Alice's booking result becomes:

```
[get_user_bookings]
national_rail:
  [1]
    booking_id: BK020
    travel_date: 2026-05-13
    origin_name: Bridgeport
    destination_name: Central Station
    fare_class: standard
    amount_usd: 4.00
    status: confirmed
  [2]
    booking_id: BK001
    ...
metro:
  [1]
    trip_id: MT009
    ...
```

This normalisation step is why **you do not need to write any formatting code when adding new tools** — the flattener handles any JSON structure automatically, regardless of nesting depth or field names. It uses pure Python with no LLM involved, so there is no risk of the model hallucinating, corrupting, or dropping records during conversion.

---

### Step 5 — The LLM composes the final answer

The LLM reads the normalised data summary and the original question, then writes the final reply:

> *"I can see your booking BK001 for the 07:00 NR01 → NR05 on 2 April 2026 ($8.50). Under the Delay Compensation Policy (RF005), a 30–59 minute delay entitles you to a 50% refund of the fare — that's $4.25 back. You can submit a claim within 28 days via the app under 'My Journeys → Claim Compensation', or by contacting customer service."*

---

### Step 6 — The answer is displayed

The reply is returned to `skeleton/ui.py` and shown in the chat window.

---

### Pipeline Summary Diagram

```
User types a question
        │
        ▼
  skeleton/ui.py  (Gradio web chat — handles login/register state)
        │  current_user_email passed on every message
        ▼
  skeleton/agent.py  ◄──────────────────────── LLM (Gemini or Ollama)
        │                                               ▲  ▲  ▲
        │   [1] LLM reads question +                    │  │  │
        │       login context, picks tools ─────────────┘  │  │
        │   [2] Agent executes tools                        │  │
        │       against real databases                      │  │
        │   [3] Python flattener normalises ─────────────────┘  │
        │       raw JSON to readable text                       │
        │   [4] LLM writes the final answer ────────────────────┘
        │       using normalised data
        │
        ├── databases/relational/queries.py ──► PostgreSQL (port 5433)
        │                                          ├── Relational tables
        │                                          │     metro_stations, national_rail_stations,
        │                                          │     schedules, seat_layouts, users,
        │                                          │     national_rail_bookings, metro_travels
        │                                          └── Vector table
        │                                                policy_documents  (searched by meaning)
        │
        └── databases/graph/queries.py ─────► Neo4j (port 7688)
                                                 └── Graph network
                                                       MetroStation / NationalRailStation nodes,
                                                       METRO_LINK / RAIL_LINK / INTERCHANGE_TO edges
                                                       (route finding, delay ripple)
```

---

### What Is RAG? (How the Policy Search Works)

The policy document search uses a technique called **RAG — Retrieval-Augmented Generation**:

1. When the database is seeded, each policy document is converted into a long list of numbers called a **vector embedding**. These numbers capture the *meaning* of the text mathematically.
2. When a user asks a policy question, that question is also converted into a vector — using the same method.
3. The database finds the policy documents whose vectors are *closest* (most similar) to the question's vector.
4. Those documents are handed to the LLM, which reads them and uses them to answer the question.

The key benefit: it finds the right policy even if the user's wording is completely different from the document's wording, because it's matching meaning rather than keywords.

---

## Prerequisites

- **Git** — [git-scm.com/downloads](https://git-scm.com/downloads)
  > Required to clone the repository. Pre-installed on most macOS and Linux systems. Windows users should download and run the Git installer.
- **Docker Desktop** — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop)
  > Docker runs the databases without you having to install PostgreSQL or Neo4j directly. Think of it as a clean, self-contained box that holds the database servers.
  > **Windows users:** Docker Desktop requires WSL2 (Windows Subsystem for Linux 2). Follow [Docker's WSL2 setup guide](https://docs.docker.com/desktop/wsl/) if you have not enabled it yet.
- **Python 3.10 or newer** — [python.org/downloads](https://www.python.org/downloads/)
  > On **Windows**, the command is `python`. On **macOS and Linux**, it is typically `python3`. Throughout this README, use whichever works on your machine.
- **An LLM — pick one:**
  - **Ollama** (recommended — runs entirely on your laptop, no API key needed): [ollama.com/download](https://ollama.com/download)
  - **Gemini** (alternative — faster responses, but requires a free API key): [aistudio.google.com](https://aistudio.google.com/app/apikey)

---

## Setup (Do This Once)

> **Recommended:** Run this project inside a Python virtual environment. It keeps the project's packages isolated from everything else on your machine and prevents version conflicts. It is not required, but it is good practice and the approach used by most professional Python developers. See [Python Virtual Environments](#python-virtual-environments) at the bottom of this file for a full explanation of why.

### 1. Clone the repository, create a virtual environment, and install Python packages

```bash
git clone https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-final transitflow
cd transitflow
```

**Recommended — create and activate a virtual environment first:**

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

> **Windows PowerShell note:** If activation fails with "running scripts is disabled on this system", run this once in PowerShell and then retry:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Your terminal prompt will change to show `(.venv)` when the environment is active. Now install the project's packages into it:

```bash
pip install -r requirements.txt
```

> If you choose not to use a virtual environment, run `pip install -r requirements.txt` directly. Be aware this installs packages into your system Python, which can cause conflicts with other projects.

### 2. Create your environment file

```bash
cp .env.example .env
```

The default provider is **Ollama** — no API key needed. If you want to use Gemini instead, open `.env` and set `LLM_PROVIDER=gemini`, then paste your `GEMINI_API_KEY`.

### 3. Start the databases

```bash
docker compose up -d
```

This downloads and starts three services in the background:
- **PostgreSQL** on port 5433 — the relational + vector database
- **Neo4j** on port 7688 — the graph database
- **pgAdmin** on port 5051 — browser-based UI for browsing and querying PostgreSQL

The relational database schema (tables and indexes) is loaded automatically from `databases/relational/schema.sql` on first start. Seed data is loaded separately in the next step.

> **On first run**, Docker must also download the database images (~500 MB total). This can take several minutes depending on your connection. On subsequent starts, both containers are ready in 15–30 seconds.
>
> **Older Docker installs:** If `docker compose` is not recognised, try `docker-compose` (with a hyphen). Updating Docker Desktop to the latest version is recommended.

Wait until both containers are ready:

```bash
docker compose ps
```

Both containers should show `healthy` in the Status column.

### 4. Seed the relational database

> **Your task:** before running this step, you need to implement the seed functions inside `skeleton/seed_postgres.py`. The connection setup and helper functions are already provided — you write the body of each `seed_*` function. See [Your Tasks — Writing Your Seeding Scripts](#writing-your-seeding-scripts) for guidance and examples.

Once implemented:

```bash
# macOS / Linux:
python3 skeleton/seed_postgres.py

# Windows (PowerShell):
python skeleton/seed_postgres.py
```

This reads all mock data from the `train-mock-data/` folder and inserts it into PostgreSQL in dependency order: stations → schedules → seat layouts → users → bookings → trips → payments → feedback. It uses `ON CONFLICT DO NOTHING`, so it is safe to re-run.

### 5. Pull Ollama models and load the policy document embeddings

If you are using Ollama (the default), make sure Ollama is running and pull the required models first — this only needs to be done once:

```bash
ollama pull llama3.2:1b        # ~1.3 GB  — chat model
ollama pull nomic-embed-text   # ~274 MB  — embedding model for pgvector
```

Then seed the vector database:

```bash
# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

This loads the policy documents directly from the JSON files in `train-mock-data/` (`refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json`), converts each entry into a vector embedding using Ollama (`nomic-embed-text`), and stores the result in PostgreSQL.

> If you are using Gemini instead of Ollama, set `LLM_PROVIDER=gemini` and add your `GEMINI_API_KEY` to `.env` before running this. You do not need to pull Ollama models.

### 6. Load the transit network graph

```bash
# macOS / Linux:
python3 skeleton/seed_neo4j.py

# Windows (PowerShell):
python skeleton/seed_neo4j.py
```

This runs the Cypher queries in `databases/graph/seed.cypher`, creating all the station nodes and rail link edges in Neo4j. The graph topology encoded in that file is derived from `train-mock-data/metro_stations.json` and `train-mock-data/national_rail_stations.json` — study those files if you need to extend or correct the graph.

### 7. Launch the assistant

```bash
# macOS / Linux:
python3 skeleton/ui.py

# Windows (PowerShell):
python skeleton/ui.py
```

Open **http://localhost:7860** in your browser. The TransitFlow chat interface should appear.

---

## Browse the Databases

Once the Docker containers are running you can inspect your data directly in the browser — useful for verifying that seeding worked and for running ad-hoc queries while you develop.

### pgAdmin — PostgreSQL browser

1. Open **http://localhost:5051** in your browser.
2. Log in with:
   - **Email:** `admin@admin.com`
   - **Password:** `admin`
3. In the left sidebar, right-click **Servers → Register → Server…**
4. Fill in the two tabs:

   **General tab**
   - Name: `TransitFlow` (or any label you like)

   **Connection tab**
   - Host: `postgres`
   - Port: `5432`
   - Maintenance database: `transitflow`
   - Username: `transitflow`
   - Password: `transitflow`
   - Tick **Save password**

5. Click **Save**. The server appears in the left sidebar.
6. Expand **Servers → TransitFlow → Databases → transitflow → Schemas → public → Tables** to browse all tables.
7. To run a SQL query, right-click the `transitflow` database and choose **Query Tool**.

> **Why port 5432 here and not 5433?** pgAdmin runs inside Docker and talks to PostgreSQL over the internal Docker network, where Postgres is on its native port 5432. Port 5433 is only used when connecting from outside Docker (e.g. from your terminal or a local Python script).

---

### Neo4j Browser — graph visualiser

1. Open **http://localhost:7475** in your browser.
2. Set the connect URL to `bolt://localhost:7688` (the Bolt port is remapped from the default 7687).
3. Log in with:
   - **Username:** `neo4j`
   - **Password:** `transitflow`
4. To visualise the entire rail network, paste this query and press **Run (Ctrl+Enter)**:

   ```cypher
   MATCH (n)-[r]->(m) RETURN n, r, m
   ```

   Click any node or edge in the graph to inspect its properties.

---

## Try These Queries

Paste these into the chat to confirm everything is working:

```
What national rail trains run from Central (NR01) to Stonehaven (NR05)?
```
→ Tests PostgreSQL relational (`check_national_rail_availability` against `national_rail_schedules`)

```
What is the fastest metro route from MS01 to MS14?
```
→ Tests Neo4j (Dijkstra by `travel_time_min` through the metro graph)

```
How do I get from Central Square (MS01) to Stonehaven (NR05)?
```
→ Tests Neo4j cross-network routing (METRO_LINK → INTERCHANGE_TO → RAIL_LINK)

```
If Old Town station (NR03) is closed, what alternative routes exist from NR01 to NR05?
```
→ Tests Neo4j (alternative routing, avoiding a specific node)

```
My train was delayed 45 minutes — what compensation am I entitled to?
```
→ Tests pgvector RAG (delay compensation policy RF005)

```
What is the company policy on travelling with a bicycle on national rail?
```
→ Tests pgvector RAG (travel policies document — bikes, luggage, pets)

**Auth-aware queries — log in first (use the Register or Login button in the top-right corner):**

```
Show my bookings
```
→ Tests `get_user_bookings` — returns your booking history from PostgreSQL (empty for a newly registered user)

```
Book me a standard ticket from Central Station (NR01) to Stonehaven (NR05) on 2026-06-01
```
→ Tests the multi-step booking flow: `check_national_rail_availability` → `get_available_seats` → `make_booking`

```
Cancel booking BK-XXXXXX
```
→ Tests `cancel_booking` with automatic refund calculation per the applicable policy

Enable **"Show database debug panel"** in the UI sidebar to see exactly which tools were called, what the databases returned, and how the LLM normalised the raw results.

---

## Project Structure

```
transitflow/
├── docker-compose.yml                  # Starts PostgreSQL + Neo4j + pgAdmin
├── requirements.txt
├── .env.example                        # Copy to .env and fill in your API key
│
├── train-mock-data/                    #   Source JSON files — study before designing schemas
│   ├── metro_stations.json
│   ├── national_rail_stations.json
│   ├── metro_schedules.json
│   ├── national_rail_schedules.json
│   ├── registered_users.json
│   ├── bookings.json
│   ├── metro_travel_history.json
│   ├── payments.json
│   ├── feedback.json
│   └── ...                             #   (policy JSON files)
│
├── databases/                          # ← YOUR WORKING AREA
│   ├── relational/
│   │   ├── schema.sql                  # ← EDIT THIS: table definitions (DDL only)
│   │   └── queries.py                  # ← EDIT THIS: add new SQL query functions
│   │
│   ├── graph/
│   │   ├── seed.cypher                 # ← EDIT THIS: graph nodes and relationships
│   │   └── queries.py                  # ← EDIT THIS: add new Cypher query functions
│   │
│   └── vector/
│       └── documents.py                #   (deprecated — no longer used)
│
└── skeleton/                           # ← DO NOT EDIT (unless you know what you're doing)
    ├── agent.py                        #   LLM orchestration and tool routing
    ├── ui.py                           #   Gradio web interface
    ├── llm_provider.py                 #   LLM abstraction (Gemini / Ollama)
    ├── config.py                       #   Environment config (reads .env)
    ├── seed_postgres.py                #   Loads train-mock-data/ JSON files into PostgreSQL
    ├── seed_neo4j.py                   #   Runs databases/graph/seed.cypher (graph data derived from train-mock-data/ station JSONs)
    └── seed_vectors.py                 #   Embeds train-mock-data/ policy JSONs into pgvector
```

---

## How This Structure Differs from a Real Production Application

The folder layout in this project is deliberately simplified for learning. Understanding how it differs from a real codebase — and why — will help you make sense of both worlds.

### What a production codebase would look like

In a real system built on three databases, the query code would live next to the feature it belongs to, not grouped by database type. A typical Python service might look like this:

```
transitflow/
├── api/                          # HTTP layer — FastAPI or Django REST
│   ├── routes/
│   │   ├── bookings.py           # POST /bookings, GET /bookings/{id}
│   │   ├── routes.py             # GET /routes?from=LDN&to=BRS
│   │   └── policies.py           # GET /policies/search?q=...
│   └── middleware/
├── services/                     # Business logic, no database knowledge here
│   ├── booking_service.py
│   ├── routing_service.py
│   └── policy_service.py
├── repositories/                 # One file per database concern
│   ├── postgres/
│   │   ├── bookings_repo.py      # SQL for bookings and users
│   │   └── pricing_repo.py
│   ├── neo4j/
│   │   └── network_repo.py       # Cypher for route finding
│   └── vector/
│       └── policy_repo.py        # pgvector similarity search
├── migrations/                   # Incremental schema changes (Alembic / Flyway)
│   ├── 001_initial_schema.sql
│   ├── 002_add_loyalty_points.sql
│   └── 003_add_operators_table.sql
├── tests/
│   ├── unit/
│   └── integration/              # Tests hit real (test) databases
├── infrastructure/               # Docker, Kubernetes, Terraform
└── config/
    ├── settings_dev.py
    ├── settings_staging.py
    └── settings_prod.py          # Secrets loaded from Vault / AWS Secrets Manager
```

Key differences from this project:

| Aspect | This project | Production practice |
|---|---|---|
| **Schema changes** | Edit `schema.sql`, then `docker compose down -v` to wipe and recreate | Migration files — one file per change, applied incrementally without data loss |
| **Query code location** | Grouped by database type (`databases/relational/`, `databases/graph/`) | Grouped by business domain (`repositories/bookings/`, `repositories/routing/`) |
| **Seeding data** | Manual scripts run by hand | Handled by CI pipelines or a dedicated seed/fixture framework |
| **Configuration** | One `.env` file | Separate config per environment (dev/staging/prod); secrets managed by a vault, never in files |
| **Web interface** | Gradio — one Python file, zero frontend code | A dedicated frontend (React, Vue) communicating with a REST or GraphQL API |
| **The agent** | A single `agent.py` | Likely a separate microservice or a managed AI platform (e.g. AWS Bedrock, Google Vertex AI) |
| **LLM provider** | Switched via an environment variable | Abstracted behind a versioned API contract; model upgrades go through a staged rollout |
| **Testing** | Manual — run the app and type queries | Automated unit, integration, and end-to-end tests run in CI on every commit |

### Why this project uses a simpler structure

The goal of this project is to teach you **when and why** to reach for each database type — not to teach software architecture. Every structural decision was made to keep that focus sharp:

- **`databases/` groups by database type, not by feature** — so each folder is a focused, standalone learning unit. You can work on the relational database without touching the graph or vector code.
- **One `schema.sql` file instead of migrations** — migrations are the right tool in production, but they add a layer of indirection. A single file lets you see the entire data model at a glance and reason about it as a whole.
- **`skeleton/` contains all pre-built code** — the boundary is intentional. It tells you exactly what you are responsible for and frees you from needing to understand the LLM orchestration or UI code before you can start working with the databases.
- **Gradio instead of a full API + frontend** — a production UI would take days to set up. Gradio gets you to a working, interactive interface in a single command, so the focus stays on the databases.
- **Manual seed scripts instead of a migration/fixture framework** — running `python skeleton/seed_vectors.py` yourself makes the seeding process visible and debuggable. In production this would be hidden inside a deployment pipeline, which is harder to learn from.

When you leave this course and build real systems, you will naturally outgrow these simplifications. The structure here is a teaching scaffold — useful precisely because it keeps things visible and separated, even if that is not how you would organise a system you were shipping to users.

We have also provided side notes for production practices for the three databases - relational, vector and graph database. [Find them under project root]

- Relational Database: [SideNote1-RelationalDBPractices.md](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/blob/master/SideNote1-RelationalDBPractices.md)
- Vector Database: [SideNote2-VectorDBPractices.md](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/blob/master/SideNote2-VectorDBPractices.md)
- Graph Database: [SideNote3-GraphDBPractices.md](https://github.com/NCUIM-Lab710-Teaching/IM2002-DBMGT-Train-v2/blob/master/SideNote3-GraphDBPractices.md) 
---

## The databases/ Folder — Plug-and-Play Components

Each subfolder inside `databases/` is a self-contained component. The AI pipeline in `skeleton/` imports from them automatically — you only need to modify files inside `databases/` to extend what the assistant can do.

Think of each database folder as a **plug-and-play module**:

| Folder | What you control | How changes take effect |
|---|---|---|
| `databases/relational/` | The SQL schema and query functions | Edit `schema.sql`, then reset the database (see below). Edit `queries.py` to add new Python query functions. |
| `databases/graph/` | The graph topology and Cypher queries | Edit `seed.cypher` to add nodes and edges (data sourced from `train-mock-data/` station JSONs). Edit `queries.py` to add new Cypher query functions. |
| `databases/vector/` | The policy documents the assistant knows about | Edit the policy JSON files in `train-mock-data/` to add or update documents, then re-run the seed script. |

### Relational database (PostgreSQL)

**File to edit:** `databases/relational/schema.sql`

This file defines all tables and indexes (DDL only — no data). Study the JSON files in `train-mock-data/` first to understand the data model. Seed data is loaded separately by `skeleton/seed_postgres.py`.

Extension ideas:
- Add a `delay_records` table to log operator-reported delays per service
- Add a `season_tickets` table for weekly, monthly, and annual metro passes
- Add a `platform_assignments` table — which platform each service departs from
- Add a `loyalty_points` column to the `users` table
- Add a `disruptions` table for planned engineering works

After any schema changes, reset and reload the database:
```bash
docker compose down -v && docker compose up -d
```

**File to edit:** `databases/relational/queries.py`

Add new Python functions here following the existing patterns. Any function prefixed with `query_` can be registered as a tool in the agent (see the Advanced section below).

---

### Graph database (Neo4j)

**File to edit:** `databases/graph/seed.cypher`

This Cypher file creates all `MetroStation` and `NationalRailStation` nodes, plus `METRO_LINK`, `RAIL_LINK`, and `INTERCHANGE_TO` edges. Study `train-mock-data/metro_stations.json` and `train-mock-data/national_rail_stations.json` to understand the network topology.

Extension ideas:
- Add `BUS_LINK` relationship type connecting bus stops to metro or rail stations
- Add more metro stations and extend existing lines
- Add zone properties to nodes (zone 1, 2, 3) for zone-based fare calculation
- Add an `OPERATED_BY` relationship linking stations to operators
- Add a `CLOSED` property to nodes for live disruption modelling

After editing the Cypher seed file:
```bash
# macOS / Linux:
python3 skeleton/seed_neo4j.py

# Windows (PowerShell):
python skeleton/seed_neo4j.py
```

**File to edit:** `databases/graph/queries.py`

Add new Cypher query functions here following the existing patterns.

---

### Vector database (pgvector / RAG)

**Files to edit:** the policy JSON files in `train-mock-data/` (`refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json`).

Add new entries following the existing structure in each file.

Extension ideas:
- Lost property policy
- Group booking discounts (10+ passengers on national rail)
- Accessibility and assisted travel
- Engineering works and planned disruption
- Penalty fares and fare evasion

After adding or changing documents:
```bash
# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

> If you switch providers (Ollama ↔ Gemini) after seeding, you must re-run the seed script (`python3 skeleton/seed_vectors.py` on macOS/Linux, `python skeleton/seed_vectors.py` on Windows). The embedding model changes with the provider — stored vectors will no longer match queries made with the new model.

---

## Raw Data — Study These Before Designing the Databases

All source data lives in the `train-mock-data/` folder as structured JSON files. Study these files before starting your schema or graph design tasks.

| File | What It Contains |
|---|---|
| `metro_stations.json` | 20 metro stations (MS01–MS20), lines, interchange flags, adjacent station lists |
| `national_rail_stations.json` | 10 national rail stations (NR01–NR10), lines, interchange links to metro |
| `metro_schedules.json` | Metro timetables for lines M1–M4: stops, fares, frequencies, operating days |
| `national_rail_schedules.json` | National rail timetables for NR1–NR2: normal and express services, fare classes |
| `national_rail_seat_layouts.json` | Coach and seat maps for each national rail schedule |
| `registered_users.json` | 20 fictional users with profile and authentication fields |
| `bookings.json` | National rail booking history across all users |
| `metro_travel_history.json` | Metro trip history (single tickets and day passes) |
| `payments.json` | Payment records for both national rail and metro transactions |
| `feedback.json` | Passenger ratings and comments |
| `refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` | Policy documents embedded into pgvector for RAG. Edit these files to extend the assistant's knowledge, then re-run `seed_vectors.py`. |

**Questions to ask yourself as you study the data:**

- Which fields repeat across many records? Those are candidates for their own table.
- What uniquely identifies each record — what is the natural primary key?
- How do records relate to each other? Those relationships become foreign keys.
- Which station connections are best represented as a *network* rather than a table of rows?
- Which policy content needs to be searched by *meaning* rather than exact keywords?

---

## Your Tasks

**Required — you must edit these files to complete the project:**

| File | What to do |
|---|---|
| `skeleton/seed_postgres.py` | Implement each `seed_*` function to load JSON data into your PostgreSQL tables |
| `skeleton/seed_neo4j.py` | Implement the `seed()` function to create station nodes and rail link relationships in Neo4j |
| `databases/relational/schema.sql` | Design and write the table definitions (DDL) for all relational data |
| `databases/relational/queries.py` | Add Python functions that query your PostgreSQL tables |
| `databases/graph/seed.cypher` | Define the graph topology — station nodes and the links between them |
| `databases/graph/queries.py` | Add Python functions that run Cypher queries against Neo4j |
| `train-mock-data/refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` | Add or extend policy entries so the assistant can answer more policy questions |

**Optional — edit these to add extended features:**

| File | What you can do |
|---|---|
| `skeleton/agent.py` | Register new query functions as tools so the AI can call them |
| `skeleton/ui.py` | Customise the chat interface — layout, example queries, display options |

---

### Writing Your Seeding Scripts

Two seeding scripts are left for you to implement:

- `skeleton/seed_postgres.py` — reads JSON files from `train-mock-data/` and inserts rows into your PostgreSQL tables
- `skeleton/seed_neo4j.py` — reads the station JSON files and creates nodes and relationships in Neo4j

The connection setup, helper functions, and overall call order are already in place. **Your job is to implement each `seed_*` function** by extracting the right fields from the loaded JSON and writing the insert logic.

---

#### PostgreSQL seeder (`seed_postgres.py`)

Each `seed_*` function receives an open cursor. Use the `insert_many` helper to bulk-insert rows. The column names you pass must match your `schema.sql` table definition exactly.

**Basic example — inserting flat records:**

```python
def seed_metro_stations(cur):
    data = load("metro_stations.json")
    rows = [
        (s["station_id"], s["name"], s["zone"])
        for s in data
    ]
    n = insert_many(cur, "metro_stations", ["station_id", "name", "zone"], rows)
    print(f"  metro_stations: {n} rows")
```

**Nested example — flattening a list inside each record:**

Some JSON fields are nested lists (e.g. a schedule that contains multiple stops). Loop over the outer list and the inner list together to produce one row per stop:

```python
def seed_metro_schedules(cur):
    data = load("metro_schedules.json")
    rows = []
    for schedule in data:
        for stop in schedule["stops"]:
            rows.append((
                schedule["schedule_id"],
                stop["station_id"],
                stop["arrival_time"],
                stop["stop_order"],
            ))
    n = insert_many(cur, "metro_schedule_stops",
                    ["schedule_id", "station_id", "arrival_time", "stop_order"], rows)
    print(f"  metro_schedule_stops: {n} rows")
```

`insert_many` generates a single `INSERT … VALUES %s ON CONFLICT DO NOTHING` — safe to re-run as many times as needed.

---

#### Neo4j seeder (`seed_neo4j.py`)

Inside the `seed()` function, use `session.run()` to execute Cypher. Use `MERGE` instead of `CREATE` so re-runs do not produce duplicate nodes or relationships.

**Creating nodes:**

```python
for s in metro_stations:
    session.run(
        "MERGE (n:MetroStation {station_id: $id}) "
        "SET n.name = $name, n.zone = $zone",
        id=s["station_id"], name=s["name"], zone=s.get("zone"),
    )
print(f"  Created {len(metro_stations)} MetroStation nodes")
```

**Creating relationships between nodes:**

Each metro station lists its adjacent stations. Loop over them to create directed links:

```python
for s in metro_stations:
    for adj in s.get("adjacent_stations", []):
        session.run(
            "MATCH (a:MetroStation {station_id: $from_id}) "
            "MATCH (b:MetroStation {station_id: $to_id}) "
            "MERGE (a)-[r:METRO_LINK {line: $line}]->(b) "
            "SET r.travel_time_min = $time",
            from_id=s["station_id"], to_id=adj["station_id"],
            line=adj["line"], time=adj["travel_time_min"],
        )
print("  Created metro links")
```

Study each JSON file in `train-mock-data/` carefully before writing your seeder — the fields in the JSON become the columns in your table (PostgreSQL) or the properties on your nodes and relationships (Neo4j).

---

### Task 1 — Design and Extend the Relational Schema (PostgreSQL)

**Files to edit:** `databases/relational/schema.sql`, `databases/relational/queries.py`

Study the JSON files in `train-mock-data/`, then extend the schema and add query functions as described above.

After any changes to the SQL schema file:
```bash
docker compose down -v && docker compose up -d

# macOS / Linux:
python3 skeleton/seed_postgres.py

# Windows (PowerShell):
python skeleton/seed_postgres.py
```

### Task 2 — Enrich the Graph (Neo4j)

**Files to edit:** `databases/graph/seed.cypher`, `databases/graph/queries.py`

Study `train-mock-data/metro_stations.json` and `train-mock-data/national_rail_stations.json`, then extend the graph and add Cypher query functions as described above.

After editing the seed file:
```bash
# macOS / Linux:
python3 skeleton/seed_neo4j.py

# Windows (PowerShell):
python skeleton/seed_neo4j.py
```

### Task 3 — Add Policy Documents (pgvector / RAG)

**Files to edit:** the policy JSON files in `train-mock-data/` — add new entries following the existing structure.

After adding documents:
```bash
# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

### Task 4 — Write New Query Functions

**Files to edit:** `databases/relational/queries.py`, `databases/graph/queries.py`

Add new functions following the patterns already in those files. To make the agent use a new function, see the Advanced section below.

---

## Advanced — Extending the Agent or UI

> **Proceed at your own risk.** The files in `skeleton/` are intentionally complete and working. Editing them is not required to complete the course tasks, and mistakes here can break the entire system. Make a backup copy before changing anything.

### Adding a new tool to the agent

If you have written a new query function in `databases/relational/queries.py` or `databases/graph/queries.py` and want the AI to be able to call it, you need to make four small changes in `skeleton/agent.py`. You do **not** need to write any formatting or summarisation code — the pipeline converts raw JSON results to plain English automatically.

---

**Step 1 — Import your function** at the top of the file, alongside the existing imports:

```python
from databases.relational.queries import (
    query_national_rail_availability,
    # ... existing imports ...
    your_new_function,          # add this
)
```

---

**Step 2 — Add a tool definition** to the `TOOLS` list. This is what the LLM reads to decide when and how to call your tool. Write the description as a clear trigger phrase — the more precise it is, the more reliably the LLM will call your tool at the right moment:

```python
{
    "name": "your_tool_name",
    "description": (
        "One or two sentences explaining what this tool does. "
        "Include the exact kinds of question that should trigger it, e.g. "
        "'Use when the user asks about platform numbers or departure boards.'"
    ),
    "parameters": {
        "param_one": {"type": "string", "description": "What this parameter is, e.g. station ID like NR01"},
        "param_two": {"type": "string", "description": "What this parameter is"},
    },
    "required": ["param_one"],
},
```

---

**Step 3 — Add a one-line entry to `TOOLS_SCHEMA`** (the compact text summary used by the Gemini JSON router, a few lines below the `TOOLS` list):

```python
TOOLS_SCHEMA = """\
...existing tools...
your_tool_name(param_one, param_two?)"""
```

Use `?` to mark optional parameters.

---

**Step 4 — Wire up the execution** inside the `_execute_tool` function, following the same `elif` pattern used for every existing tool:

```python
elif tool_name == "your_tool_name":
    result = your_new_function(**params)
```

That's it. The pipeline's Python flattener (`_normalise_result` in `agent.py`) will automatically convert whatever JSON your function returns into structured readable text — no formatting code needed.

---

**Optional Step 5 — Add a routing hint for Ollama** (only if the LLM does not call your tool reliably when using a small local model):

Inside `run_agent()`, find the `ollama_tool_call` system prompt string and add a one-line hint:

```python
system_prompt=(
    "...existing hints..."
    "Platform/departure board questions → your_tool_name. "   # add this
    ...
),
```

You can verify whether your tool is being called by enabling **"Show database debug panel"** in the UI — it shows the tool selection output, the raw database result, and the LLM-generated data summary for each turn.

---

**Complete example** — adding a tool that looks up platform numbers:

```python
# Step 1: in the imports at the top of agent.py
from databases.relational.queries import (
    ...,
    query_platform_assignment,
)

# Step 2: in the TOOLS list
{
    "name": "get_platform",
    "description": (
        "Look up the platform number for a national rail service at a station. "
        "Use when the user asks which platform to go to, or about departure boards."
    ),
    "parameters": {
        "station_id":   {"type": "string", "description": "Station ID e.g. NR01"},
        "schedule_id":  {"type": "string", "description": "Schedule ID e.g. NR_SCH01"},
    },
    "required": ["station_id", "schedule_id"],
},

# Step 3: in TOOLS_SCHEMA
"get_platform(station_id, schedule_id)"

# Step 4: in _execute_tool
elif tool_name == "get_platform":
    result = query_platform_assignment(**params)
```

---

### Modifying the UI

The chat interface lives in `skeleton/ui.py` and is built with [Gradio](https://www.gradio.app/). If you want to change layout, add example queries, or add new UI controls, that is the only file you need to edit.

Things you can safely change in `skeleton/ui.py`:
- The `EXAMPLES` list — add or remove the clickable example queries shown in the sidebar
- The title and description text in `gr.Markdown()`
- UI layout (column widths, number of rows, colour theme)

Things you should not change in `skeleton/ui.py` without understanding the implications:
- The `chat()` function — this calls `run_agent()` and manages conversation history
- The `agent_history_state` state variable — removing it will break multi-turn conversation
- The `debug_panel` and `debug_toggle` — these are wired to the agent's debug output

---

## Switching Between Ollama and Gemini

**Ollama** (default — local, no API key, no internet required):
```bash
# Install Ollama from https://ollama.com/download, then pull the required models:
ollama pull llama3.2:1b        # ~1.3 GB  — chat model
ollama pull nomic-embed-text   # ~274 MB  — embedding model for pgvector
```
```env
LLM_PROVIDER=ollama
```

**Gemini** (alternative — faster responses, requires a free API key):
```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Gemini's embedding model produces **3072-dimensional** vectors. The schema defaults to **768** (Ollama). If you switch to Gemini, you must also update `databases/relational/schema.sql` before resetting the database:

```sql
-- Change this line in the policy_documents table definition:
embedding   vector(3072),
```

Then reset the database and re-seed:
```bash
docker compose down -v && docker compose up -d

# macOS / Linux:
python3 skeleton/seed_vectors.py

# Windows (PowerShell):
python skeleton/seed_vectors.py
```

> **Important:** If you switch providers after seeding the vector database, you must always re-run the seed script. The embedding model changes with the provider — stored vectors will no longer match queries made with the new model.

---

## Useful URLs (When Docker Is Running)

| Service | URL | Login credentials |
|---|---|---|
| TransitFlow Chat UI | http://localhost:7860 | — |
| Neo4j Browser (graph visualiser) | http://localhost:7475 | neo4j / transitflow |
| pgAdmin (PostgreSQL browser UI) | http://localhost:5051 | admin@admin.com / admin |
| PostgreSQL (direct connection) | localhost:5433 | transitflow / transitflow |

### Connecting pgAdmin to PostgreSQL

1. Open **http://localhost:5051** and log in with `admin@admin.com` / `admin`
2. In the left sidebar, right-click **Servers → Register → Server…**
3. Fill in the two tabs:

   **General tab**
   - Name: `TransitFlow` (or any label you like)

   **Connection tab**
   - Host: `postgres`
   - Port: `5432`
   - Maintenance database: `transitflow`
   - Username: `transitflow`
   - Password: `transitflow`
   - Tick **Save password**

4. Click **Save** — the server appears in the sidebar. Expand it to browse tables under **Databases → transitflow → Schemas → public → Tables**.

To run a SQL query, right-click the database and choose **Query Tool**.

---

To visualise the entire rail network in Neo4j Browser, paste this query:
```cypher
MATCH (n)-[r]->(m) RETURN n, r, m
```

---

## Troubleshooting

**"Cannot connect to Neo4j"** — Neo4j takes up to 30 seconds to start. Wait, then retry.

**"GEMINI_API_KEY is not set"** — You have `LLM_PROVIDER=gemini` but no key. Either add your key to `.env`, or switch to `LLM_PROVIDER=ollama` to run without one.

**"Cannot reach Ollama"** — Ollama is not running. Start it from your Applications folder or system tray, then retry.

**"embedding dimension mismatch"** — The vector dimension stored in the database does not match the active embedding model. Either you switched providers after seeding, or `schema.sql` still declares the wrong dimension. Check that `schema.sql` has `vector(768)` for Ollama or `vector(3072)` for Gemini, reset the database (`docker compose down -v && docker compose up -d`), then re-run `python skeleton/seed_vectors.py`.

**Docker containers won't start** — Ensure Docker Desktop is open and running. Then try: `docker compose down -v && docker compose up -d`

**Gradio shows an error on startup** — Check the terminal for a Python traceback. The most common causes are a missing `.env` file, or a database container that isn't fully ready yet.

**`pip install` works but `python skeleton/ui.py` says "ModuleNotFoundError"** — Your virtual environment is not active. Run `source .venv/bin/activate` (macOS/Linux) or `.venv\Scripts\Activate.ps1` (Windows PowerShell) and try again.

**Windows PowerShell says "running scripts is disabled"** — Run this once, then retry the activation:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

**`python` not found on macOS or Linux** — Use `python3` instead. On these systems, `python` may refer to Python 2 or may not exist. All `python` commands in this README can be replaced with `python3`.

---

## Python Virtual Environments

### What is a virtual environment?

When you install Python packages with `pip install`, they are placed somewhere on your machine. Without a virtual environment, they go into your **system Python** — a shared, global location used by your operating system, other projects, and tools you may not even know about.

A **virtual environment** (venv) creates a private, isolated copy of Python for a single project. Packages installed inside it stay inside it. Your system Python is not touched. If you delete the project, you delete the environment with it — no cleanup required.

```
Without venv                         With venv
────────────────────────────────     ───────────────────────────────────
System Python                        System Python  (unchanged)
  └── site-packages/                   └── site-packages/  (unchanged)
        requests==2.28                        ← nothing added here
        gradio==4.0
        neo4j==5.0                   transitflow/.venv/
        psycopg2==2.9                  └── site-packages/
        (used by ALL projects)               requests==2.28
                                             gradio==4.0
                                             neo4j==5.0
                                             psycopg2==2.9
                                             (used ONLY by this project)
```

### Why it matters for this project

This project installs specific versions of `gradio`, `neo4j`, `psycopg2`, `google-genai`, and several other packages. If you are working on other Python projects on the same machine, those projects may require different versions of the same packages. Without isolation, installing one project's requirements can silently break another's.

A virtual environment prevents this entirely. Each project gets its own sandbox.

### `apt install` vs `pip install` — what's the difference?

You may have seen both commands and wondered when to use which.

**`apt install`** (Debian/Ubuntu Linux only) is your **operating system's** package manager. It installs software at the system level — not just Python packages, but any program, library, or tool your OS needs. Use it when you are installing something that the whole machine needs:

```bash
# Install Python itself, or system-level tools
sudo apt install python3
sudo apt install python3-pip
sudo apt install postgresql-client
```

`apt` packages are tested for compatibility with your OS distribution. They are usually slightly behind the latest version on purpose, because stability matters more than novelty at the system level.

**`pip install`** is **Python's** package manager. It installs packages from [PyPI](https://pypi.org) — the Python Package Index — into whichever Python environment is currently active. Use it when you are installing a Python library for your code to use:

```bash
# Install Python libraries your code imports
pip install gradio
pip install psycopg2-binary
pip install neo4j
```

The key distinction: `apt` manages your machine; `pip` manages your Python project. For application development, `pip` inside a virtual environment is how you manage all your Python dependencies. `apt` is only needed to install Python itself, or system-level prerequisites like database clients.

| | `apt install` | `pip install` |
|---|---|---|
| What it installs | System software and OS-level libraries | Python packages for your code |
| Where packages go | System directories (`/usr/lib`, etc.) | Active Python environment |
| Who maintains it | Your Linux distribution | The Python community (PyPI) |
| When to use it | Installing Python, system tools, drivers | Installing libraries your project imports |
| Needs `sudo`? | Yes | No (inside a venv) |

### Setting up a virtual environment for this project

**Step 1 — Create the environment** (once, after cloning):

**macOS / Linux:**
```bash
cd transitflow
python3 -m venv .venv
```

**Windows (PowerShell):**
```powershell
cd transitflow
python -m venv .venv
```

This creates a `.venv/` folder inside the project. It contains a private Python interpreter and an empty `site-packages/` directory. The folder is listed in `.gitignore` — it should never be committed.

**Step 2 — Activate it** (every time you open a new terminal):

**macOS / Linux:**
```bash
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
.venv\Scripts\Activate.ps1
```

> **Windows PowerShell note:** If activation fails with "running scripts is disabled", run this once and then retry:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
> ```

Your prompt will change to show `(.venv)` as confirmation. While active, `python` and `pip` refer to the environment's private copies, not the system ones.

**Step 3 — Install the project's packages:**

```bash
pip install -r requirements.txt
```

All packages go into `.venv/site-packages/`. Your system Python is untouched.

**Step 4 — Deactivate when you're done** (optional):

```bash
deactivate
```

### Quick reference

| Task | macOS / Linux | Windows (PowerShell) |
|---|---|---|
| Create environment | `python3 -m venv .venv` | `python -m venv .venv` |
| Activate | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Install project packages | `pip install -r requirements.txt` | `pip install -r requirements.txt` |
| See installed packages | `pip list` | `pip list` |
| Deactivate | `deactivate` | `deactivate` |
| Delete the environment | `rm -rf .venv` | Delete the `.venv\` folder |

### Virtual environments and IDEs

Most IDEs detect and use virtual environments automatically:

- **VS Code** — open the project folder, press `Ctrl+Shift+P`, select **Python: Select Interpreter**, and choose the one labelled `.venv`. VS Code will then use it for all terminals and the debugger.
- **PyCharm** — go to Settings → Project → Python Interpreter → Add Interpreter → Existing → point to `.venv/bin/python` (macOS/Linux) or `.venv\Scripts\python.exe` (Windows PowerShell).

Once your IDE is configured, you do not need to manually activate the environment in the integrated terminal — it activates automatically.

---

## Finally, Working as a Team

### What git tracks — and what it doesn't

Docker volumes are not part of your git repository. Each teammate's database data lives entirely on their own machine. **Git only tracks the files that define the data** — not the data itself.

| What | Tracked by git? | Notes |
|---|---|---|
| `databases/relational/schema.sql` | Yes | Tables, constraints, and all seed data |
| `databases/graph/seed.cypher` | Yes | Station nodes and rail link edges |
| `train-mock-data/refund_policy.json`, `ticket_types.json`, `booking_rules.json`, `travel_policies.json` | Yes | Policy documents to be embedded |
| `databases/*/queries.py` | Yes | Python query functions |
| `.env` | **No** (gitignored) | Each teammate keeps their own copy based on `.env.example` |
| Docker volume data | **No** | Stored only on your local machine by Docker |

This means: if a teammate changes `schema.sql` and pushes to git, your running database is unaffected until you explicitly reset and reload it.

---

### The golden rule

> **If a seed file changed in git, reset your database.**

After every `git pull`, check whether any of the three seed files changed, and act accordingly:

```bash
# See which seed files your teammate changed:
git diff HEAD~1 HEAD -- databases/relational/schema.sql databases/graph/seed.cypher train-mock-data/refund_policy.json train-mock-data/ticket_types.json train-mock-data/booking_rules.json train-mock-data/travel_policies.json
```

| File that changed | Command to run |
|---|---|
| `databases/relational/schema.sql` | `docker compose down -v && docker compose up -d`, then `python skeleton/seed_postgres.py` |
| `skeleton/seed_postgres.py` (or any `train-mock-data/*.json`) | `python skeleton/seed_postgres.py` |
| `databases/graph/seed.cypher` | `python skeleton/seed_neo4j.py` |
| `train-mock-data/` policy JSON files | `python skeleton/seed_vectors.py` |

> **Important:** `docker compose down -v` wipes **both** Docker volumes (PostgreSQL and pgvector together). If you reset due to a schema change, you must also re-run `seed_neo4j.py` and `seed_vectors.py` afterwards — even if those files did not change.

---

### Agree on one LLM provider before seeding

The policy documents in pgvector are stored as numerical vectors. The size of those vectors depends on the embedding model, which changes with the LLM provider:

| Provider | Vector size in `schema.sql` | `.env` setting |
|---|---|---|
| Ollama (default) | `vector(768)` | `LLM_PROVIDER=ollama` |
| Gemini | `vector(3072)` | `LLM_PROVIDER=gemini` |

**These two formats are not compatible.** If one teammate seeds with Ollama and another queries with Gemini (or vice versa), the app will fail with an `embedding dimension mismatch` error.

Agree as a team on a single provider before anyone runs `seed_vectors.py`. Make sure:
1. Everyone sets the same `LLM_PROVIDER` value in their own `.env`
2. The `vector(...)` dimension in `databases/relational/schema.sql` matches that provider

If you later switch providers as a team, everyone must reset the database (`docker compose down -v && docker compose up -d`) and re-run `seed_vectors.py`.

---

### Full resync workflow (run after every `git pull` if seed files changed)

```bash
# 1. Wipe volumes and restart containers (only needed if schema.sql changed)
docker compose down -v && docker compose up -d

# 2. Wait until both containers are healthy
docker compose ps

# 3. Seed the relational database
#    macOS / Linux:
python3 skeleton/seed_postgres.py
#    Windows (PowerShell):
python skeleton/seed_postgres.py

# 4. Re-seed the graph database
#    macOS / Linux:
python3 skeleton/seed_neo4j.py
#    Windows (PowerShell):
python skeleton/seed_neo4j.py

# 5. Re-seed the vector database
#    macOS / Linux:
python3 skeleton/seed_vectors.py
#    Windows (PowerShell):
python skeleton/seed_vectors.py
```

---

### What to commit — and what not to

**Always commit** changes to any file inside `databases/` — that is your working area and the shared source of truth.

**Never commit:**
- `.env` — gitignored because it contains credentials. Each teammate copies `.env.example` and fills in their own values.
- The `.venv/` folder — gitignored, and large. Each teammate creates their own via `python -m venv .venv`.
- Any locally generated data exports or dump files.

Before pushing, run `git status` and `git diff --staged` to confirm you are only committing files from `databases/`.
hahahahah