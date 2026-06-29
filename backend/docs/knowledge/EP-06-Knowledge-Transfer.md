# EP-06 Knowledge Transfer — AI Provider Framework

**Epic:** EP-06  
**Date:** 2026-06-29  
**Status:** Complete  
**Branch:** `claude/ai-finops-ep-01-s4d42x`

---

## Table of Contents

1. [Implementation Summary](#1-implementation-summary)
2. [Provider Architecture](#2-provider-architecture)
3. [Provider Lifecycle](#3-provider-lifecycle)
4. [AIProvider Interface](#4-aiprovider-interface)
5. [Registry Pattern](#5-registry-pattern)
6. [Factory Pattern](#6-factory-pattern)
7. [Capability Model](#7-capability-model)
8. [Configuration Model](#8-configuration-model)
9. [Error Model](#9-error-model)
10. [Adapter Design](#10-adapter-design)
11. [Architecture Review](#11-architecture-review)
12. [Production Readiness](#12-production-readiness)
13. [How EP-07 Builds on EP-06](#13-how-ep-07-builds-on-ep-06)
14. [Top 30 Engineering Concepts Learned](#14-top-30-engineering-concepts-learned)

---

## 1. Implementation Summary

### What EP-06 Implemented

EP-06 built the **AI provider abstraction layer** — the architectural foundation that every AI provider adapter must implement. It covers nine domain files and seven provider-specific adapter stubs under `app/providers/`:

| Feature | Spec ID | Description |
|---------|---------|-------------|
| `AIProvider` abstract base class | F-024 | The contract every provider must fulfil |
| `ProviderRegistry` | F-025 | Central map of ProviderType → adapter class |
| `ProviderFactory` | F-026 | Instantiates providers from configuration |
| `ProviderCapabilities` | F-027 | Frozen capability flags per provider |
| Provider configuration models | F-028 | Typed, validated config per provider type |
| `ProviderError` hierarchy | F-029 | Normalised error taxonomy |
| Retry policy interfaces | F-030 | `RetryPolicy`, `CircuitBreaker` ABCs |
| Health check interface | F-031 | `HealthCheckInterface` ABC |
| Common models | F-032 | `ModelMetadata`, `ProviderRequest/Response`, `UsageData` |
| Seven adapter stubs | — | OpenAI, Anthropic, Grok, Google, Azure OpenAI, OpenRouter, Ollama |

**No real API calls are made anywhere in EP-06.** Every adapter method that would require external network access either returns stub data or raises `NotImplementedError("EP-07")`.

### Why It Exists

Before EP-06, the system knew about providers only through the `ProviderConnection` ORM model (EP-03) — a database record that says "this org uses OpenAI." There was no Python code to actually speak to any provider, no shared vocabulary for what providers can do, and no consistent way to handle provider failures.

Without an abstraction layer, EP-07 would have to hard-code provider-specific logic throughout the service layer. Adding a new provider (e.g., Mistral) would require changes scattered across many files.

EP-06 fixes this by defining a single, stable interface that the rest of the codebase calls. EP-07 and beyond fill in the implementation details behind that interface.

### Business Value

- **Provider-agnostic cost attribution:** The FinOps engine (EP-08+) can record usage against any provider using the same `UsageData` model.
- **Time-to-market for new providers:** Adding a new AI provider in the future requires one new adapter file and one line in the registry. No other code changes.
- **Vendor lock-in prevention:** The service layer never imports `openai`, `anthropic`, or any vendor SDK directly. It only calls `AIProvider` methods.
- **Operational visibility:** `ProviderCapabilities` lets the UI truthfully display what each provider supports (streaming, vision, audio) without polling the provider API.

### Architecture Value

EP-06 creates the boundary between "what we need from providers" and "how each provider delivers it." This is the Dependency Inversion Principle applied at the provider integration layer: high-level business logic depends on the `AIProvider` abstraction; only the adapter stubs depend on provider-specific details.

### How It Supports Future AI Providers

Every new provider follows the same four-step process:

1. Add a value to `ProviderType` StrEnum (`app/models/provider_connection.py`).
2. Create a typed config subclass in `app/providers/config.py`.
3. Create `app/providers/adapters/<name>.py` subclassing `AIProvider`.
4. Add one `registry.register(...)` call in `ProviderFactory.build_default_registry()`.

No changes to the service layer, API layer, or cost engine are required.

---

## 2. Provider Architecture

### Conceptual Map

```
┌─────────────────────────────────────────────────────────────────────┐
│                        app/providers/                               │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────┐        │
│  │  interface.py — AIProvider (ABC)                        │        │
│  │  The contract. Every adapter must implement this.       │        │
│  └──────────────────────────────┬──────────────────────────┘        │
│                                 │ implemented by                    │
│         ┌───────────────────────┼───────────────────┐              │
│         ▼                       ▼                   ▼              │
│  adapters/openai.py    adapters/anthropic.py   adapters/…          │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐      │
│  │ registry.py  │  │  factory.py  │  │   capabilities.py    │      │
│  │ ProviderReg. │  │ ProviderFact.│  │  ProviderCapabilities│      │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────┘      │
│         │                 │                                         │
│         └────────uses─────┘                                         │
│                                                                     │
│  ┌───────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐  │
│  │ models.py │ │config.py │ │ errors.py│ │ retry.py │ │health.py│  │
│  └───────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Layer Responsibilities

| File | Layer | Responsibility |
|------|-------|----------------|
| `interface.py` | Contract | Defines *what* every provider must do |
| `registry.py` | Discovery | Maps provider type → adapter class |
| `factory.py` | Creation | Instantiates adapters from config |
| `capabilities.py` | Metadata | What features a provider supports |
| `models.py` | Data | Shared request/response/usage types |
| `config.py` | Configuration | Validated, typed config per provider |
| `errors.py` | Errors | Normalised failure taxonomy |
| `retry.py` | Resilience | Interfaces for retry and circuit-breaking |
| `health.py` | Observability | Interface for connectivity checking |
| `adapters/` | Implementation | Provider-specific stubs (real calls in EP-07) |

### Why Each Layer Exists

**`interface.py`** — Without a shared interface, every caller would need to know which provider it was talking to. The interface hides all provider differences behind one set of method signatures.

**`registry.py`** — Without a registry, adding a provider requires hunting through the codebase for every place that switches on `ProviderType`. The registry centralises that mapping.

**`factory.py`** — Without a factory, every call site would need to know which config class to instantiate and which adapter class to construct. The factory encapsulates that construction logic.

**`capabilities.py`** — Without capabilities, the UI and business logic would need to hard-code "OpenAI supports vision but Grok does not" everywhere. Capabilities make this data-driven.

**`models.py`** — Without shared models, each adapter returns different shapes. The common models establish the canonical data contract across all providers.

**`config.py`** — Without typed config, configuration errors are only discovered at runtime (often at the first API call). Typed, validated config catches mistakes at load time.

**`errors.py`** — Without normalised errors, callers must catch `openai.RateLimitError` in one place and `anthropic.APIStatusError` in another. Normalised errors let the service layer catch `RateLimitError` regardless of provider.

**`retry.py`** — Without interfaces, concrete retry logic can't be injected or tested in isolation. ABCs define the shape so EP-07 can implement and EP-08 can swap strategies.

**`health.py`** — Without an interface, health checking is provider-specific. The interface enables a generic health dashboard in future.

---

## 3. Provider Lifecycle

### Full Lifecycle Diagram

```
User creates ProviderConnection in the database
           │
           │  (EP-03: ProviderConnection ORM row with ProviderType, configuration JSONB)
           ▼
Service layer reads ProviderConnection from DB
           │
           │  conn.provider_type  →  ProviderType.OPENAI
           │  conn.configuration  →  {"org_id": "org-123"}
           ▼
Build ProviderConfig (EP-06: config.py)
           │
           │  OpenAIConfig(
           │      provider_type="openai",
           │      display_name=conn.display_name,
           │      api_key_ref=SecretReference(secret_store="env", secret_key="OPENAI_API_KEY"),
           │      organization_id="org-123",
           │  )
           │
           │  ← credential-leak validator runs here
           │     rejects any plaintext secret in extra {}
           ▼
ProviderFactory.create(config)
           │
           │  factory._registry.get(ProviderType.OPENAI)  →  OpenAIProvider class
           │  return OpenAIProvider(config)
           ▼
OpenAIProvider (AIProvider adapter)
           │
           ├─── provider.capabilities        →  ProviderCapabilities(supports_vision=True, …)
           │                                    (no I/O — compile-time constant)
           │
           ├─── await provider.check_connection()  →  ConnectionStatus(…)
           │                                           (EP-07: real HTTP ping)
           │
           ├─── await provider.verify_auth()   →  bool
           │                                       (EP-07: validates API key)
           │
           ├─── await provider.list_models()   →  list[ModelMetadata]
           │                                       (EP-07: fetches from provider API)
           │
           └─── await provider.complete(request) → ProviderResponse
                                                    (EP-07: real LLM call)
                                                    └── response.usage  →  UsageData
                                                                             (EP-08: cost engine)
```

### Lifecycle State Transitions

```
ProviderConnection (DB)
        │
        │ instantiate
        ▼
   AIProvider (Python object)
        │
        │ verify_auth()
        ▼
   AUTHENTICATED ──────────────── check_connection() ───► HEALTHY / DEGRADED / UNHEALTHY
        │
        │ list_models()
        ▼
   MODELS KNOWN
        │
        │ complete(request)
        ▼
   RESPONSE ──────────────────────── usage → UsageData → Cost Engine (EP-08+)
```

The lifecycle moves from *configuration* (no I/O) → *authentication* (one I/O round-trip) → *capability discovery* (optional I/O) → *usage* (repeated I/O). EP-06 implements everything before the first I/O arrow.

---

## 4. AIProvider Interface

**File:** `app/providers/interface.py`  
**Spec:** F-024

The `AIProvider` abstract base class is the single most important file in EP-06. Every other component either produces an `AIProvider` (the factory) or consumes one (the service layer).

```python
class AIProvider(ABC):
    def __init__(self, config: ProviderConfig) -> None: ...

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType: ...

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    async def check_connection(self) -> ConnectionStatus: ...

    @abstractmethod
    async def list_models(self) -> list[ModelMetadata]: ...

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...

    @abstractmethod
    async def verify_auth(self) -> bool: ...

    @property
    def config(self) -> ProviderConfig: ...       # concrete — returns self._config

    @property
    def display_name(self) -> str: ...            # concrete — returns config.display_name
```

### Method Reference

#### `provider_type` → `ProviderType`

**Purpose:** Identifies which provider this adapter represents.  
**Input:** None (property).  
**Output:** A `ProviderType` enum value (e.g., `ProviderType.OPENAI`).  
**Why abstract:** Every adapter returns a different value. The registry and factory use this to validate that the correct class is registered for the type.  
**Future:** Unchanged. Static forever — a class represents exactly one provider.

#### `capabilities` → `ProviderCapabilities`

**Purpose:** Returns what this provider can do, without any network call.  
**Input:** None (property).  
**Output:** A frozen `ProviderCapabilities` dataclass.  
**Why abstract:** Capabilities differ by provider (Ollama has no usage API; Google supports OAuth).  
**Why a property (not a method):** Capabilities are a static fact about the provider, not the result of a computation. Properties signal that accessing them is free.  
**Future:** Capabilities may become dynamic once EP-07 can fetch real model lists (a provider may add vision support mid-cycle). For now they are compile-time constants.

#### `check_connection()` → `ConnectionStatus`

**Purpose:** Test connectivity and return a status report. No side-effects.  
**Input:** None.  
**Output:** `ConnectionStatus(is_connected, health_status, latency_ms, error_message, checked_at)`.  
**EP-06 stub:** Returns `is_connected=False, health_status=UNKNOWN` — correct because no real HTTP call is made.  
**EP-07 implementation:** Make a lightweight probe request (e.g., list models with `limit=1`). Measure wall-clock latency. Return `HEALTHY` on 2xx, `DEGRADED` on slow response, `UNHEALTHY` on error.  
**Why async:** Every real implementation will make a network call. Declaring it async now avoids a breaking change in EP-07.

#### `list_models()` → `list[ModelMetadata]`

**Purpose:** Return the set of models available through this provider.  
**Input:** None.  
**Output:** A list of `ModelMetadata` objects with id, display_name, context_window, capabilities, and cost data.  
**EP-06 stub:** Returns a hardcoded list of well-known models at the time of EP-06.  
**EP-07 implementation:** Fetch from the provider's `/models` endpoint where available (OpenAI, Anthropic); keep the hardcoded list for providers without a model discovery API.  
**Cost engine hook:** `ModelMetadata.input_cost_per_1k` and `output_cost_per_1k` fields are pre-wired for EP-08.

#### `complete(request: ProviderRequest)` → `ProviderResponse`

**Purpose:** Submit a text completion (chat) request to the provider.  
**Input:** `ProviderRequest(model_id, messages, max_tokens, temperature, stream, extra)`.  
**Output:** `ProviderResponse(model_id, content, usage, finish_reason, raw_response)`.  
**EP-06 stub:** Raises `NotImplementedError("EP-07")`.  
**EP-07 implementation:** Call the provider's chat completions API. Normalise the response into `ProviderResponse`. Extract token usage into `UsageData`. Pass `raw_response` for debugging.  
**Why the common model matters:** The service layer calls `provider.complete(request)` and receives a `ProviderResponse` regardless of whether the underlying provider is OpenAI or Anthropic. Token counting and cost attribution work the same way across all providers.

#### `verify_auth()` → `bool`

**Purpose:** Confirm that the configured API key (or OAuth token) is valid.  
**Input:** None — credentials come from the config's `SecretReference`.  
**Output:** `True` if authenticated, `False` if not. (May also raise `AuthenticationError`.)  
**EP-06 stub:** Raises `NotImplementedError("EP-07")`.  
**EP-07 implementation:** Make the cheapest authenticated request the provider allows (e.g., list models, check account balance). Return `True` on success.  
**Security note:** This method must never log the API key value. It should only log the outcome.

#### `config` → `ProviderConfig` (concrete)

A read-only property returning `self._config`. Concrete — all adapters inherit this. Provides access to `base_url`, `timeout_seconds`, and provider-specific fields without the adapter exposing them individually.

#### `display_name` → `str` (concrete)

A convenience shortcut for `self._config.display_name`. Adapters do not override this.

### Why Abstract Interfaces Are Better Than Provider-Specific Implementations

Without an interface, the service layer looks like this:

```python
# Without interface — tightly coupled to every provider
if conn.provider_type == ProviderType.OPENAI:
    import openai
    client = openai.AsyncOpenAI(api_key=resolve_secret(conn))
    response = await client.chat.completions.create(...)
    usage = UsageData(prompt_tokens=response.usage.prompt_tokens, ...)
elif conn.provider_type == ProviderType.ANTHROPIC:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=resolve_secret(conn))
    response = await client.messages.create(...)
    usage = UsageData(prompt_tokens=response.usage.input_tokens, ...)
# ... 5 more elif blocks
```

With the `AIProvider` interface:

```python
# With interface — provider is irrelevant to the caller
provider = factory.create(config)
response = await provider.complete(request)
usage = response.usage  # already normalised
```

The second form adds a new provider with zero changes to the service layer.

---

## 5. Registry Pattern

**File:** `app/providers/registry.py`  
**Spec:** F-025

### What the Registry Does

The `ProviderRegistry` maps a `ProviderType` enum value to the Python *class* (not an instance) that implements `AIProvider` for that provider.

```
ProviderRegistry._registry = {
    ProviderType.OPENAI:       OpenAIProvider,
    ProviderType.ANTHROPIC:    AnthropicProvider,
    ProviderType.GROK:         GrokProvider,
    ProviderType.GOOGLE:       GoogleProvider,
    ProviderType.AZURE_OPENAI: AzureOpenAIProvider,
    ProviderType.OPENROUTER:   OpenRouterProvider,
    ProviderType.OLLAMA:       OllamaProvider,
}
```

### Public API

```python
registry.register(ProviderType.OPENAI, OpenAIProvider)   # add mapping
registry.get(ProviderType.OPENAI)                        # lookup — raises KeyError if missing
registry.is_registered(ProviderType.OPENAI)              # boolean check
registry.registered_types()                             # list of known types
len(registry)                                           # count
```

### The Module-Level Singleton

```python
_default_registry: ProviderRegistry | None = None

def get_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        from app.providers.factory import ProviderFactory   # lazy import
        _default_registry = ProviderFactory.build_default_registry()
    return _default_registry
```

**Why lazy?** If this import ran at module load time, a circular import would occur: `registry.py` imports `factory.py`, which imports `registry.py`. The lazy import inside the function body breaks the cycle — by the time the function runs, both modules are fully loaded.

**Why a module-level singleton?** The default registry is always the same seven providers. There is no reason to rebuild it on each request. The singleton is thread-safe in CPython because dictionary assignments under the GIL are atomic.

### Dependency Injection

The `ProviderRegistry` is designed for injection:

```python
# In tests — inject a custom registry
test_registry = ProviderRegistry()
test_registry.register(ProviderType.OPENAI, MockOpenAIProvider)
factory = ProviderFactory(test_registry)

# In production — use the default singleton
factory = ProviderFactory(get_registry())
```

This allows unit tests to inject mock providers without patching global state.

### Plugin Architecture

The registry is extensible by design. A plugin that adds a new AI provider only needs to:

1. Call `get_registry().register(ProviderType.NEW_PROVIDER, NewProvider)` at startup.
2. No other code changes required.

In future, this could be driven by a configuration file or entry_points in `pyproject.toml`.

### Adding a New Provider (Step by Step)

```python
# Step 1: Extend the ProviderType enum
class ProviderType(enum.StrEnum):
    ...
    MISTRAL = "mistral"   # add this

# Step 2: Add a config subclass (config.py)
class MistralConfig(ProviderConfig):
    provider_type: str = "mistral"
    base_url: str | None = "https://api.mistral.ai/v1"

# Step 3: Create the adapter (adapters/mistral.py)
class MistralProvider(AIProvider):
    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.MISTRAL
    ...

# Step 4: Register it (factory.py)
registry.register(ProviderType.MISTRAL, MistralProvider)
```

No changes to any service, repository, API router, or test unrelated to Mistral.

---

## 6. Factory Pattern

**File:** `app/providers/factory.py`  
**Spec:** F-026

### What the Factory Does

The `ProviderFactory` is the single point of construction for `AIProvider` instances. It takes a `ProviderConfig` and returns a fully initialised provider adapter.

```python
class ProviderFactory:
    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def create(self, config: ProviderConfig) -> AIProvider:
        provider_type = ProviderType(config.provider_type)   # validate the type
        cls = self._registry.get(provider_type)              # look up the class
        return cls(config)                                   # construct the adapter
```

### Why the Factory Exists

Without a factory:

```python
# Caller must know which class to use
if config.provider_type == "openai":
    from app.providers.adapters.openai import OpenAIProvider
    provider = OpenAIProvider(config)
elif config.provider_type == "anthropic":
    ...
```

With the factory:

```python
provider = factory.create(config)   # caller doesn't need to know
```

The factory encapsulates the class-selection logic and makes it testable in one place.

### Credential Injection

The factory does not resolve secrets — that is the responsibility of the service layer, which populates `config.api_key_ref` with a `SecretReference` before calling `factory.create()`. The adapter receives the reference and resolves it at call time (EP-07+).

This separation ensures that:
- The factory never handles raw credentials.
- Secret resolution can be swapped (env vars → Vault → AWS Secrets Manager) without changing the factory.

### `build_default_registry()` — Static Method

```python
@staticmethod
def build_default_registry() -> ProviderRegistry:
    from app.providers.adapters.openai import OpenAIProvider
    ...
    registry = ProviderRegistry()
    registry.register(ProviderType.OPENAI, OpenAIProvider)
    ...
    return registry
```

The deferred imports prevent circular import errors at module load time. This method is called exactly once, from `get_registry()` in `registry.py`, and its result is cached.

### Error Handling

If an unregistered `ProviderType` is passed:

```python
provider_type = ProviderType(config.provider_type)
# raises ValueError if config.provider_type is not a valid ProviderType value

cls = self._registry.get(provider_type)
# raises KeyError: "No provider registered for type 'mistral'"
```

EP-07 service layer should catch `KeyError` from the factory and return HTTP 422 (unsupported provider type) to the caller.

---

## 7. Capability Model

**File:** `app/providers/capabilities.py`  
**Spec:** F-027

### What `ProviderCapabilities` Is

`ProviderCapabilities` is a frozen dataclass that describes what a provider can do. It is declared once per adapter as a module-level constant and never changes at runtime.

```python
@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    supports_streaming: bool = False
    supports_tool_calling: bool = False
    supports_vision: bool = False
    supports_audio: bool = False
    supports_usage_api: bool = False
    has_rate_limits: bool = True
    requires_api_key: bool = True
    supports_oauth: bool = False
    supports_fine_tuning: bool = False
    supports_function_calling: bool = False
    supports_web_sessions: bool = False
    max_context_window: int | None = None
    supported_model_ids: frozenset[str] = field(default_factory=frozenset)
```

### Capability Reference

#### `supports_streaming`

Whether the provider can stream partial tokens back to the client via SSE (Server-Sent Events). Affects the API response format and the frontend display. All seven providers support streaming. Without this flag, the UI must poll for a complete response rather than displaying tokens as they arrive.

#### `supports_tool_calling`

Whether the provider can call user-defined tools during a completion request (e.g., "search the web", "run code"). This is a prerequisite for AI agent workflows. OpenAI, Anthropic, Google, and Grok support tool calling. Ollama supports it for capable models only.

#### `supports_vision`

Whether the provider can process image inputs. This enables use cases like "analyse this chart" or "describe this screenshot." OpenAI (GPT-4o), Anthropic (Claude), Google (Gemini), Grok (Grok-2 Vision), OpenRouter, Azure OpenAI, and Ollama (selected models) support vision.

#### `supports_audio`

Whether the provider can process audio inputs (speech-to-text, audio understanding). Currently supported by OpenAI (Whisper integration in GPT-4o) and Google (Gemini 1.5 Pro, 2.0 Flash). Required for transcription and voice interface features.

#### `supports_usage_api`

Whether the provider exposes a separate API endpoint to query historical usage and costs. OpenAI, Anthropic, Google, Azure, and Grok support this. Ollama does not (it is self-hosted with no billing). This flag gates the "fetch usage from provider" feature in EP-08.

#### `has_rate_limits`

Whether the provider enforces rate limits (requests per minute / tokens per minute). All cloud providers do. Ollama does not (self-hosted, rate-limited only by your hardware). When `True`, the `RateLimitError.retry_after_seconds` field is meaningful.

#### `requires_api_key`

Whether the provider requires an API key for authentication. All cloud providers do. Ollama does not (`requires_api_key=False`). When `False`, the `config.api_key_ref` can be `None` without failing validation.

#### `supports_oauth`

Whether the provider supports OAuth 2.0 in addition to API keys. Google and Azure OpenAI support OAuth (service account credentials, Azure AD). This enables enterprise SSO integration where rotating API keys is prohibited.

#### `supports_fine_tuning`

Whether the provider allows fine-tuning base models on custom datasets. Supported by OpenAI and Google. Fine-tuning creates custom model IDs that appear in `list_models()` for that org.

#### `supports_function_calling`

Whether the provider supports the function-calling format (a structured schema for tools). This is closely related to `supports_tool_calling` but specifically refers to the structured JSON-schema function definition format popularised by OpenAI's API. Most modern providers support it.

#### `supports_web_sessions`

Whether the provider can maintain a web browsing session across turns (e.g., Operator-style agents that interact with websites). Reserved for future use; no current provider has this enabled.

#### `max_context_window`

The maximum number of tokens the provider can process in a single request (input + output). Examples:
- GPT-4o: 128,000 tokens
- Claude 3.5 Sonnet: 200,000 tokens
- Gemini 1.5 Pro: **2,000,000** tokens (largest in the framework)
- Grok-2: 131,072 tokens

This field drives context length validation in the service layer (EP-07+) and helps users select the right model for long documents.

#### `supported_model_ids`

A `frozenset[str]` of model IDs known to be available for this provider at the time of EP-06. Used for fast validation without a network call ("is `gpt-5` a valid model ID?"). EP-07 will supplement this with live model discovery.

### Provider Capability Matrix

| Capability | OpenAI | Anthropic | Grok | Google | Azure | OpenRouter | Ollama |
|-----------|--------|-----------|------|--------|-------|------------|--------|
| Streaming | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Tool Calling | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Vision | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Audio | ✓ | — | — | ✓ | — | — | — |
| Usage API | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| Rate Limits | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| API Key | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| OAuth | — | — | — | ✓ | ✓ | — | — |
| Fine Tuning | ✓ | — | — | ✓ | ✓ | — | — |
| Function Calling | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

### Why `frozen=True, slots=True`

- **`frozen=True`:** Capabilities are immutable. A provider's capabilities do not change at runtime. Freezing prevents accidental mutation and makes the object safely hashable.
- **`slots=True`:** Eliminates the `__dict__` per instance, saving memory. Since these are module-level constants (one per adapter, not one per request), the saving is minimal — but `slots=True` also makes attribute access faster.

### Why Module-Level Constants

Each adapter declares:

```python
_CAPABILITIES = ProviderCapabilities(
    supports_streaming=True,
    ...
)

class OpenAIProvider(AIProvider):
    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES        # returns the module-level constant
```

This means `provider.capabilities` is a dictionary lookup (returning a pre-built object), not a new object creation on each access.

### How Capabilities Enable Multi-Provider Support

The service layer can make decisions without knowing the provider:

```python
if not provider.capabilities.supports_vision:
    raise ValueError("This provider does not support image inputs")

if not provider.capabilities.supports_streaming:
    request.stream = False  # degrade gracefully

if provider.capabilities.max_context_window and len(tokens) > provider.capabilities.max_context_window:
    raise ValueError(f"Request exceeds context window of {provider.capabilities.max_context_window}")
```

This code works identically for all seven providers.

---

## 8. Configuration Model

**File:** `app/providers/config.py`  
**Spec:** F-028

### Why Typed Configuration

Before EP-06, a `ProviderConnection` had a JSONB `configuration` column with no schema enforcement. Any key could be set to any value. Mistakes only surfaced at runtime (at the first API call).

EP-06 introduces a Pydantic v2 config hierarchy that validates at construction time, documents required fields per provider, and — critically — prevents secrets from being stored in the wrong place.

### `ProviderConfig` — Base Class

```python
class ProviderConfig(BaseModel):
    provider_type: str          # must match a ProviderType value
    display_name: str           # human-readable name for logs/UI
    api_key_ref: SecretReference | None = None   # reference to API key, never the key itself
    base_url: str | None = None                  # override default endpoint
    timeout_seconds: float = 30.0               # per-request timeout
    extra: dict[str, Any] = Field(default_factory=dict)    # provider-specific extras
    config_version: int = 1                     # for future schema migration
```

#### The Credential Leak Guard

```python
@model_validator(mode="after")
def _no_plaintext_secrets(self) -> ProviderConfig:
    sensitive_keys = {"api_key", "secret", "password", "token", "key"}
    for k in self.extra:
        if any(s in k.lower() for s in sensitive_keys):
            raise ValueError(
                "extra config must not contain credential keys;"
                f" use SecretReference instead: {k!r}"
            )
    return self
```

This validator runs after field validation. If the caller tries to store an API key directly in `extra` (`{"api_key": "sk-..."}` or `{"openai_key": "sk-..."}`), it raises `ValueError` immediately — at configuration time, not at the first API call.

This extends EP-03.5's `validate_provider_configuration()` (which guards the ORM layer) with an equivalent guard at the Python config layer.

#### `config_version`

Reserved for schema evolution. When EP-09 needs to change a config field, it can migrate stored configs by checking `config_version < 2` and applying the transform. Without this field, schema migration requires an Alembic migration over all stored JSONB blobs.

### `SecretReference` — The Secret Indirection Model

```python
class SecretReference(BaseModel):
    model_config = {"frozen": True}
    secret_store: str = "env"   # "env", "vault", "aws_secrets_manager"
    secret_key: str             # the name/path in the secret store

    def __repr__(self) -> str:
        return f"SecretReference(secret_store={self.secret_store!r}, secret_key=<redacted>)"
```

`SecretReference` is a pointer, not a value. It says "the API key is in environment variable `OPENAI_API_KEY`." The actual resolution happens in the service layer (EP-07+) when the API call is being made.

The custom `__repr__` redacts `secret_key`, preventing accidental exposure in log lines like `logger.info("Creating provider with config=%s", config)`.

### Provider-Specific Config Subclasses

Each provider has a typed subclass that locks `provider_type` and adds provider-specific fields:

| Class | Key Fields |
|-------|-----------|
| `OpenAIConfig` | `organization_id`, `project_id` (both optional) |
| `AnthropicConfig` | `anthropic_version` (API version header) |
| `GrokConfig` | `base_url` defaults to `https://api.x.ai/v1` |
| `GoogleConfig` | `project_id`, `location` (for Vertex AI) |
| `AzureOpenAIConfig` | `azure_endpoint` (required!), `api_version`, `deployment_name` |
| `OpenRouterConfig` | `http_referer`, `x_title` (for OpenRouter analytics) |
| `OllamaConfig` | `base_url` defaults to `http://localhost:11434`, `requires_api_key=False` |

`AzureOpenAIConfig.azure_endpoint` is the only required (non-defaulted) field across all configs. Azure requires a per-deployment endpoint URL (`https://<resource>.openai.azure.com/`), and there is no sensible default.

### Security Properties

- **No secrets in the database:** `ProviderConnection.configuration` JSONB only stores non-secret metadata. Secrets live in environment variables or a secrets manager.
- **No secrets in Python objects:** `ProviderConfig.api_key_ref` holds a `SecretReference`, not a string.
- **No secrets in logs:** `SecretReference.__repr__` redacts `secret_key`.
- **Guard at construction:** The validator prevents secrets from slipping into `extra`.
- **Frozen references:** `SecretReference` is frozen (`model_config = {"frozen": True}`), preventing mutation after construction.

---

## 9. Error Model

**File:** `app/providers/errors.py`  
**Spec:** F-029

### The Problem: Every Provider Has Different Errors

OpenAI raises `openai.RateLimitError`. Anthropic raises `anthropic.APIStatusError` with status 529. Google raises `google.api_core.exceptions.ResourceExhausted`. Without normalisation, the service layer must catch seven different exception types for the same logical failure.

### The Solution: Normalised Error Hierarchy

```
Exception
  └── ProviderError                   ← base for all provider errors
        ├── RateLimitError            ← 429 Too Many Requests (retryable)
        ├── AuthenticationError       ← 401/403 credentials invalid (not retryable)
        ├── NetworkError              ← connection timeout, DNS failure (retryable)
        ├── QuotaExceededError        ← billing quota exhausted (not retryable)
        ├── InvalidRequestError       ← bad request, invalid model (not retryable)
        └── InternalProviderError     ← provider 5xx error (retryable)
```

### `ProviderError` — Base Class

```python
class ProviderError(Exception):
    def __init__(
        self,
        message: str,
        provider_type: str | None = None,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_type = provider_type    # which provider failed
        self.retryable = retryable           # should the caller retry?
```

`provider_type` is stored on the exception so that a generic error handler can log "OpenAI rate limit exceeded" without parsing the message string.

`retryable` is the key flag for the retry layer (EP-07+). If `retryable is True`, the service layer should apply its `RetryPolicy`. If `False`, it should surface the error to the caller immediately.

### Error Classification

| Error | Retryable? | When to Raise |
|-------|------------|---------------|
| `RateLimitError` | Yes | Provider returns 429 |
| `AuthenticationError` | No | Provider returns 401/403; key is invalid |
| `NetworkError` | Yes | Connection timeout, DNS failure, socket reset |
| `QuotaExceededError` | No | Billing quota for the month is exhausted |
| `InvalidRequestError` | No | Bad model ID, missing required field, token limit exceeded |
| `InternalProviderError` | Yes | Provider returns 500/503/529 |

### `RateLimitError` — Extra Field

```python
class RateLimitError(ProviderError):
    def __init__(self, ..., *, retry_after_seconds: float | None = None) -> None:
        super().__init__(..., retryable=True)
        self.retry_after_seconds = retry_after_seconds
```

`retry_after_seconds` is populated from the `Retry-After` HTTP header when the provider includes it. The retry policy can use this to wait the exact amount of time instead of guessing.

### How Adapters Will Use This in EP-07

```python
# Inside OpenAIProvider.complete() — EP-07 implementation sketch
try:
    response = await openai_client.chat.completions.create(...)
except openai.RateLimitError as e:
    raise RateLimitError(
        str(e),
        provider_type="openai",
        retry_after_seconds=_parse_retry_after(e),
    ) from e
except openai.AuthenticationError as e:
    raise AuthenticationError(str(e), provider_type="openai") from e
```

The service layer only ever catches `ProviderError` subclasses — it never imports from `openai` or `anthropic`.

### Future Retry Implementation

The retry policy interfaces in `retry.py` are ready for EP-07 to implement:

```python
class RetryPolicy(ABC):
    def should_retry(self, attempt: int, error: Exception) -> bool: ...
    def get_delay(self, attempt: int) -> float: ...
    def get_config(self) -> RetryConfig: ...
```

An EP-07 implementation would:
1. Catch `ProviderError` from `provider.complete()`.
2. Call `retry_policy.should_retry(attempt, error)` — checks `error.retryable` and `attempt < max_attempts`.
3. Call `retry_policy.get_delay(attempt)` — applies exponential backoff with jitter.
4. Sleep and retry.

---

## 10. Adapter Design

**Directory:** `app/providers/adapters/`

### Design Principles

All seven adapters follow the same pattern:
1. Module-level `_CAPABILITIES` constant (frozen, shared across all instances).
2. Module-level `_MODELS` list (hardcoded known models at EP-06 time).
3. `provider_type` property returns the corresponding `ProviderType` enum value.
4. `capabilities` property returns the module-level `_CAPABILITIES` constant.
5. `check_connection()` returns `ConnectionStatus(is_connected=False, health_status=UNKNOWN, ...)`.
6. `list_models()` returns a copy of `_MODELS`.
7. `complete()` raises `NotImplementedError("EP-07")`.
8. `verify_auth()` raises `NotImplementedError("EP-07")`.

### OpenAI (`adapters/openai.py`)

**Provider type:** `ProviderType.OPENAI`  
**Models:** GPT-4o, GPT-4o Mini, GPT-4 Turbo, GPT-3.5 Turbo (deprecated)  
**Max context:** 128,000 tokens  
**Notable capabilities:** Streaming, tool calling, vision, **audio**, usage API, **fine tuning**

OpenAI is the reference implementation for commercial cloud providers. GPT-3.5 Turbo is marked `is_deprecated=True` because OpenAI has sunset it. This flag surfaces in the UI to guide users toward GPT-4o Mini.

**EP-07:** Will call the OpenAI Python SDK (`AsyncOpenAI.chat.completions.create()`). Credential resolved via `config.api_key_ref`.

### Anthropic (`adapters/anthropic.py`)

**Provider type:** `ProviderType.ANTHROPIC`  
**Models:** Claude 3.5 Sonnet, Claude 3.5 Haiku, Claude 3 Opus  
**Max context:** **200,000 tokens** (largest context among API providers)  
**Notable capabilities:** Streaming, tool calling, vision; **no audio, no fine tuning**

Anthropic models are known for their large context windows and strong instruction-following. The `AnthropicConfig.anthropic_version` field sets the `anthropic-version` HTTP header required by the Messages API.

**EP-07:** Will call `anthropic.AsyncAnthropic().messages.create()`. Input token field is named `input_tokens` (not `prompt_tokens`) — the adapter must normalise to `UsageData`.

### Grok (`adapters/grok.py`)

**Provider type:** `ProviderType.GROK`  
**Models:** Grok-2, Grok-2 Vision, Grok-Beta  
**Max context:** 131,072 tokens  
**Notable capabilities:** Streaming, tool calling, vision (Grok-2 Vision only); **no audio, no fine tuning**

Grok is xAI's provider with an OpenAI-compatible API at `https://api.x.ai/v1`. The `GrokConfig` has `base_url` defaulting to that endpoint. Grok-2 Vision has a smaller context window (32,768 tokens) than the text-only Grok-2.

**EP-07:** API is OpenAI-compatible, so it may reuse the OpenAI SDK pointed at the Grok base URL.

### Google (`adapters/google.py`)

**Provider type:** `ProviderType.GOOGLE`  
**Models:** Gemini 1.5 Pro, Gemini 1.5 Flash, Gemini 1.5 Flash 8B, Gemini 2.0 Flash  
**Max context:** **2,000,000 tokens** (Gemini 1.5 Pro — largest in the entire framework)  
**Notable capabilities:** Streaming, tool calling, vision, **audio**, usage API, **OAuth**, **fine tuning**

Google is the most capable provider in capability terms: it supports both OAuth (enterprise) and API keys, audio input, fine tuning, and the largest context window by far. `GoogleConfig` includes `project_id` and `location` for Vertex AI deployments.

**EP-07:** Will use `google-generativeai` SDK or Vertex AI SDK. OAuth path requires service account credentials.

### Azure OpenAI (`adapters/azure_openai.py`)

**Provider type:** `ProviderType.AZURE_OPENAI`  
**Models:** GPT-4o, GPT-4o Mini, GPT-4 Turbo, GPT-3.5 Turbo (deprecated)  
**Max context:** 128,000 tokens  
**Notable capabilities:** Streaming, tool calling, vision, usage API, **OAuth**, fine tuning; **no audio**

Azure OpenAI proxies OpenAI models through Azure's infrastructure with enterprise data privacy guarantees (data does not leave your Azure tenant). `AzureOpenAIConfig.azure_endpoint` is **required** — there is no default because it is per-customer. `api_version` matters: Azure OpenAI APIs are versioned differently from OpenAI's.

**EP-07:** Will use the `openai.AsyncAzureOpenAI` client with `azure_endpoint` and `api_version`.

### OpenRouter (`adapters/openrouter.py`)

**Provider type:** `ProviderType.OPENROUTER`  
**Models:** GPT-4o (via OpenRouter), Claude 3.5 Sonnet (via OpenRouter), Gemini 1.5 Pro (via OpenRouter), Llama 3.1 405B (via OpenRouter)  
**Max context:** 2,000,000 tokens (inherited from the Gemini model)  
**Notable capabilities:** Streaming, tool calling, vision; **no audio, no fine tuning**

OpenRouter is a meta-provider that routes requests to the best available underlying provider. It uses an OpenAI-compatible API at `https://openrouter.ai/api/v1`. Model IDs use the format `provider/model` (e.g., `anthropic/claude-3-5-sonnet`). `OpenRouterConfig.http_referer` and `x_title` are used for OpenRouter's per-app analytics.

**EP-07:** Will use the OpenAI SDK pointed at the OpenRouter base URL.

### Ollama (`adapters/ollama.py`)

**Provider type:** `ProviderType.OLLAMA`  
**Models:** Llama 3.2, Llama 3.1, Mistral, Code Llama, Phi-3, Gemma 2  
**Max context:** `None` (model-dependent)  
**Notable capabilities:** Streaming, tool calling, vision (selected models); **no audio, no usage API, no rate limits, no API key required, no fine tuning**

Ollama is a self-hosted provider — it runs on the user's infrastructure with no cloud dependency. This makes it fundamentally different from all other providers:
- `requires_api_key=False` — the API is unauthenticated by default.
- `has_rate_limits=False` — rate limits depend only on hardware.
- `supports_usage_api=False` — there is no billing/usage endpoint.
- `max_context_window=None` — varies per model and available RAM.

`OllamaConfig.base_url` defaults to `http://localhost:11434`. Enterprise deployments running Ollama on a remote server override this.

**EP-07:** Will call the Ollama REST API (`POST /api/chat`). No SDK required — pure HTTP.

### Why They Currently Return `NotImplementedError`

The `complete()` and `verify_auth()` methods raise `NotImplementedError("EP-07")` because:

1. **No external SDK dependencies in EP-06.** The provider package has zero runtime dependencies beyond what FastAPI already uses. Adding `openai`, `anthropic`, and `google-generativeai` adds ~50 MB of dependencies and potential import-time failures.
2. **Clean contract first.** The interface is agreed upon before any implementation is written. EP-07 fills in behind the agreed interface.
3. **Testable without network.** The 132 EP-06 tests run in milliseconds with no mocks, no patches, and no external calls.

---

## 11. Architecture Review

### Layering

EP-06 sits between the database layer (EP-03: `ProviderConnection` ORM) and the future API execution layer (EP-07):

```
EP-03: ProviderConnection (database row)
  ↓
EP-06: ProviderConfig (validated Python object, no I/O)
  ↓
EP-06: ProviderFactory → AIProvider (adapter instance, no I/O)
  ↓
EP-07: provider.complete() (real API call)
  ↓
EP-08: UsageData → Cost engine
```

The layering is clean. No layer reaches across a boundary. `ProviderConfig` never imports SQLAlchemy. The adapter never imports ORM models.

### SOLID Principles

| Principle | How EP-06 Applies |
|-----------|-------------------|
| Single Responsibility | Each file has one job: `interface.py` defines the contract; `registry.py` maps types; `factory.py` constructs; `config.py` validates. |
| Open/Closed | Adding a provider is open (add a file, add one registry line) without modifying any existing code. |
| Liskov Substitution | Any `AIProvider` subclass can be used wherever `AIProvider` is expected. Tests use the concrete adapters interchangeably. |
| Interface Segregation | `HealthCheckInterface` is separate from `AIProvider`. Clients that only need health checking don't take a dependency on the full `AIProvider`. |
| Dependency Inversion | The service layer depends on `AIProvider` (abstract); only the factory depends on concrete adapter classes. |

### Dependency Inversion in Detail

```
app/services/  ────────────────────────────────►  app/providers/interface.py
                  depends on AIProvider (ABC)              ▲
                                                           │ implements
                                               app/providers/adapters/openai.py
```

The service layer is not aware of `OpenAIProvider`. The factory is. This means:
- The service layer can be tested without any real provider.
- Swapping OpenAI for a custom provider requires zero service layer changes.

### Extensibility Assessment

| Dimension | Assessment |
|-----------|-----------|
| New provider | 4 steps, ~50 lines, no existing file edits |
| New capability flag | Add one field to `ProviderCapabilities`, update 7 adapters |
| New config field | Add one field to the appropriate config subclass |
| New error type | Add one subclass to `errors.py` |
| New retry strategy | Implement `RetryPolicy` ABC in EP-07, inject via constructor |

### Technical Debt

| Item | Priority | When to Address |
|------|----------|----------------|
| `list_models()` returns hardcoded stubs — real data from provider APIs | High | EP-07 |
| `check_connection()` returns `UNKNOWN` — no real HTTP probe | High | EP-07 |
| `RetryPolicy` ABC has no concrete implementation | Medium | EP-07 |
| `CircuitBreaker` ABC has no concrete implementation | Medium | EP-07/08 |
| `HealthCheckInterface` has no concrete implementation | Medium | EP-07 |
| Model costs (`input_cost_per_1k`) are `None` — no pricing data yet | Low | EP-08 |
| `config_version` exists but no migration logic exists yet | Low | EP-09 |

---

## 12. Production Readiness

### Configuration

All provider configuration flows through typed, validated `ProviderConfig` subclasses. No raw dict access. Pydantic v2 validates at construction time. Required fields (`AzureOpenAIConfig.azure_endpoint`) will fail at object construction, not at the first API call.

### Security

| Control | Status | Notes |
|---------|--------|-------|
| No plaintext secrets in config | ✓ | `_no_plaintext_secrets` validator enforces |
| Secrets not in DB | ✓ | `ProviderConnection.configuration` JSONB is non-secret by design (EP-03) |
| Secrets not in logs | ✓ | `SecretReference.__repr__` redacts `secret_key` |
| No SDK credentials in source | ✓ | No external SDK imported; no hardcoded keys |
| Frozen secret references | ✓ | `SecretReference` is immutable |

### Observability

**Current state (EP-06):** None. The adapters make no calls, so there is nothing to observe.

**EP-07 must add:**
- Structured log fields: `provider_type`, `model_id`, `duration_ms`, `tokens_used` on every completion call.
- Prometheus counters: `provider_requests_total`, `provider_errors_total` labelled by `provider_type` and `error_type`.
- Prometheus histograms: `provider_request_duration_seconds` labelled by `provider_type` and `model_id`.
- Tracing spans: One span per `complete()` call with model and token attributes.

**EP-06 pre-wired for observability:**
- `ConnectionStatus.latency_ms` field — EP-07 fills this in `check_connection()`.
- `ProviderError.provider_type` field — structured error reporting without string parsing.
- `UsageData.prompt_tokens`, `completion_tokens` — token-level telemetry ready for the cost engine.

### Logging

No logging occurs in EP-06 (no I/O to observe). EP-07 must log at `DEBUG` level for every provider request with:
- `provider_type`
- `model_id`
- Request size in tokens (input)
- Response size in tokens (output)
- Duration in milliseconds

Never log:
- Raw API key values or `secret_key`
- The raw HTTP request/response body at INFO or above (may contain user data)

### Metrics Strategy

```
provider_requests_total{provider_type="openai", model_id="gpt-4o", status="success"}
provider_requests_total{provider_type="openai", model_id="gpt-4o", status="rate_limited"}
provider_request_duration_seconds{provider_type="openai", model_id="gpt-4o", le="0.5"}
provider_tokens_total{provider_type="openai", model_id="gpt-4o", direction="input"}
```

### Failure Handling

EP-06 defines the error taxonomy. EP-07 must:
1. Catch provider SDK exceptions inside adapters.
2. Re-raise as the appropriate `ProviderError` subclass.
3. Service layer catches `ProviderError`, checks `error.retryable`, applies `RetryPolicy`.
4. On non-retryable errors, surface HTTP 422 or 502 depending on error type.

### Future Improvements

| Improvement | Description |
|-------------|-------------|
| Secret resolution abstraction | EP-07 needs a `SecretResolver` interface to swap env vars for Vault |
| Per-provider rate limit tracking | Redis counter per `(org_id, provider_type)` per minute |
| Model price feed | Automated price updates from provider pricing APIs |
| Dynamic capability discovery | Refresh `supported_model_ids` on schedule from provider `/models` |
| Adapter hot-reload | Register new providers without restarting the server |

---

## 13. How EP-07 Builds on EP-06

EP-06 built the frame. EP-07 puts in the engine.

### What EP-07 Must Implement

#### 1. Real Provider API Calls (`complete()`)

Each adapter's `complete()` method must:
1. Resolve the API key from `config.api_key_ref` using a `SecretResolver`.
2. Construct the provider SDK client.
3. Map `ProviderRequest` → provider-specific request format.
4. Call the provider API.
5. Map provider response → `ProviderResponse` with `UsageData`.
6. Catch provider SDK exceptions → re-raise as `ProviderError` subclasses.

```python
# Sketch: EP-07 OpenAIProvider.complete()
async def complete(self, request: ProviderRequest) -> ProviderResponse:
    api_key = await secret_resolver.resolve(self.config.api_key_ref)
    client = AsyncOpenAI(api_key=api_key, base_url=self.config.base_url)
    try:
        resp = await client.chat.completions.create(
            model=request.model_id,
            messages=request.messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            stream=False,
        )
    except openai.RateLimitError as e:
        raise RateLimitError("OpenAI rate limit", provider_type="openai") from e
    return ProviderResponse(
        model_id=resp.model,
        content=resp.choices[0].message.content,
        usage=UsageData(
            prompt_tokens=resp.usage.prompt_tokens,
            completion_tokens=resp.usage.completion_tokens,
            total_tokens=resp.usage.total_tokens,
        ),
        finish_reason=resp.choices[0].finish_reason,
        raw_response=resp.model_dump(),
    )
```

#### 2. Real Authentication (`verify_auth()`)

Each adapter's `verify_auth()` must confirm the configured credentials are valid — the cheapest possible authenticated call.

#### 3. Real Connectivity Check (`check_connection()`)

Replace the stub `ConnectionStatus(is_connected=False, health_status=UNKNOWN)` with a real latency probe:

```python
async def check_connection(self) -> ConnectionStatus:
    start = time.monotonic()
    try:
        await self._probe()   # e.g., list models with limit=1
        latency = (time.monotonic() - start) * 1000
        return ConnectionStatus(
            is_connected=True,
            health_status=HealthStatus.HEALTHY,
            latency_ms=latency,
            checked_at=datetime.now(UTC),
        )
    except Exception as e:
        return ConnectionStatus(
            is_connected=False,
            health_status=HealthStatus.UNHEALTHY,
            error_message=str(e),
            checked_at=datetime.now(UTC),
        )
```

#### 4. Concrete `RetryPolicy`

Implement the `RetryPolicy` ABC using the `RetryConfig` defaults (3 attempts, exponential backoff, 1s → 60s).

#### 5. Concrete `CircuitBreaker`

Implement the `CircuitBreaker` ABC backed by Redis (so state is shared across workers). The circuit opens after N consecutive failures; half-opens after a timeout; closes on the first success.

#### 6. Live Model Discovery

For providers with a `/models` endpoint (OpenAI, Anthropic, Google), replace the hardcoded `_MODELS` list with a live fetch, cached in Redis with a 1-hour TTL.

### Why EP-06 Makes EP-07 Easier

| Without EP-06 | With EP-06 |
|---------------|-----------|
| EP-07 must decide the API for every provider from scratch | EP-07 implements a known interface |
| Adding OpenAI requires refactoring to add Anthropic later | Adding any provider is the same 4-step process |
| Error handling is per-provider throughout the service layer | Error handling is in one place — the adapter |
| Unit testing requires mocking external SDKs everywhere | Unit testing injects a `MockProvider(AIProvider)` |
| Capability checks require per-provider `if/elif` chains | Capability checks read `provider.capabilities.supports_vision` |

---

## 14. Top 30 Engineering Concepts Learned

1. **Abstract Base Classes (ABCs)** — `from abc import ABC, abstractmethod` enforces that subclasses implement every decorated method. Python raises `TypeError` at instantiation time if a method is missing, not at call time.

2. **Dependency Inversion Principle** — High-level modules (service layer) depend on abstractions (`AIProvider`), not on concrete classes (`OpenAIProvider`). Concrete classes depend on abstractions too (adapters implement `AIProvider`).

3. **The Registry Pattern** — A central map from a type token (enum value) to a class or factory function. Decouples the decision of *which class to use* from the code that *uses* the class.

4. **The Factory Pattern** — Encapsulates object construction. Callers ask the factory for an object; the factory decides which class to instantiate and how to wire it. Makes construction logic testable in one place.

5. **Frozen Dataclasses (`frozen=True`)** — Makes a dataclass immutable after construction (sets `__hash__`, blocks `__setattr__`). Safe to share across threads. Idiomatic for value objects that represent facts, not mutable state.

6. **`slots=True` on Dataclasses** — Replaces `__dict__` with a fixed set of slot descriptors. Reduces memory per instance and makes attribute access faster.

7. **Lazy Imports to Break Circular Dependencies** — Placing `from module import X` inside a function body defers the import until the function is called, by which time both modules are fully loaded. Used in `get_registry()` to break the `registry → factory → registry` circular import.

8. **Module-Level Singletons** — A module-level variable that is initialised once and reused (`_default_registry`). In CPython, this is thread-safe for simple assignments because of the GIL.

9. **`enum.StrEnum`** — Combines `str` and `enum.Enum` without the `(str, enum.Enum)` metaclass confusion. Values compare equal to their string representation. Required by Ruff rule UP042.

10. **`@model_validator(mode="after")` in Pydantic v2** — Runs after all field validators. Receives the fully-constructed model instance. Used for cross-field validation (e.g., checking that no field in `extra` matches a credential pattern).

11. **`SecretReference` Pattern** — Never store secret values; store a reference to where the secret lives. The reference is serialisable, loggable (with redaction), and switchable (env → Vault) without changing the code that holds it.

12. **`__repr__` Redaction** — Override `__repr__` on sensitive models to omit secret values. Python's default repr includes all fields; custom repr prevents accidental log exposure.

13. **`retryable` as a First-Class Error Property** — Attaching the retry hint to the exception itself means the retry logic doesn't need a mapping table of "which exception types are retryable." The exception knows.

14. **Normalised Error Taxonomy** — A hierarchy of provider-agnostic exception classes that every adapter maps its SDK exceptions into. The service layer catches `ProviderError` subclasses, never `openai.RateLimitError`.

15. **`NotImplementedError` as Contract Enforcement** — Raising `NotImplementedError("EP-07")` makes the stub's purpose explicit: "this works as a contract stub; the implementation comes in the next epic." Better than a silent `pass` or `return None`.

16. **`frozenset` for Immutable Sets** — Used in `ProviderCapabilities.supported_model_ids` and `ModelMetadata.capabilities`. `frozenset` is hashable and cannot be mutated, making it safe to use as a module-level constant.

17. **`ModelCapabilityFlag` as Per-Model Capabilities vs. `ProviderCapabilities` as Per-Provider** — Two levels of capability metadata: the provider-level flags say "this provider can do X"; the per-model flags say "this specific model ID can do X." A provider may support vision, but not all its models do.

18. **`from __future__ import annotations`** — Defers evaluation of all annotations to strings. Enables forward references (`X | None` in older Python), avoids import cycles from type annotations, and is required by project convention.

19. **`ConnectionStatus` as a Value Object** — The result of a health check is not just `True/False`. It carries latency, error message, and timestamp. Returning a rich value object instead of a boolean enables better diagnostics and logging.

20. **Provider Adapter as the Anti-Corruption Layer** — The adapter translates between the AI FinOps data model (`ProviderRequest`, `ProviderResponse`) and the provider SDK's data model. This is the Anti-Corruption Layer (DDD term): it keeps the domain model clean of provider-specific concepts.

21. **`BackoffStrategy` StrEnum** — Enumerating retry backoff strategies (FIXED, LINEAR, EXPONENTIAL, JITTER) as a StrEnum makes them serialisable, loggable, and configurable from environment variables or config files.

22. **`CircuitBreakerState` StrEnum** — The three states (CLOSED, OPEN, HALF_OPEN) of the circuit breaker pattern represent whether requests are flowing (CLOSED), blocked (OPEN), or being tested (HALF_OPEN). StrEnum makes state transitions loggable.

23. **`RetryConfig` as a Frozen Dataclass** — Retry configuration is a value object: it describes a policy, not state. Frozen makes it immutable and shareable across all adapters using the same policy.

24. **Pluggable Architecture via Registry** — A registry + factory pattern is the foundation of plugin architectures. Third-party packages can register providers without modifying the core codebase (given a public `ProviderRegistry.register()` API).

25. **`is_deprecated=True` on Model Metadata** — Marking deprecated models in the metadata (not just removing them) allows the UI to warn users rather than silently returning errors. `deprecated_at: datetime` enables automatic deprecation notices.

26. **`config_version` for Schema Evolution** — Storing a version number in every config object enables future schema migrations. When `config_version < 2`, apply migration transforms. Without this, the only option is a data migration over all stored configs.

27. **`ProviderConfig.extra` with Validation** — A structured `extra: dict` field is safer than accepting arbitrary keyword arguments. The validator can scan all keys and reject credential-like names. An `**kwargs` approach cannot be validated.

28. **Typed Config Hierarchy (Inheritance)** — `OpenAIConfig(ProviderConfig)` locks `provider_type="openai"` and adds `organization_id`. Consumers who know they have an OpenAI config get typed access to `organization_id`. Consumers who don't care use `ProviderConfig`.

29. **`HealthStatus` as a Four-State Enum** — `HEALTHY / DEGRADED / UNHEALTHY / UNKNOWN` is more useful than `bool`. `UNKNOWN` distinguishes "we haven't checked yet" from `UNHEALTHY` (we checked and it's down). `DEGRADED` enables graduated alerting.

30. **Stub-First, Implement-Later as an Epic Strategy** — By shipping the complete interface in EP-06 with stubs, EP-07 engineers receive a clear, pre-approved contract to implement against. This also enables EP-06 tests to run without network access and without any provider SDK installed.

---

*This document covers EP-06 completely. Read `docs/architecture/Provider-Framework.md` for the architecture overview diagram. Read `docs/engineering/EP-06-Completion-Report.md` for the delivery summary.*
