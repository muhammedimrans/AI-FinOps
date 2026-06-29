# EP-06 Architecture Review — AI Provider Framework

**Reviewer:** Principal Software Architect  
**Date:** 2026-06-29  
**Branch:** `claude/ai-finops-ep-01-s4d42x`  
**Scope:** `app/providers/` (10 framework files, 7 adapter stubs), `tests/test_ep06.py` (132 tests), all EP-06 documentation

---

## Executive Summary

EP-06 delivers a well-structured provider abstraction layer that correctly applies the Dependency Inversion Principle, Registry Pattern, Factory Pattern, and Anti-Corruption Layer patterns to isolate AI provider details from the platform's core business logic. The fundamentals are sound: the interface contract is clean, secrets are handled correctly, errors are normalised, and the test suite is comprehensive for an interface-only epic.

Seven issues were identified that carry enough risk to require resolution before EP-07 work begins. None of them are architectural failures; all are refinement gaps — most fixable in under 50 lines of code. The architecture itself does not need to be redesigned.

The implementation is approved to proceed to EP-07, subject to the seven prerequisites documented in Section 10 of this review.

---

## Architecture Score

**8.0 / 10**

| Dimension | Score | Notes |
|-----------|-------|-------|
| Interface design | 9/10 | Clean ABC, correct method signatures, good concrete defaults |
| Registry & Factory | 8/10 | Correct patterns; minor mismatch-detection gap |
| Configuration model | 8/10 | Typed hierarchy is strong; `provider_type: str` loses type safety |
| Secret handling | 9/10 | Solid: `SecretReference`, redacted repr, leak guard validator |
| Error normalization | 9/10 | Excellent hierarchy; `retryable` + `retry_after_seconds` pre-wired |
| Retry / health interfaces | 7/10 | ABCs defined; `HealthCheckInterface` orphaned from `AIProvider` |
| Adapters | 8/10 | Consistent pattern; vision `messages` type too narrow |
| Test quality | 8/10 | 132 tests; some coverage gaps noted |
| Documentation | 9/10 | Knowledge Transfer doc is thorough |
| Security | 8/10 | Good posture; `base_url` SSRF and `SecretStore` enum gaps remain |

---

## Strengths

### S-01 — Interface Contract Is the Right Shape

`AIProvider` defines exactly the right set of abstract methods for an AI provider integration layer:
- `provider_type` and `capabilities` as properties signal they are free (no I/O)
- All I/O-bound methods (`check_connection`, `list_models`, `complete`, `verify_auth`) are `async`
- Two concrete properties (`config`, `display_name`) eliminate boilerplate in every adapter
- No leakage of provider-specific concepts into the interface

This is the correct shape for the Dependency Inversion applied at a network boundary.

### S-02 — Credential Leak Guard Is Effective

The `ProviderConfig._no_plaintext_secrets` model validator runs at construction time and rejects any `extra` key containing `api_key`, `secret`, `password`, `token`, or `key` (case-insensitive). This means:

```python
ProviderConfig(provider_type="openai", display_name="X", extra={"openai_api_key": "sk-..."})
# → ValueError immediately
```

Combined with the EP-03.5 `validate_provider_configuration()` guard at the ORM layer, plaintext secrets face two independent rejection barriers.

### S-03 — `SecretReference.__repr__` Redacts Secret Keys

```python
>>> SecretReference(secret_key="sk-prod-abc123")
SecretReference(secret_store='env', secret_key=<redacted>)
```

Any structured log line that includes a config object will not expose the secret key name. This is the correct design — the key *name* in the environment is also sensitive metadata.

### S-04 — `retryable` on `ProviderError` Is the Right Abstraction

Attaching the retry hint to the exception itself means the retry policy does not need a lookup table. The service layer pattern becomes:

```python
except ProviderError as e:
    if e.retryable:
        await retry_policy.wait(attempt)
    else:
        raise
```

This works correctly for all six error subclasses without any `isinstance` checks.

### S-05 — `RateLimitError.retry_after_seconds` Is Pre-Wired

Provider APIs return the `Retry-After` header (sometimes). The field exists on `RateLimitError` now, so EP-07 adapter code can populate it and EP-07 retry logic can use it — without any interface change.

### S-06 — Module-Level `_CAPABILITIES` Constants Avoid Per-Instance Allocation

```python
_CAPABILITIES = ProviderCapabilities(supports_streaming=True, ...)

class OpenAIProvider(AIProvider):
    @property
    def capabilities(self) -> ProviderCapabilities:
        return _CAPABILITIES   # dictionary lookup, not object construction
```

Since `ProviderCapabilities` is `frozen=True`, sharing a single instance across all `OpenAIProvider` instances is safe and efficient. This is a small but correct optimisation.

### S-07 — `ModelMetadata` Is Pre-Wired for the Cost Engine

`input_cost_per_1k: float | None = None` and `output_cost_per_1k: float | None = None` are already in the model. When EP-08 introduces the cost engine, it reads these fields without any migration. `UsageData.cached_tokens` is similarly pre-wired for providers that discount cached prompt tokens (Anthropic prompt caching, OpenAI cached context).

### S-08 — Zero External SDK Dependencies in EP-06

The entire `app/providers/` package imports nothing beyond `pydantic`, `abc`, `dataclasses`, and `enum` — all stdlib or already present in the project. This means EP-06 tests run in 0.27 seconds with no network, no mocks, and no SDK version conflicts.

### S-09 — `AzureOpenAIConfig.azure_endpoint` Is Required

`azure_endpoint: str` has no default and no `= None`. Pydantic raises `ValidationError` at config construction time if it is missing. This is the correct design for a required field — the error surfaces at configuration time, not at the first API call.

### S-10 — `config_version` Enables Future Schema Migration

`ProviderConfig.config_version: int = 1` is a migration anchor. When EP-09 needs to restructure configuration, it can do `if config.config_version < 2: migrate(config)` rather than running a data migration over all stored JSONB configs.

### S-11 — `HealthCheckInterface` and `RetryPolicy` ABCs Are Placeholders Done Right

By defining ABCs now, EP-07 implementation inherits a clear, pre-approved interface. EP-07 engineers cannot accidentally design `check_connection()` with a different signature.

### S-12 — Test Suite Is Appropriately Focused

132 tests cover: all 7 error types (22 cases), all capabilities, all models/requests/responses, all config types (including the secret rejection validator), the registry API, the factory for all 7 providers, and every adapter stub's `provider_type`, `capabilities`, `check_connection`, `list_models`, `complete`, and `verify_auth`. The test depth is appropriate for an interface-only epic.

---

## Weaknesses

### W-01 — `HealthCheckInterface` Is Orphaned

**Severity: HIGH**

`app/providers/health.py` defines:

```python
class HealthCheckInterface(ABC):
    async def check_connection(self) -> ConnectionStatus: ...
    async def verify_auth(self) -> bool: ...
    async def check_capability(self, capability: str) -> bool: ...
    @property
    def is_healthy(self) -> bool: ...
```

`AIProvider` independently defines `check_connection()` and `verify_auth()` with the same signatures. However, `AIProvider` does **not** inherit from `HealthCheckInterface`. As a result:

- `HealthCheckInterface` is imported by nothing in the codebase
- `AIProvider.check_connection()` and `HealthCheckInterface.check_connection()` are parallel definitions that can drift apart
- `HealthCheckInterface.check_capability()` and `is_healthy` have **no implementation path** — no class implements `HealthCheckInterface`

This is a design inconsistency. `AIProvider` partially satisfies `HealthCheckInterface` by accident, not by contract.

**Recommended fix:** Have `AIProvider` inherit from `HealthCheckInterface`:

```python
class AIProvider(HealthCheckInterface, ABC):
    ...
```

This makes the health interface explicit, eliminates the orphaned file, and ensures `check_capability()` and `is_healthy` must be implemented (or declared abstract) in every adapter.

---

### W-02 — `ProviderConfig.provider_type` Is `str`, Not `ProviderType`

**Severity: HIGH**

```python
class ProviderConfig(BaseModel):
    provider_type: str   # ← accepts "invalid_value" with no error
```

`ProviderType` validation only happens in `ProviderFactory.create()`:

```python
provider_type = ProviderType(config.provider_type)   # may raise ValueError here
```

This means a misconfigured `ProviderConfig(provider_type="gpt4_turbo", display_name="X")` (a typo) passes all validation and is only rejected at the moment of factory creation — potentially much later in the request lifecycle.

**Recommended fix:** Validate at config construction time. Options:
1. Change `provider_type: str` to `provider_type: ProviderType` (strictest, best)
2. Add a `@field_validator("provider_type")` that calls `ProviderType(v)` and re-raises as `ValueError`

The typed subclasses (`OpenAIConfig`, etc.) lock `provider_type` to a string literal, which mitigates the risk for well-typed callers. The risk is highest for `ProviderConfig(provider_type=untrusted_string, ...)` calls in the service layer.

---

### W-03 — Factory Does Not Validate Provider Type Consistency

**Severity: HIGH**

`ProviderFactory.create()` looks up and instantiates the adapter class:

```python
def create(self, config: ProviderConfig) -> AIProvider:
    provider_type = ProviderType(config.provider_type)
    cls = self._registry.get(provider_type)
    return cls(config)
```

There is no check that `cls(config).provider_type == provider_type`. If the registry is misconfigured:

```python
registry.register(ProviderType.OPENAI, AnthropicProvider)
factory.create(OpenAIConfig(display_name="X"))
```

The factory silently returns an `AnthropicProvider` with `provider.provider_type == ProviderType.ANTHROPIC`, while `provider.config.provider_type == "openai"`. This mismatch would cause silent misattribution of costs and incorrect capability lookups.

**Recommended fix:** Add an assertion in `create()`:

```python
instance = cls(config)
assert instance.provider_type == provider_type, (
    f"Registry misconfiguration: registered {cls.__name__} for {provider_type!r} "
    f"but adapter reports provider_type={instance.provider_type!r}"
)
return instance
```

In production, replace the `assert` with an explicit `raise ValueError` (asserts are stripped with `-O`).

---

### W-04 — `base_url` Is Not Validated Against SSRF Patterns

**Severity: HIGH — Security**

`ProviderConfig.base_url: str | None` and `OllamaConfig.base_url: str = "http://localhost:11434"` accept any URL. A misconfigured or maliciously injected `base_url` value of `http://169.254.169.254/latest/meta-data/` would cause EP-07's HTTP client to make SSRF (Server-Side Request Forgery) requests to the AWS instance metadata service.

This is not exploitable in EP-06 (no HTTP calls). In EP-07, when adapters resolve `config.base_url` to construct HTTP clients, SSRF becomes a real attack surface.

**Recommended fix before EP-07:**

Add a `base_url` validator to `ProviderConfig`:

```python
@field_validator("base_url", mode="before")
@classmethod
def _validate_base_url(cls, v: str | None) -> str | None:
    if v is None:
        return v
    parsed = urlparse(v)
    allowed_schemes = {"https", "http"}
    if parsed.scheme not in allowed_schemes:
        raise ValueError(f"base_url must use http or https, got {parsed.scheme!r}")
    blocked_hosts = {"169.254.169.254", "metadata.google.internal", "fd00:ec2::254"}
    if parsed.hostname in blocked_hosts:
        raise ValueError(f"base_url resolves to a blocked host: {parsed.hostname!r}")
    return v
```

A production deployment should also enforce `https://` only (non-Ollama providers), rejecting `http://` for cloud endpoints.

---

### W-05 — `AIProvider` Has No `get_usage()` Method — Breaking Change Risk

**Severity: HIGH — Forward Compatibility**

Seven providers (`supports_usage_api=True` for all except Ollama) expose a dedicated usage/billing API endpoint — separate from the completion API. EP-08+ will need to pull historical usage data from these endpoints.

There is no `get_usage()` abstract method on `AIProvider`. This means:
1. EP-07 will likely add it when needed.
2. Adding an abstract method to `AIProvider` in EP-07 is a **breaking change** to the interface — all seven adapter stubs become invalid until they implement the new method.
3. This could be avoided by defining the method now (raises `NotImplementedError("EP-08")`) — the same pattern used for `complete()` and `verify_auth()`.

**Recommended fix:** Add to `AIProvider` now:

```python
@abstractmethod
async def get_usage(
    self,
    start_date: datetime,
    end_date: datetime,
) -> list[UsageData]:
    """Fetch historical usage from the provider's billing API. EP-08 implements this."""
    ...
```

Adapters that don't support it (`OllamaProvider`) implement:

```python
async def get_usage(self, start_date: datetime, end_date: datetime) -> list[UsageData]:
    raise NotImplementedError("Ollama does not expose a usage API")
```

This is the same stub pattern used for `complete()`.

---

### W-06 — `ProviderRequest.messages` Type Is Too Narrow for Vision

**Severity: MEDIUM — Forward Compatibility**

```python
class ProviderRequest(BaseModel):
    messages: list[dict[str, str]]   # values are str only
```

The OpenAI vision API requires:

```json
{
  "role": "user",
  "content": [
    {"type": "text", "text": "What is in this image?"},
    {"type": "image_url", "url": {"url": "data:image/png;base64,..."}}
  ]
}
```

Here, `content` is a `list`, not a `str`. The current type annotation `dict[str, str]` rejects this at Pydantic validation time, making `supports_vision=True` a broken promise.

**Recommended fix:**

```python
messages: list[dict[str, Any]]   # Any to accommodate vision content blocks
```

Or, define a `Message` union type that explicitly handles text and image content blocks — the cleaner long-term solution for EP-07.

---

### W-07 — `OllamaConfig._ollama_no_key_required` Validator Is Dead Code

**Severity: LOW**

```python
class OllamaConfig(ProviderConfig):
    ...
    @model_validator(mode="after")
    def _ollama_no_key_required(self) -> OllamaConfig:
        return self   # ← does nothing
```

This validator runs on every `OllamaConfig` construction with zero effect. It appears to be scaffolding for a validation that was never written. It is harmless but confusing.

**Recommended fix:** Remove the validator.

---

## Technical Debt

| ID | Item | Priority | When to Address |
|----|------|----------|----------------|
| TD-01 | `HealthCheckInterface` orphaned from `AIProvider` | HIGH | Before EP-07 |
| TD-02 | `ProviderConfig.provider_type: str` loses ProviderType safety | HIGH | Before EP-07 |
| TD-03 | Factory does not validate provider_type consistency | HIGH | Before EP-07 |
| TD-04 | `base_url` SSRF validation missing | HIGH | Before EP-07 (blocks EP-07 HTTP calls) |
| TD-05 | No `get_usage()` on `AIProvider` | HIGH | Before EP-07 or as first EP-07 task |
| TD-06 | `ProviderRequest.messages: list[dict[str, str]]` too narrow | MEDIUM | Before first vision adapter in EP-07 |
| TD-07 | `OllamaConfig._ollama_no_key_required` is dead code | LOW | Next cleanup pass |
| TD-08 | `SecretReference.secret_store` has no `SecretStoreType` enum | MEDIUM | Before EP-07 secret resolver |
| TD-09 | `ModelMetadata.provider_type: str` not `ProviderType` | LOW | EP-07 |
| TD-10 | `ConnectionStatus` allows `is_connected=True` + `UNHEALTHY` | LOW | EP-07 when real probes land |
| TD-11 | `ProviderRegistry` has no `__contains__` for `in` operator | LOW | EP-07 |
| TD-12 | `list_models()` returns hardcoded stubs; no live discovery | HIGH | EP-07 |
| TD-13 | `check_connection()` returns `UNKNOWN`; no real HTTP probe | HIGH | EP-07 |
| TD-14 | `RetryPolicy` and `CircuitBreaker` have no concrete implementation | HIGH | EP-07 |
| TD-15 | `ModelMetadata` cost fields are all `None` | MEDIUM | EP-08 |
| TD-16 | `ProviderRegistry` global singleton has no test-reset path | LOW | Test infrastructure |
| TD-17 | `ProviderResponse.raw_response: dict` lacks `[str, Any]` typing | LOW | Next cleanup pass |
| TD-18 | `public __all__` in `__init__.py` omits `models.py` exports | MEDIUM | EP-07 before first service layer use |

---

## Security Review

### Credential Handling: PASS

| Control | Present | Notes |
|---------|---------|-------|
| No plaintext secrets in `ProviderConfig` | ✓ | Model validator rejects at construction |
| No secrets in ORM `configuration` JSONB | ✓ | Established in EP-03; EP-06 inherits |
| `SecretReference.__repr__` redacts secret key | ✓ | Tested in `test_repr_redacts_key` |
| No external SDK imports (no SDK credential leaks) | ✓ | Zero external dependencies |
| Secrets not in test fixtures | ✓ | Tests use `SecretReference(secret_key="TEST_KEY")` |

### SSRF Risk: OPEN — Must Fix Before EP-07

As noted in W-04, `base_url` accepts any URL. This is a deferred risk that becomes real when EP-07 adds HTTP calls. A `@field_validator` for `base_url` must be added to `ProviderConfig` before EP-07's first network call is merged.

SSRF attack vector: an admin with `provider:write` permission sets `base_url` to `http://169.254.169.254/latest/meta-data/` and watches logs for the response.

### Secret Store Enum: OPEN — Minor

`SecretReference.secret_store: str` accepts arbitrary strings. EP-07's secret resolver will fail silently or with a cryptic error on unrecognised store names. A `SecretStoreType` StrEnum (`"env"`, `"vault"`, `"aws_secrets_manager"`) would reject invalid store names at config construction time.

### No Sensitive Data in Error Messages: PASS

Error messages in `ProviderError` subclasses use default messages (`"Rate limit exceeded"`, `"Authentication failed"`) and accept custom messages from adapters. No error message includes credential values.

### Dependency Supply Chain: PASS

Zero new runtime dependencies introduced in EP-06. Attack surface is unchanged from EP-05.

---

## Performance Review

### In-Process Performance: EXCELLENT

- All seven `_CAPABILITIES` objects are module-level constants (one allocation per module import, not per request)
- `ProviderCapabilities` uses `slots=True` — 20–30% faster attribute access than dict-backed instances
- `ProviderRegistry.get()` is a dict lookup — O(1)
- `ProviderFactory.create()` is O(1): one dict lookup + one constructor call
- `list_models()` returns `list(_MODELS)` — a shallow copy. The models themselves are immutable (frozen Pydantic), so the copy is safe and cheap

### Zero Latency Added to Request Path: CONFIRMED

EP-06 adds no I/O to any request path. All new code is in-process object construction. The provider framework will add latency only in EP-07 when actual API calls are made.

### Memory Profile: ACCEPTABLE

Each `ProviderConfig` instance (~7–10 fields) lives for the duration of a request. With `frozen=True` on `ProviderCapabilities` and `ModelMetadata`, no copies are made during capability checks or model lookups.

**Concern:** `ProviderResponse.raw_response: dict` stores the full provider API response. For large completions (e.g., 128K token context), this could be several hundred KB per request. EP-07 should consider whether `raw_response` should be truncated or omitted in production, stored only in debug mode.

---

## Scalability Review

### Horizontal Scaling: NO ISSUES

The provider framework contains no process-local mutable state that would prevent horizontal scaling:
- The `_default_registry` singleton is populated from compile-time constants (adapter classes). No shared mutable state between requests.
- `ProviderConfig` objects are constructed per-request from the `ProviderConnection` database row.
- All adapters are stateless between calls (EP-06 makes no calls at all; EP-07 adapters will be stateless HTTP clients).

### Adding New Providers: EXCELLENT

Registering a new provider requires:
1. Add `ProviderType` enum value — 1 line
2. Add config subclass — ~5 lines
3. Add adapter file — ~40 lines
4. Add registry line in `build_default_registry()` — 1 line

No existing file requires more than 1 line of change. This is the correct scalability target for a plugin architecture.

### Concurrency Under Load: ACCEPTABLE (with caveat)

The `get_registry()` singleton uses a double-checked locking pattern that works in CPython due to the GIL but is not safe in environments without the GIL (PyPy3, future free-threaded CPython). For production correctness:

```python
# Current (CPython-safe)
if _default_registry is None:
    _default_registry = ProviderFactory.build_default_registry()

# Better (GIL-independent)
import threading
_registry_lock = threading.Lock()

def get_registry() -> ProviderRegistry:
    global _default_registry
    if _default_registry is None:
        with _registry_lock:
            if _default_registry is None:
                _default_registry = ProviderFactory.build_default_registry()
    return _default_registry
```

This is a low-priority hardening item — CPython's GIL makes the current code safe in practice.

### Circuit Breaker: NOT YET IMPLEMENTED

For high-traffic production use, the circuit breaker pattern (defined in `retry.py`) is essential to prevent cascading failures when a provider goes down. Without it, all in-flight requests to a failed provider will queue up and time out, exhausting the FastAPI thread pool. This must be implemented in EP-07 before production traffic.

---

## Production Readiness Review

### EP-06 Itself: READY (it adds no I/O)

EP-06's code is production-ready for what it does: defining interfaces, validating configuration, and providing stubs. There is nothing to fail at runtime.

### Gate Criteria for EP-07 Production Use

The following must be true before EP-07 provider API calls go to production:

| Gate | Status | Required Action |
|------|--------|----------------|
| `base_url` SSRF validation | ❌ OPEN | Add `@field_validator` before EP-07 HTTP calls |
| Concrete `RetryPolicy` implementation | ❌ OPEN | EP-07 deliverable |
| Concrete `CircuitBreaker` implementation | ❌ OPEN | EP-07 deliverable (Redis-backed) |
| Provider API key resolution path | ❌ OPEN | EP-07: `SecretResolver` that reads from env / Vault |
| Structured logging on all `complete()` calls | ❌ OPEN | EP-07 deliverable |
| Prometheus metrics for provider calls | ❌ OPEN | EP-07 deliverable |
| `RateLimitError` with `retry_after_seconds` populated | ❌ OPEN | EP-07 per-adapter |
| Real `check_connection()` with latency measurement | ❌ OPEN | EP-07 deliverable |

### Observability Gaps in EP-06 (by design)

EP-06 has no observability because it makes no calls. These are intentional gaps to be filled in EP-07:
- No logging per provider call (nothing to log)
- No metrics counters (nothing to count)
- No distributed tracing spans (nothing to trace)
- No `ConnectionStatus.latency_ms` populated (not connected)

---

## Risk Register

| ID | Risk | Probability | Impact | Mitigation |
|----|------|-------------|--------|-----------|
| R-01 | EP-07 adds `get_usage()` to `AIProvider`, breaking all 7 stubs simultaneously | HIGH | MEDIUM | Add stub now (W-05) |
| R-02 | SSRF via misconfigured `base_url` after EP-07 HTTP calls land | MEDIUM | HIGH | Validate `base_url` in `ProviderConfig` (W-04) |
| R-03 | Provider type mismatch in registry causes wrong adapter to execute | LOW | HIGH | Add consistency check in factory (W-03) |
| R-04 | Vision request fails at Pydantic validation due to `dict[str, str]` type | HIGH | MEDIUM | Widen to `dict[str, Any]` before first vision request (W-06) |
| R-05 | `HealthCheckInterface` drifts from `AIProvider` contract | MEDIUM | LOW | Inherit `AIProvider` from `HealthCheckInterface` (W-01) |
| R-06 | Typo in `ProviderConfig.provider_type` surfaces only at factory call time | LOW | LOW | Validate as `ProviderType` at config construction (W-02) |
| R-07 | Circuit breaker absent in EP-07 causes cascading failures under provider outage | HIGH | HIGH | Mandatory EP-07 deliverable; block EP-07 merge without it |
| R-08 | `ProviderResponse.raw_response` stores multi-MB completions in memory | MEDIUM | MEDIUM | Add size cap or debug-only flag in EP-07 |
| R-09 | `SecretReference.secret_store` with invalid value fails at resolution time, not config time | LOW | LOW | Add `SecretStoreType` StrEnum |
| R-10 | `_default_registry` singleton pollutes test isolation if mutated | LOW | LOW | Add `reset_registry()` for test use |

---

## Recommendations Before EP-07

The following are ordered by risk. Items 1–5 are mandatory prerequisites. Items 6–7 are strongly recommended.

### Mandatory (7 items)

#### REC-01 — Make `AIProvider` inherit from `HealthCheckInterface`

```python
# interface.py
from app.providers.health import HealthCheckInterface

class AIProvider(HealthCheckInterface, ABC):
    ...
```

Remove the duplicate `check_connection()` and `verify_auth()` declarations from `AIProvider` (they are now inherited from `HealthCheckInterface`). Add `check_capability()` and `is_healthy` as abstract methods to `AIProvider`. Update all 7 adapter stubs to implement `check_capability()` and `is_healthy`.

**Effort:** ~30 minutes. Low risk.

---

#### REC-02 — Validate `ProviderConfig.provider_type` as a `ProviderType` value

```python
from pydantic import field_validator
from app.models.provider_connection import ProviderType

class ProviderConfig(BaseModel):
    provider_type: str

    @field_validator("provider_type", mode="before")
    @classmethod
    def _validate_provider_type(cls, v: str) -> str:
        ProviderType(v)   # raises ValueError if not a valid ProviderType
        return v
```

**Note:** Keep `provider_type` as `str` (not `ProviderType`) to avoid import cycles between `app.models` and `app.providers`. The validator enforces validity without changing the field type.

**Effort:** ~15 minutes. No risk.

---

#### REC-03 — Add provider type consistency check in `ProviderFactory.create()`

```python
def create(self, config: ProviderConfig) -> AIProvider:
    provider_type = ProviderType(config.provider_type)
    cls = self._registry.get(provider_type)
    instance = cls(config)
    if instance.provider_type != provider_type:
        raise ValueError(
            f"Registry misconfiguration: {cls.__name__} is registered under "
            f"{provider_type!r} but reports provider_type={instance.provider_type!r}"
        )
    return instance
```

**Effort:** ~10 minutes. No risk.

---

#### REC-04 — Add `base_url` SSRF validation to `ProviderConfig`

```python
from urllib.parse import urlparse

@field_validator("base_url", mode="before")
@classmethod
def _validate_base_url(cls, v: str | None) -> str | None:
    if v is None:
        return v
    parsed = urlparse(v)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"base_url scheme must be http or https, got {parsed.scheme!r}")
    _SSRF_BLOCKED = {"169.254.169.254", "metadata.google.internal"}
    if parsed.hostname in _SSRF_BLOCKED:
        raise ValueError(f"base_url points to a blocked metadata host: {parsed.hostname!r}")
    return v
```

This must be in place before any EP-07 HTTP client constructs a URL from `config.base_url`.

**Effort:** ~20 minutes. No risk.

---

#### REC-05 — Add `get_usage()` abstract method to `AIProvider`

```python
# interface.py
from datetime import datetime

@abstractmethod
async def get_usage(
    self,
    start_date: datetime,
    end_date: datetime,
) -> list[UsageData]:
    """Fetch historical usage from the provider's billing API. EP-08 implements."""
    ...
```

All 7 adapters implement the stub:

```python
async def get_usage(self, start_date: datetime, end_date: datetime) -> list[UsageData]:
    raise NotImplementedError("<Provider> usage fetching is implemented in EP-08")
```

Ollama's stub message: `"Ollama does not expose a usage API (self-hosted)"`.

**Effort:** ~30 minutes. No risk.

---

#### REC-06 — Widen `ProviderRequest.messages` type

```python
from typing import Any

class ProviderRequest(BaseModel):
    messages: list[dict[str, Any]]   # was list[dict[str, str]]
```

This unblocks vision requests without requiring a full `Message` model (EP-07 can define proper typed message models as part of adapter implementation).

**Effort:** 1 line. No risk.

---

#### REC-07 — Remove `OllamaConfig._ollama_no_key_required` dead code

```python
# Remove this from OllamaConfig:
@model_validator(mode="after")
def _ollama_no_key_required(self) -> OllamaConfig:
    return self
```

**Effort:** 3 lines removed. No risk.

---

### Strongly Recommended (Before EP-07 Merge to Main)

**REC-08 — Add `SecretStoreType` StrEnum**

```python
class SecretStoreType(enum.StrEnum):
    ENV = "env"
    VAULT = "vault"
    AWS_SECRETS_MANAGER = "aws_secrets_manager"

class SecretReference(BaseModel):
    secret_store: SecretStoreType = SecretStoreType.ENV
    secret_key: str
```

This catches invalid `secret_store` values at config construction time instead of at secret resolution time.

**REC-09 — Export `models.py` types from `__init__.py`**

`ModelMetadata`, `ProviderRequest`, `ProviderResponse`, `UsageData`, `ConnectionStatus`, and `HealthStatus` should be in `__all__`. Service layer code will need these types and should import from `app.providers`, not `app.providers.models`.

---

## Final Decision

### APPROVED WITH MINOR CHANGES

---

EP-06 is **approved** to move to EP-07, **conditional on** the seven mandatory items in Section 10 (REC-01 through REC-07) being completed before EP-07's first network-calling commit is merged into the branch.

These items can be delivered as a short EP-06.1 cleanup task (estimated effort: 2–3 hours) at the start of the EP-07 sprint, or as the first task within EP-07 itself before any adapter implementation begins.

**Why approved:** The fundamental design is correct. The interface contract is the right shape. Secret handling is solid. Error normalisation is the right approach. The Registry and Factory patterns are correctly applied. The test suite covers what is testable at this stage. The architecture will not need to be redesigned — only refined.

**Why not "Approved" without qualification:** Five of the seven mandatory items will cause real bugs or security vulnerabilities in EP-07 if not fixed before the first HTTP call lands:
- R-02 (SSRF) is a security vulnerability the moment EP-07 uses `config.base_url`
- R-01 (missing `get_usage`) will break all 7 adapters simultaneously when added in EP-08
- R-04 (messages type) will make the vision feature non-functional from day one
- R-03 (factory consistency check) eliminates a class of silent misconfiguration
- W-01 (orphaned HealthCheckInterface) creates a contract drift risk

**Why not "Major Changes":** None of the issues require redesigning the layering, the patterns, or the interface. Every fix is additive (new validators, new abstract method) or corrective (type fix, dead code removal). The architecture is fundamentally sound.

---

### EP-07 Prerequisites Checklist

Before any EP-07 code implementing real API calls is committed, confirm:

- [ ] `AIProvider` inherits from `HealthCheckInterface` (REC-01)
- [ ] `ProviderConfig.provider_type` validated as known `ProviderType` (REC-02)
- [ ] `ProviderFactory.create()` validates provider type consistency (REC-03)
- [ ] `base_url` SSRF validation in `ProviderConfig` (REC-04)
- [ ] `get_usage()` abstract method on `AIProvider`, stubs in all 7 adapters (REC-05)
- [ ] `ProviderRequest.messages` widened to `list[dict[str, Any]]` (REC-06)
- [ ] `OllamaConfig._ollama_no_key_required` validator removed (REC-07)
- [ ] Circuit breaker implementation plan agreed before first adapter goes live

---

*Reviewed against: SDD §3, §4.4, §4.5, §4.15 — EP-03.5 hardening standards — OWASP API Security Top 10 (SSRF, Sensitive Data Exposure) — EP-05 auth patterns*
