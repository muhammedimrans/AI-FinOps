# AI Framework Integrations (EP-18.7)

COSTORAH extends beyond direct provider SDK instrumentation (EP-18.2) into AI
application frameworks — orchestration libraries, agent frameworks, and the
Model Context Protocol. Where a provider instrumentor captures "a call was
made to OpenAI," an AI framework instrumentor captures "this chain/agent/tool
made that call," adding trace context (`trace_id`/`span_id`/`parent_span_id`)
and framework-specific metadata (chain name, agent role, tool name, finish
reason) around the same underlying provider usage event.

## What's built, and to what depth

| Framework | Language | Module | Status |
|---|---|---|---|
| LangChain | Python | `costorah.instrumentation.langchain` | Production-ready, tested against real `langchain-openai` |
| CrewAI | Python | `costorah.instrumentation.crewai` | Production-ready, tested against real `crewai` |
| MCP (client + server) | Python | `costorah.instrumentation.mcp` | Production-ready, tested against real `mcp` SDK |
| LangChain JS | JavaScript | `LangChainInstrumentor` (`@costorah/sdk`) | Production-ready, tested against real `@langchain/openai` |
| Vercel AI SDK | JavaScript | `VercelAIInstrumentor` (`@costorah/sdk`) | Production-ready, tested against real `@ai-sdk/openai` + `ai` |

Every one of these was verified against the real, installed target package —
not mocked-only — including two genuine execution-model bugs found and fixed
during that verification (see each framework's own doc for details):

- **CrewAI** dispatches its event bus through a thread pool with a fresh
  `contextvars.copy_context()` per event, which broke a naive push/pop
  ambient-context design; fixed by reading `task_name`/`agent_role` directly
  off each `LLMCallCompletedEvent`'s own fields instead.
- **LangChain JS** dispatches callback handlers through a background
  `p-queue` by default and its own `setContextVariable` is itself built on
  the same `AsyncLocalStorage.enterWith` primitive this SDK initially used
  for ambient context — both had to be worked around; see `LANGCHAIN_JS.md`.

## What's deferred

The EP-18.7 ticket named a much larger surface than one session can build to
real depth. The following are **not implemented** — no stub files, no
placeholder classes:

**Python:** LlamaIndex, AutoGen, Semantic Kernel, Haystack, DSPy, OpenAI
Agents SDK.

**JavaScript:** Mastra, OpenAI Agents SDK (JS), a dedicated MCP client/server
instrumentor (Python's MCP instrumentor is the only MCP coverage), and the
broader "AI SDK Core" primitives beyond `generateText`/`streamText` (e.g.
`generateObject`/`streamObject`/`embed` are not separately instrumented,
though `VercelAIInstrumentor`'s middleware would apply to any AI SDK function
that accepts a wrapped `LanguageModelV2`).

**Cross-cutting, regardless of framework:** dedicated vector-database
instrumentors (Pinecone/Weaviate/Qdrant/Milvus/Chroma/pgvector/Redis
Vector), a dedicated embeddings-call instrumentor, RAG/retrieval-specific
capture beyond what a LangChain retriever span already produces via
`chain_name`/`tool_name` enrichment, and any OpenTelemetry trace/span
exporter (explicitly out of scope per the ticket).

If your framework isn't listed above, COSTORAH doesn't currently capture its
LLM calls automatically — instrument the underlying provider SDK directly via
EP-18.2's provider instrumentors, or call `client.track()`/`client.trackAsync()`
manually.

## The shared architectural constraint: why not everything submits a usage event

COSTORAH's ingestion endpoint (`POST /v1/ingest/usage`, EP-16) only accepts
LLM usage records — provider, model, token counts, cost. There's no
trace/span ingestion endpoint (adding one is a backend change out of scope
for this ticket). Every AI framework instrumentor in this package follows
the same rule as a result:

- **A real, completed LLM call** (with a provider resolvable to a member of
  the closed `SUPPORTED_PROVIDERS` enum) submits a genuine usage event
  through the existing reliability pipeline (EP-18.3's queue/batching/retry),
  enriched with `trace_id`/`span_id`/`parent_span_id` and framework metadata.
- **Everything else** — chain start/end, tool start/end, agent lifecycle,
  crew kickoff, MCP tool/resource/prompt calls — is either (a) used to
  enrich a *nested* LLM call's metadata (chain name, tool name, task name,
  agent role — read directly off already-tracked run info, never via a
  provider-agnostic fake usage record), or (b) counted and logged locally
  only (`events_captured_total`, debug-level structured logs), never
  submitted as a usage event. No framework instrumentor ever invents a
  provider (e.g. `provider: "langchain"`) or a zero-cost record to force
  non-LLM activity into the usage schema.

## Privacy

See `AI_PRIVACY.md` for the full accounting. In short: prompt text, response
text, tool arguments/results, retrieved documents, and MCP resource/prompt
contents are never read, logged, or transmitted by any instrumentor in this
package — only metadata (names, IDs, token counts, timing, cost, finish
reason).

## Configuration

Python:

```python
from costorah.instrumentation.langchain import LangChainInstrumentor
from costorah.instrumentation.crewai import CrewAIInstrumentor
from costorah.instrumentation.mcp import MCPInstrumentor

LangChainInstrumentor().instrument()
CrewAIInstrumentor().instrument()
MCPInstrumentor().instrument()
```

JavaScript:

```ts
import { LangChainInstrumentor, VercelAIInstrumentor } from "@costorah/sdk";

const lc = new LangChainInstrumentor();
await lc.instrument();

const vercel = new VercelAIInstrumentor();
vercel.instrument();
const model = vercel.wrapModel(openai("gpt-4o-mini"));
```

Each instrumentor accepts an explicit `client`/`Costorah` instance (falls
back to the env-var-configured default client from EP-18.1/EP-18.4 when
omitted) and honestly documents combining with a provider instrumentor for
the same underlying calls as a double-counting hazard — don't instrument
both `LangChainInstrumentor` and `OpenAIInstrumentor` for LLM calls that
LangChain itself routes.

## Performance

See `PERFORMANCE.md`'s AI framework section. All five instrumentors reuse
the existing background worker, batching, and retry engine from EP-18.3 —
none open a new network connection or perform blocking I/O on the
instrumented call path.
