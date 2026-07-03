# Django + COSTORAH example

A minimal Django app demonstrating the integration named in EP-18.5's
Success Criteria: `"costorah.integrations.django.CostorahMiddleware"` in
`MIDDLEWARE`, plus automatic OpenAI instrumentation and the
`costorah_doctor` management command.

## Setup

```bash
cd sdk/examples/django
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in COSTORAH_API_KEY (and OPENAI_API_KEY for /chat)
export $(cat .env | xargs)
python manage.py migrate
```

## Run

```bash
python manage.py runserver
```

## Try it

```bash
curl http://127.0.0.1:8000/
# {"status":"ok"}

curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hi in five words"}'
# {"reply":"Hello there, how are you?"}
```

## Verify end-to-end

```bash
python manage.py costorah_doctor
```

runs the same checks as the shell's `costorah doctor`, reading
`COSTORAH_API_KEY`/`COSTORAH_ENDPOINT` from `myproject/settings.py`
(which itself reads them from the environment — see `.env.example`).

## What to expect

- Every response includes an `X-Costorah-Request-Id` header.
- The `/chat` call triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically, tagged with that same request ID via ambient request
  context — no manual `client.track()` call anywhere in this example.
- With no `COSTORAH_API_KEY` set, the app still runs: the middleware
  logs one warning and instrumentation still executes locally, it just
  has nothing to submit to.
