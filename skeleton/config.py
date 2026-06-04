"""
TransitFlow Configuration
Reads from environment variables / .env file.
Students: copy .env.example to .env and fill in your API key.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM Provider ──────────────────────────────────────────────────────────────
# Set LLM_PROVIDER to "gemini" or "ollama"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Gemini settings (free tier: gemini-1.5-flash)
GEMINI_API_KEY        = os.getenv("GEMINI_API_KEY", "")
GEMINI_CHAT_MODEL     = os.getenv("GEMINI_CHAT_MODEL", "gemini-2.0-flash-lite")
GEMINI_EMBED_MODEL    = os.getenv("GEMINI_EMBED_MODEL", "gemini-embedding-001")
GEMINI_EMBED_DIM      = 3072

# Ollama settings (local, no API key needed)
OLLAMA_BASE_URL       = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_CHAT_MODEL     = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:1b")   # ~1.3 GB
OLLAMA_EMBED_MODEL    = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
OLLAMA_EMBED_DIM      = 768
OLLAMA_TIMEOUT        = int(os.getenv("OLLAMA_TIMEOUT", "300"))          # seconds; raise for slow CPUs

# ── PostgreSQL ────────────────────────────────────────────────────────────────
PG_HOST     = os.getenv("PG_HOST",     "localhost")
PG_PORT     = int(os.getenv("PG_PORT", "5432"))
PG_USER     = os.getenv("PG_USER",     "transitflow")
PG_PASSWORD = os.getenv("PG_PASSWORD", "transitflow")
PG_DB       = os.getenv("PG_DB",       "transitflow")

PG_DSN = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"

# ── Neo4j ─────────────────────────────────────────────────────────────────────
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USER     = os.getenv("NEO4J_USER",     "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "transitflow")

# ── RAG settings ──────────────────────────────────────────────────────────────
VECTOR_TOP_K           = int(os.getenv("VECTOR_TOP_K", "3"))       # How many policy chunks to retrieve
VECTOR_SIMILARITY_THRESHOLD = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.3"))
