# LangChain (Python)

```python
from langchain_openai import ChatOpenAI
from costorah.instrumentation.langchain import LangChainInstrumentor

LangChainInstrumentor().instrument()

model = ChatOpenAI(model="gpt-4o-mini")
model.invoke("Hello")   # usage, cost, latency, and trace context are
                          # captured automatically — no manual tracking
                          # calls
```

## How it works

`LangChainInstrumentor` hooks into `langchain_core.tracers.context.
register_configure_hook` — the same `ContextVar`-based extension point
LangSmith's own `LANGCHAIN_TRACING_V2` auto-tracer uses internally
(verified by reading the installed `langchain-core` source, not assumed).
`register_configure_hook(context_var, inheritable=True)` registers a
`ContextVar` that `CallbackManager._configure()` reads on every run,
auto-injecting whatever handler `LangChainInstrumentor` currently holds
there — no `callbacks=[...]` argument needed at any call site.

## What gets captured

For every real, completed LLM call (`on_llm_end`/`on_chat_model_end`):

- `provider`, `model`, `input_tokens`, `output_tokens`, `total_tokens`,
  `reasoning_tokens` and `cached_tokens` when the model reports them
  (LangChain's standardized `usage_metadata` shape), `cost`,
  `finish_reason`, `latency_ms`
- `trace_id`/`span_id`/`parent_span_id` — a new trace per top-level
  invocation, inherited by nested chain/tool/LLM runs
- `chain_name`/`tool_name` — read directly from the enclosing chain/tool
  run's own tracked name, not via ambient request context

Chain start/end and tool start/end (`on_chain_start`, `on_tool_start`, ...)
are counted (`events_captured_total`) but never independently submit a
usage event — see `AI_FRAMEWORK_INTEGRATIONS.md`'s shared-constraint
section for why.

## Provider resolution

The provider is inferred from the LangChain integration package's module
path (e.g. `langchain_openai.chat_models.base` → `openai`), falling back
to the model name's prefix (`gpt-4o-mini` → `openai`) when the module path
doesn't resolve. If neither resolves to a member of
`costorah.types.SUPPORTED_PROVIDERS`, **no usage event is submitted** —
this instrumentor never invents a provider.

## Combining with a provider instrumentor

Don't also `instrument()` `OpenAIInstrumentor`/`AnthropicInstrumentor`/etc.
for the same LLM calls LangChain already routes through its own chat model
classes — the same underlying HTTP call would be captured twice.

## Never captured

Prompt/message content, response content, and tool input/output are never
read by `on_llm_start`/`on_chat_model_start`/`on_llm_end` handlers here —
only name/ID/token-count/timing/finish-reason fields.

## Verified against

Real `langchain-core`, `langchain-openai` packages, with a `ChatOpenAI`
instance whose `http_client` is a mocked `httpx.MockTransport` — the actual
network boundary, not an internal SDK method (see the module docstring for
why: `langchain-openai` routes through `self.client.with_raw_response.
create(...)`, not the plain `Completions.create` the OpenAI provider
instrumentor patches).
