"""
OpenRouterInstrumentor — automatic usage capture for OpenRouter calls made
through the official `openai` package pointed at OpenRouter's
OpenAI-compatible endpoint (OpenRouter has no bespoke Python SDK; this is
its documented integration path).

    from openai import OpenAI
    from costorah.instrumentation import OpenRouterInstrumentor

    OpenRouterInstrumentor().instrument()

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=...)
    client.chat.completions.create(model="openai/gpt-4o", messages=[...])

Detected via `base_url` containing "openrouter.ai" (see `_detect_provider`
in `_openai_compatible.py`); only OpenRouter-targeted clients are captured
while this instrumentor is active.
"""

from __future__ import annotations

from costorah.instrumentation._openai_compatible import _OpenAICompatibleInstrumentor


class OpenRouterInstrumentor(_OpenAICompatibleInstrumentor):
    name = "openrouter"
    fixed_provider = "openrouter"
