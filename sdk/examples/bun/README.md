# Bun + COSTORAH example

A minimal `Bun.serve()` HTTP server demonstrating `@costorah/sdk`
running natively under Bun — see `sdk/docs/BUN.md` for how this was
verified. Uses `costorahHandler` (a generic `Request -> Response`
wrapper, despite living at `@costorah/sdk/next` — no Next.js dependency)
since `Bun.serve()`'s fetch handler is fetch-API-shaped.

## Setup

```bash
cd sdk/examples/bun
bun install
cp .env.example .env   # fill in COSTORAH_API_KEY (and OPENAI_API_KEY for /chat)
export $(cat .env | xargs)
```

## Run

```bash
bun run start
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
  automatically — no manual `client.track()` call anywhere in
  `server.ts`.
