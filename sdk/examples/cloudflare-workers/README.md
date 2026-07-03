# Cloudflare Workers + COSTORAH example

A minimal Worker demonstrating the integration named in EP-18.6's
Success Criteria: `export default costorahWorker(handler)` plus
automatic OpenAI instrumentation.

## Setup

```bash
cd sdk/examples/cloudflare-workers
npm install
wrangler secret put COSTORAH_API_KEY
wrangler secret put OPENAI_API_KEY   # only needed for /chat
```

## Run locally

```bash
npm run dev
```

## Try it

```bash
curl http://127.0.0.1:8787/
# {"status":"ok"}

curl -X POST "http://127.0.0.1:8787/chat?prompt=Say+hi+in+five+words"
# {"reply":"Hello there, how are you?"}
```

## Deploy

```bash
npm run deploy
```

## What to expect

- Every response includes an `X-Costorah-Request-Id` header.
- `costorahWorker` reads `COSTORAH_API_KEY` from the Worker's `env`
  bindings (set via `wrangler secret put`), **not** `process.env` — see
  `sdk/docs/CLOUDFLARE_WORKERS.md` for why.
- `compatibility_flags = ["nodejs_compat"]` in `wrangler.toml` is
  required — it's what makes `AsyncLocalStorage` (the ambient
  request-context mechanism every integration in this SDK shares)
  available in the Workers runtime.
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically — no manual `client.track()` call anywhere in
  `src/index.ts`.
