# Architecture Changelog

## [0.6.5] — EP-06.5 Provider Framework Hardening (2026-06-29)

### Changed

- **REC-01** `AIProvider` now inherits from `HealthCheckInterface` — eliminates duplicate abstract method signatures; every adapter automatically satisfies both interfaces
- **REC-02** `_check_ssrf()` added to `config.py` — validates `base_url` / `azure_endpoint` at construction; blocks cloud-metadata hosts, loopback, private IPs, and non-HTTP/S schemes; no network calls
- **REC-03** `ProviderConfigurationError` added to `errors.py`; `ProviderFactory.create()` now verifies `instance.provider_type == registry_key` post-construction and raises on mismatch
- **REC-04** `ProviderConfig.provider_type` validated against `ProviderType` enum at construction via `@field_validator`; invalid strings rejected with descriptive error listing valid values
- **REC-05** All 7 adapters now implement `get_usage()`, `check_capability()`, and `is_healthy` (was missing on Ollama and others); `AIProvider.get_usage()` added as abstract method
- **REC-06** `models.py` — full message content hierarchy: `TextContent`, `ImageUrlContent`, `ImageBase64Content`, `AudioContent`, `ToolCall`, `ToolCallContent`, `ToolResultContent`; `MessageContent` discriminated union on `Literal["type"]`; `ProviderRequest.messages` typed as `list[Message]` (backwards-compatible with dict input via Pydantic coercion)
- **REC-07** `SecretStoreType` StrEnum added (`env` / `vault` / `aws_secrets_manager`); `SecretReference.secret_store` typed as `SecretStoreType`; `OllamaConfig` dead validator removed; `_allow_http_base_url: ClassVar[bool]` pattern introduced for SSRF opt-in

### Added

- `ProviderConfigurationError` — exported from `app/providers/__init__.py`
- Message content types — all exported from `app/providers/__init__.py`: `Message`, `MessageRole`, `MessageContent`, `TextContent`, `ImageUrlContent`, `ImageBase64Content`, `AudioContent`, `ToolCall`, `ToolCallContent`, `ToolResultContent`
- `docs/knowledge/EP-06.5-Provider-Hardening.md`
- 56 new unit tests in `tests/test_ep06.py` covering all 7 REC items (total: 188 provider tests, 569 suite-wide)

### Security

- SSRF attack surface for provider `base_url` / `azure_endpoint` eliminated at the config layer; cloud-instance metadata services (169.254.169.254, metadata.google.internal, etc.) always blocked regardless of HTTP/S
- Self-hosted Ollama correctly permitted to use `http://localhost` via `OllamaConfig._allow_http_base_url = True`

## [0.6.0] — EP-06 AI Provider Framework (2026-06-29)

### Added

- `app/providers/` — full provider abstraction layer
  - `AIProvider` ABC (`interface.py`) — F-024
  - `ProviderRegistry` + `get_registry()` singleton (`registry.py`) — F-025
  - `ProviderFactory` (`factory.py`) — F-026
  - `ProviderCapabilities` frozen dataclass (`capabilities.py`) — F-027
  - `ProviderConfig` + 7 typed subclasses (`config.py`) — F-028
  - Provider error hierarchy: `ProviderError`, `RateLimitError`, `AuthenticationError`, `NetworkError`, `QuotaExceededError`, `InvalidRequestError`, `InternalProviderError` (`errors.py`) — F-029
  - `RetryPolicy`, `CircuitBreaker` ABCs + `RetryConfig` + `BackoffStrategy` (`retry.py`) — F-030
  - `HealthCheckInterface` ABC (`health.py`) — F-031
  - Shared Pydantic v2 models: `ModelMetadata`, `ConnectionStatus`, `ProviderRequest`, `ProviderResponse`, `UsageData`, `HealthStatus`, `ModelCapabilityFlag` (`models.py`) — F-032
  - `app/providers/adapters/` — stub adapters for all 7 `ProviderType` values
- `tests/test_ep06.py` — 132 unit tests
- `docs/architecture/Provider-Framework.md`
- `docs/engineering/EP-06-Completion-Report.md`
- `docs/knowledge/EP-06-Knowledge-Transfer.md`

### Design notes

- No real HTTP calls anywhere in EP-06; adapter `complete()` / `verify_auth()` raise `NotImplementedError` pending EP-07
- `ProviderConfig` rejects plaintext credentials in `extra`; all secrets must be `SecretReference`
- `ProviderCapabilities` is a frozen dataclass with `slots=True`; module-level constants avoid per-instance allocation
- Circular import between registry and factory is resolved via lazy import inside `get_registry()`
