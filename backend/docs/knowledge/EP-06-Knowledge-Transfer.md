# EP-06 Knowledge Transfer — AI Provider Framework

## What was built

EP-06 adds a **provider abstraction layer** under `app/providers/`. It defines interfaces and stubs for all supported AI providers without making any real API calls.

## File map

| File | Purpose |
|------|---------|
| `app/providers/__init__.py` | Public re-exports |
| `app/providers/models.py` | Shared Pydantic models (F-032) |
| `app/providers/capabilities.py` | `ProviderCapabilities` frozen dataclass (F-027) |
| `app/providers/errors.py` | Exception hierarchy (F-029) |
| `app/providers/retry.py` | Retry/circuit-breaker interfaces (F-030) |
| `app/providers/health.py` | `HealthCheckInterface` ABC (F-031) |
| `app/providers/config.py` | Typed config models per provider (F-028) |
| `app/providers/interface.py` | `AIProvider` ABC (F-024) |
| `app/providers/registry.py` | `ProviderRegistry` + `get_registry()` (F-025) |
| `app/providers/factory.py` | `ProviderFactory` (F-026) |
| `app/providers/adapters/` | One stub per provider (7 files) |

## Key design decisions

### No real API calls in EP-06

All adapter methods that would require network access (`complete`, `verify_auth`) raise `NotImplementedError("EP-07")`. `check_connection` returns `HealthStatus.UNKNOWN` with `is_connected=False` so callers get a valid `ConnectionStatus` without any I/O.

### Registry singleton

`get_registry()` in `registry.py` lazily builds and caches a default `ProviderRegistry` on first call. This avoids import-time side-effects. The factory is imported inside the function to prevent circular imports.

### Credential safety

`ProviderConfig` rejects any `extra` dict key containing `api_key`, `secret`, `password`, `token`, or `key` (case-insensitive). Callers must use `SecretReference` instead. The `SecretReference.__repr__` redacts `secret_key` to prevent accidental log leakage.

### Config hierarchy

Each provider has a typed config subclass (e.g. `OpenAIConfig`, `AzureOpenAIConfig`) that inherits `ProviderConfig`. `AzureOpenAIConfig.azure_endpoint` is required. `OllamaConfig` defaults `requires_api_key=False` because Ollama is self-hosted.

### ProviderCapabilities

Frozen dataclass with `slots=True`. Module-level `_CAPABILITIES` constants in each adapter avoid recreating the object per-instance.

## Extension points for EP-07+

- Implement `complete()` and `verify_auth()` in each adapter by making real HTTP calls.
- `HealthCheckInterface` (in `health.py`) defines the interface for polling; implement a concrete class per provider.
- `RetryPolicy` and `CircuitBreaker` ABCs (in `retry.py`) are ready for concrete implementations.
- `ModelMetadata.input_cost_per_1k` / `output_cost_per_1k` are pre-wired for the cost engine (EP-08+).

## How to register a new provider

1. Add the value to `ProviderType` StrEnum in `app/models/provider_connection.py`.
2. Create `app/providers/config.py` subclass.
3. Create `app/providers/adapters/<name>.py` subclassing `AIProvider`.
4. Add to `ProviderFactory.build_default_registry()`.
