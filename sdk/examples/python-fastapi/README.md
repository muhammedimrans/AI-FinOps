# FastAPI + COSTORAH example

A minimal FastAPI app demonstrating the full integration named in
EP-18.4's Success Criteria: automatic OpenAI instrumentation plus the
`CostorahMiddleware` for per-request context, wired with no code beyond
what's in `main.py`.

## Setup

```bash
cd sdk/examples/python-fastapi
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in COSTORAH_API_KEY (and OPENAI_API_KEY for /chat)
export $(cat .env | xargs)
```

## Run

```bash
uvicorn main:app --reload
```

## Try it

```bash
curl http://127.0.0.1:8000/
# {"status":"ok","docs":"/docs"}

curl -X POST "http://127.0.0.1:8000/chat?prompt=Say+hi+in+five+words"
# {"reply":"Hello there, how are you?"}
```

## What to expect

- Every response includes an `X-Costorah-Request-Id` header — generated
  by `CostorahMiddleware` (or echoed back if you sent your own
  `X-Request-Id`).
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID via ambient request
  context (`metadata["request_context"]`) — no manual `client.track()`
  call anywhere in `main.py`.
- With no `COSTORAH_API_KEY` set, the app still runs: the middleware
  logs one warning and instrumentation still executes locally, it just
  has nothing to submit to.

## Verify end-to-end

```bash
costorah doctor
```

should report Connectivity and Authentication as passing once
`COSTORAH_API_KEY` is set to a real key.
