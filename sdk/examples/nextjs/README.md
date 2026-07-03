# Next.js + COSTORAH example

A minimal App Router app demonstrating the integration named in
EP-18.6's Success Criteria: `export const POST = costorahHandler(...)`,
plus an Edge Middleware using the same wrapper, and automatic OpenAI
instrumentation.

## Setup

```bash
cd sdk/examples/nextjs
npm install
cp .env.example .env   # fill in COSTORAH_API_KEY and OPENAI_API_KEY
export $(cat .env | xargs)
```

## Run

```bash
npm run dev
```

## Try it

```bash
curl -X POST http://127.0.0.1:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hi in five words"}'
# {"reply":"Hello there, how are you?"}
```

## What to expect

- Every response from `/api/chat` and every request passing through
  `middleware.ts` includes an `X-Costorah-Request-Id` header.
- The `/api/chat` route triggers `OpenAIInstrumentor`, which captures
  the response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID — no manual
  `client.track()` call anywhere in `app/api/chat/route.ts`.
- `middleware.ts` demonstrates `costorahHandler` used for Edge
  Middleware — the exact same wrapper as the route handler, since both
  are `Request -> Response` functions.

See `sdk/docs/NEXTJS.md` for Pages Router (`costorahApiRoute`) and why
Server Actions aren't automatically wrapped.
