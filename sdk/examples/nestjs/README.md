# NestJS + COSTORAH example

A minimal NestJS app demonstrating the integration named in EP-18.6's
Success Criteria: `CostorahModule.forRoot({ apiKey })` plus automatic
OpenAI instrumentation, wired with no code beyond what's in
`src/app.module.ts`.

## Setup

```bash
cd sdk/examples/nestjs
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

- Every response includes an `X-Costorah-Request-Id` header — attached
  by `CostorahInterceptor`, which `CostorahModule.forRoot()` registers
  automatically as a global interceptor.
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID — no manual
  `client.track()` call anywhere in this example.
- With no `COSTORAH_API_KEY` set, the app still runs: the module logs
  one warning and instrumentation still executes locally.

See `sdk/docs/NESTJS.md` for the interceptor-vs-middleware choice, async
configuration (`forRootAsync`), and the `@InjectCostorah()` decorator.
