"""
GrokInstrumentor — automatic usage capture for xAI Grok calls made
through the official `openai` package pointed at xAI's OpenAI-compatible
endpoint (xAI's documented integration path).

    from openai import OpenAI
    from costorah.instrumentation import GrokInstrumentor

    GrokInstrumentor().instrument()

    client = OpenAI(base_url="https://api.x.ai/v1", api_key=...)
    client.chat.completions.create(model="grok-2", messages=[...])

Detected via `base_url` containing "api.x.ai".
"""

from __future__ import annotations

from costorah.instrumentation._openai_compatible import _OpenAICompatibleInstrumentor


class GrokInstrumentor(_OpenAICompatibleInstrumentor):
    name = "grok"
    fixed_provider = "grok"
