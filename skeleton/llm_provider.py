"""
TransitFlow LLM Provider
========================
Supports two providers switchable at runtime:
  - Ollama (default — local, no API key, requires Ollama running)
  - Gemini (alternative — cloud, requires API key)

Both chat AND embeddings follow the active provider.
If you switch providers, you must re-run skeleton/seed_vectors.py to rebuild
the pgvector index with the new embedding model.

Students: You do NOT need to change this file.
"""

from __future__ import annotations
import requests
from typing import List
from google import genai
from google.genai import types

from skeleton.config import (
    LLM_PROVIDER,
    GEMINI_API_KEY, GEMINI_CHAT_MODEL, GEMINI_EMBED_MODEL, GEMINI_EMBED_DIM,
    OLLAMA_BASE_URL, OLLAMA_CHAT_MODEL, OLLAMA_EMBED_MODEL, OLLAMA_EMBED_DIM, OLLAMA_TIMEOUT,
)


class LLMProvider:
    """
    Unified interface for chat and embeddings.

    chat_provider can be switched at runtime via set_chat_provider().
    embed_provider follows the startup LLM_PROVIDER and does not change at runtime,
    so queries always use the same embedding model that seeded the pgvector index.
    """

    def __init__(self):
        self.chat_provider = LLM_PROVIDER
        self._ollama_chat_model = OLLAMA_CHAT_MODEL
        # embed_provider tracks which model was used to seed the vectors.
        # It follows the startup LLM_PROVIDER; runtime chat toggling does NOT change it.
        self._embed_provider = LLM_PROVIDER
        self.embed_dim = OLLAMA_EMBED_DIM if self._embed_provider == "ollama" else GEMINI_EMBED_DIM

        # Initialise Gemini client only when needed
        self._gemini_client = None
        if LLM_PROVIDER == "gemini":
            if not GEMINI_API_KEY:
                raise ValueError(
                    "GEMINI_API_KEY is not set. Add it to your .env file, "
                    "or switch to LLM_PROVIDER=ollama to run without an API key."
                )
            self._gemini_client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options=types.HttpOptions(api_version="v1beta"),
            )

        # Check Ollama is reachable if that's the startup provider
        if self.chat_provider == "ollama":
            self._check_ollama()

        self._print_status()

    def _print_status(self):
        embed_info = (
            f"Ollama ({OLLAMA_EMBED_MODEL})"
            if self._embed_provider == "ollama"
            else f"Gemini ({GEMINI_EMBED_MODEL})"
        )
        if self.chat_provider == "gemini":
            print(f"[LLM] Chat: Gemini ({GEMINI_CHAT_MODEL}) | Embed: {embed_info}")
        else:
            print(f"[LLM] Chat: Ollama ({OLLAMA_CHAT_MODEL}) | Embed: {embed_info}")

    # ── Runtime provider switching ─────────────────────────────────────────

    def set_chat_provider(self, provider: str) -> str:
        """
        Switch the chat provider at runtime. Called by the UI toggle.

        Args:
            provider: "gemini" or "ollama"

        Returns:
            Status message to display in the UI
        """
        provider = provider.lower()
        if provider not in ("gemini", "ollama"):
            return f"❌ Unknown provider '{provider}'. Choose 'gemini' or 'ollama'."

        if provider == "gemini":
            if not GEMINI_API_KEY:
                return "❌ GEMINI_API_KEY is not set — cannot switch to Gemini. Add it to your .env file."
            if self._gemini_client is None:
                self._gemini_client = genai.Client(
                    api_key=GEMINI_API_KEY,
                    http_options=types.HttpOptions(api_version="v1beta"),
                )

        if provider == "ollama":
            try:
                self._check_ollama()
            except ConnectionError as e:
                return f"❌ {e}"

        self.chat_provider = provider
        self._print_status()

        if provider == "gemini":
            return f"✅ Switched to Gemini ({GEMINI_CHAT_MODEL})"
        return f"✅ Switched to Ollama ({self._ollama_chat_model}) — running locally"

    def get_chat_provider(self) -> str:
        return self.chat_provider

    def get_chat_model(self) -> str:
        return self._ollama_chat_model

    def set_chat_model(self, model_name: str) -> str:
        if self.chat_provider != "ollama":
            return "❌ Model switching only applies to the Ollama provider."
        self._ollama_chat_model = model_name
        print(f"[LLM] Switched Ollama model to: {model_name}")
        return f"✅ Switched to {model_name}"

    def get_available_ollama_models(self) -> list[str]:
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            r.raise_for_status()
            models = r.json().get("models", [])
            return sorted(m["name"] for m in models)
        except Exception:
            return []

    # ── Public API ─────────────────────────────────────────────────────────

    def chat(self, messages: list[dict], system_prompt: str = "") -> str:
        if self.chat_provider == "gemini":
            return self._gemini_chat(messages, system_prompt)
        return self._ollama_chat(messages, system_prompt)

    def embed(self, text: str) -> List[float]:
        # Uses the provider set at startup — must match the model used to seed the vectors
        if self._embed_provider == "ollama":
            return self._ollama_embed(text)
        return self._gemini_embed(text)

    # ── Gemini internals ───────────────────────────────────────────────────

    def _gemini_chat(self, messages: list[dict], system_prompt: str) -> str:
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))

        config = types.GenerateContentConfig(
            system_instruction=system_prompt or None,
        )
        response = self._gemini_client.models.generate_content(
            model=GEMINI_CHAT_MODEL,
            contents=contents,
            config=config,
        )
        return response.text

    def _gemini_embed(self, text: str) -> List[float]:
        if self._gemini_client is None:
            raise RuntimeError(
                "Gemini client is not initialised. Set LLM_PROVIDER=gemini and add "
                "GEMINI_API_KEY to your .env file, then re-run skeleton/seed_vectors.py."
            )
        result = self._gemini_client.models.embed_content(
            model=GEMINI_EMBED_MODEL,
            contents=text,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
        )
        return result.embeddings[0].values

    # ── Ollama internals ───────────────────────────────────────────────────

    def _ollama_chat(self, messages: list[dict], system_prompt: str) -> str:
        # Ollama only accepts {"role": ..., "content": ...} — strip any extra keys
        clean_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        if system_prompt:
            clean_messages = [{"role": "system", "content": system_prompt}] + clean_messages
        payload = {
            "model": self._ollama_chat_model,
            "messages": clean_messages,
            "stream": False,
        }

        r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        r.raise_for_status()
        return r.json()["message"]["content"]

    def _ollama_embed(self, text: str) -> List[float]:
        r = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
            timeout=60,
        )
        r.raise_for_status()
        return r.json()["embedding"]

    def ollama_tool_call(
        self,
        history: list[dict],
        tools: list[dict],
        user_message: str,
        system_prompt: str = "",
    ) -> list[dict]:
        """
        Use Ollama's native tool-calling API to select tools.
        llama3.2:1b is fine-tuned for this and produces reliable results,
        unlike prompt-based JSON routing which frequently produces malformed output.
        Returns [{"name": ..., "params": {...}}] — same format as the prompt router.
        """
        clean = []
        if system_prompt:
            clean.append({"role": "system", "content": system_prompt})
        clean += [{"role": m["role"], "content": m["content"]} for m in history]
        clean.append({"role": "user", "content": user_message})

        # Convert agent TOOLS list to OpenAI/Ollama function-calling schema
        ollama_tools = []
        for t in tools:
            properties = {}
            for pname, pschema in t.get("parameters", {}).items():
                properties[pname] = {k: v for k, v in pschema.items()}
            ollama_tools.append({
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": t.get("required", []),
                    },
                },
            })

        payload = {
            "model":   self._ollama_chat_model,
            "messages": clean,
            "tools":   ollama_tools,
            "stream":  False,
        }
        r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=OLLAMA_TIMEOUT)
        r.raise_for_status()

        raw_calls = r.json().get("message", {}).get("tool_calls", [])
        return [
            {
                "name":   tc["function"]["name"],
                "params": tc["function"].get("arguments", {}),
            }
            for tc in raw_calls
            if "function" in tc
        ]

    def _check_ollama(self):
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
            r.raise_for_status()
        except Exception as e:
            raise ConnectionError(
                f"Cannot reach Ollama at {OLLAMA_BASE_URL}.\n"
                "Make sure Ollama is running: https://ollama.com/download\n"
                f"Then pull a model: ollama pull {OLLAMA_CHAT_MODEL}\n"
                f"Error: {e}"
            )

    def ollama_available(self) -> bool:
        """Quick non-raising check — used by the UI to show toggle state."""
        try:
            r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=2)
            return r.ok
        except Exception:
            return False


# Singleton — import this everywhere
llm = LLMProvider()
