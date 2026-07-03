# Celery + COSTORAH example

A minimal Celery app demonstrating the integration named in EP-18.5's
Success Criteria: `CostorahCelery(app)` plus automatic OpenAI
instrumentation, wired with no code beyond what's in `tasks.py`.

This example uses `task_always_eager = True` and an in-memory broker
(`memory://`) so it's runnable standalone with `python tasks.py` — no
Redis/RabbitMQ required. A real deployment would point `broker=`/
`backend=` at an actual broker and run `celery -A tasks worker` instead.

## Setup

```bash
cd sdk/examples/celery
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in COSTORAH_API_KEY (and OPENAI_API_KEY)
export $(cat .env | xargs)
```

## Run

```bash
python tasks.py
```

## Expected output

```
task id: 3f9c1e2a-...
result: COSTORAH gives teams visibility into their AI provider spend.
```

## What to expect

- The `summarize` task triggers `OpenAIInstrumentor`, which captures the
  response's token usage and cost and submits it to COSTORAH
  automatically — tagged with that task's ID, name (`tasks.summarize`),
  queue, and worker via ambient request context. No manual
  `client.track()` call anywhere in `tasks.py`.
- With no `COSTORAH_API_KEY` set, the app still runs: `CostorahCelery`
  logs one warning and instrumentation still executes locally, it just
  has nothing to submit to.

## Verify end-to-end

```bash
costorah doctor
```
