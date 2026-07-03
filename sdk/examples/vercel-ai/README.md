# Vercel AI SDK + COSTORAH example

A minimal script demonstrating `VercelAIInstrumentor` capturing usage from
a real `generateText()` call, via `wrapModel()` — no manual tracking calls.

## Setup

```bash
cd sdk/examples/vercel-ai
npm install
export COSTORAH_API_KEY=costorah_live_...   # optional — see below
export OPENAI_API_KEY=sk-...
```

## Run

```bash
npm start
```

## Expected telemetry

One usage event: `provider=openai`, `model=gpt-4o-mini`, real
`input_tokens`/`output_tokens`/`cost`, plus
`metadata.framework=vercel-ai-sdk` and `metadata.finishReason`.

## Without `COSTORAH_API_KEY`

The script still runs — `VercelAIInstrumentor` still captures the event
locally (`instrumentor.eventsCaptured` after the call), it just has
nowhere to submit it.

## Why `wrapModel()` is needed (unlike the provider-instrumentor examples)

The Vercel AI SDK has no global interception point equivalent to what
`OpenAIInstrumentor` patches — every `openai("gpt-4o-mini")` call returns
an independent object. `wrapModel()` is a one-time setup step at
model-creation, not a manual tracking call at every request. See
`sdk/docs/VERCEL_AI.md`.
