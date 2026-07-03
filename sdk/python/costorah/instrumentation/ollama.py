"""
OllamaInstrumentor — automatic usage capture for local Ollama calls made
through the official `openai` package pointed at Ollama's
OpenAI-compatible endpoint (Ollama's documented integration path for
existing OpenAI-based tooling).

    from openai import OpenAI
    from costorah.instrumentation import OllamaInstrumentor

    OllamaInstrumentor().instrument()

    client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
    client.chat.completions.create(model="llama3", messages=[...])

Detected via `base_url` containing "localhost:11434"/"127.0.0.1:11434".
Cost is always 0.0 (no `cost_estimated` claim) — local models are free;
see `pricing.py`, which simply has no entry for Ollama models and
therefore reports 0.0 honestly rather than guessing.
"""

from __future__ import annotations

from costorah.instrumentation._openai_compatible import _OpenAICompatibleInstrumentor


class OllamaInstrumentor(_OpenAICompatibleInstrumentor):
    name = "ollama"
    fixed_provider = "ollama"
