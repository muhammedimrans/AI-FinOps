"""
AzureOpenAIInstrumentor — automatic usage capture for Azure OpenAI
Service calls made through the official `openai` package's
`AzureOpenAI`/`AsyncAzureOpenAI` clients.

    from openai import AzureOpenAI
    from costorah.instrumentation import AzureOpenAIInstrumentor

    AzureOpenAIInstrumentor().instrument()

    client = AzureOpenAI(azure_endpoint=..., api_version=...)
    client.chat.completions.create(model="my-deployment", messages=[...])

Shares the same patched `Completions`/`Responses` classes as every other
OpenAI-family instrumentor (see `_openai_compatible.py`); only Azure
clients (detected by class name) are captured while this instrumentor is
active.
"""

from __future__ import annotations

from costorah.instrumentation._openai_compatible import _OpenAICompatibleInstrumentor


class AzureOpenAIInstrumentor(_OpenAICompatibleInstrumentor):
    name = "azure_openai"
    fixed_provider = "azure_openai"
