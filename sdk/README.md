# COSTORAH SDKs

Official client SDKs for reporting AI usage/cost telemetry to COSTORAH — a
few lines of code to authenticate (EP-15) and push usage into the
Monitoring API (EP-16), with automatic provider normalization, batching,
retry, and offline queueing (phased — see `docs/`).

## Status

| Language | Status | Package |
|---|---|---|
| Python | **Available (EP-18.1: core)** | `pip install costorah` |
| JavaScript / TypeScript | **Available (EP-18.1: core)** | `npm install @costorah/sdk` |
| Go | Planned | — |
| Java | Planned | — |
| .NET | Planned | — |
| Rust | Planned | — |

`sdk/node/` is a legacy placeholder superseded by `sdk/javascript/` — see
its README.

## Structure

```
sdk/
    python/       # PyPI package "costorah"
    javascript/   # npm package "@costorah/sdk"
    shared/       # cross-language wire contract & design docs
    examples/     # runnable integration examples, one dir per framework
    docs/         # SDK-ecosystem-wide documentation
```

Each language SDK independently implements the same public API shape and
the same wire contract (`shared/API_CONTRACT.md`) — this is what lets a Go,
Java, C#, or Rust SDK be added later without an existing consumer's code or
mental model changing.

## Quick start

**Python**
```python
from costorah import Costorah

client = Costorah(api_key="costorah_live_xxxxxxxxx")
client.track(
    provider="openai",
    model="gpt-4.1",
    input_tokens=500,
    output_tokens=220,
    cost=0.041,
    latency_ms=621,
)
```

**JavaScript / TypeScript**
```ts
import { Costorah } from "@costorah/sdk";

const client = new Costorah({ apiKey: process.env.COSTORAH_API_KEY! });
await client.track({
  provider: "anthropic",
  model: "claude-sonnet-4",
  inputTokens: 200,
  outputTokens: 80,
  cost: 0.012,
  latencyMs: 410,
});
```

See `docs/QUICK_START.md` for the full walkthrough, `python/README.md` /
`javascript/README.md` for language-specific docs, and `docs/ROADMAP.md`
for what's implemented in this phase (EP-18.1: SDK Core) versus planned in
EP-18.2 (automatic instrumentation), EP-18.3 (reliability: batching/queue/
retry/offline), and EP-18.4 (framework integrations, full docs, CI/CD).
