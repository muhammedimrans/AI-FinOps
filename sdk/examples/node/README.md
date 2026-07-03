# Generic Node.js + COSTORAH example

A minimal standalone `node:http` server — no framework — demonstrating
`costorahNodeMiddleware` from `@costorah/sdk/node` plus automatic OpenAI
instrumentation.

## Setup

```bash
cd sdk/examples/node
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

curl -X POST "http://127.0.0.1:3000/chat?prompt=Say+hi+in+five+words"
# {"reply":"Hello there, how are you?"}
```

## What to expect

- Every response includes an `X-Costorah-Request-Id` header.
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID — no manual
  `client.track()` call anywhere in `server.mjs`.
- With no `COSTORAH_API_KEY` set, the app still runs: the middleware
  logs one warning and instrumentation still executes locally.
