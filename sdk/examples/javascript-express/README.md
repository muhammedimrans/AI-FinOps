# Express + COSTORAH example

A minimal Express app demonstrating the integration named in EP-18.4's
Success Criteria: `import { costorahMiddleware } from "@costorah/sdk/express"`
plus automatic OpenAI instrumentation, wired with no code beyond what's
in `server.mjs`.

## Setup

```bash
cd sdk/examples/javascript-express
npm install
cp .env.example .env   # fill in COSTORAH_API_KEY (and OPENAI_API_KEY for /chat)
export $(cat .env | xargs)
```

## Run

```bash
npm start
```

## Try it

```bash
curl http://127.0.0.1:3000/
# {"status":"ok"}

curl -X POST http://127.0.0.1:3000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hi in five words"}'
# {"reply":"Hello there, how are you?"}
```

## What to expect

- Every response includes an `X-Costorah-Request-Id` header — generated
  by `costorahMiddleware()` (or echoed back if you sent your own
  `X-Request-Id`).
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID via ambient request
  context (`AsyncLocalStorage`, `metadata.requestContext`) — no manual
  `client.track()` call anywhere in `server.mjs`.
- With no `COSTORAH_API_KEY` set, the app still runs: the middleware
  logs one warning and instrumentation still executes locally, it just
  has nothing to submit to.
