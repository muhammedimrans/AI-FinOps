"""
OpenAIInstrumentor — automatic usage capture for the official `openai`
Python package's Chat Completions and Responses APIs (sync, async, and
streaming).

    from openai import OpenAI
    from costorah.instrumentation import OpenAIInstrumentor

    OpenAIInstrumentor().instrument()

    client = OpenAI()
    client.responses.create(model="gpt-4.1", input="Hello")

See `_openai_compatible.py` for the shared patch implementation this (and
every other OpenAI-SDK-compatible provider instrumentor) is built on.
"""

from __future__ import annotations

from costorah.instrumentation._openai_compatible import _OpenAICompatibleInstrumentor


class OpenAIInstrumentor(_OpenAICompatibleInstrumentor):
    name = "openai"
    fixed_provider = "openai"
