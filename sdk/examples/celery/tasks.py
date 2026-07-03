"""
Minimal Celery app instrumented with COSTORAH — run with:

    pip install costorah celery openai
    export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
    export OPENAI_API_KEY=sk-...          # only needed for summarize
    celery -A tasks worker --loglevel=info

See README.md in this directory for the full walkthrough and expected
output.
"""

from celery import Celery

from costorah.instrumentation import OpenAIInstrumentor
from costorah.integrations.celery import CostorahCelery

app = Celery("costorah_example", broker="memory://", backend="cache+memory://")
app.conf.task_always_eager = True  # so `python tasks.py` works with no real broker

# Auto-captures every openai.* call made anywhere in the process after
# this point — no code changes needed at the call site.
OpenAIInstrumentor().instrument()

# Everything below this line is what a real app adds: one line. Every
# task's execution is now bracketed in ambient request context, so any
# usage event captured inside a task is automatically tagged with that
# task's ID, name, queue, and worker.
CostorahCelery(app)


@app.task(name="tasks.summarize")
def summarize(text: str) -> str:
    """The OpenAIInstrumentor installed above automatically captures the
    resulting token usage and cost and submits it to COSTORAH — this
    task contains no COSTORAH-specific code at all."""
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": f"Summarize in one sentence: {text}"}],
    )
    return response.choices[0].message.content or ""


if __name__ == "__main__":
    result = summarize.delay("COSTORAH is an AI usage/cost telemetry platform.")
    print(f"task id: {result.id}")
    print(f"result: {result.get()}")
