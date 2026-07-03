# Flask + COSTORAH example

A minimal Flask app demonstrating the integration named in EP-18.5's
Success Criteria: `CostorahExtension(app)` plus automatic OpenAI
instrumentation, wired with no code beyond what's in `app.py`.

## Setup

```bash
cd sdk/examples/flask
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in COSTORAH_API_KEY (and OPENAI_API_KEY for /chat)
export $(cat .env | xargs)
```

## Run

```bash
flask --app app run
```

## Try it

```bash
curl http://127.0.0.1:5000/
# {"status":"ok"}

curl -X POST "http://127.0.0.1:5000/chat?prompt=Say+hi+in+five+words"
# {"reply":"Hello there, how are you?"}
```

## What to expect

- Every response includes an `X-Costorah-Request-Id` header — generated
  by `CostorahExtension` (or echoed back if you sent your own
  `X-Request-Id`).
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID via ambient request
  context — no manual `client.track()` call anywhere in `app.py`.
- With no `COSTORAH_API_KEY` set, the app still runs: the extension logs
  one warning and instrumentation still executes locally, it just has
  nothing to submit to.

## Verify end-to-end

```bash
costorah doctor
```
