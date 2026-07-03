"""
Minimal FastAPI app instrumented with COSTORAH — run with:

    pip install costorah fastapi uvicorn openai
    export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
    export OPENAI_API_KEY=sk-...          # only needed for /chat
    uvicorn main:app --reload

See README.md in this directory for the full walkthrough and expected
output.
"""

from fastapi import FastAPI

from costorah.instrumentation import OpenAIInstrumentor
from costorah.integrations.fastapi import CostorahMiddleware

# Auto-captures every openai.* call made anywhere in the process after
# this point — no code changes needed at the call site.
OpenAIInstrumentor().instrument()

app = FastAPI(title="COSTORAH FastAPI example")

# Everything below this line is what a real app adds: one middleware
# line. It auto-initializes a Costorah client from COSTORAH_API_KEY,
# wires it as the default client the instrumentor above submits
# through, and attaches request context (request ID, path, method) to
# every usage event captured during each request.
app.add_middleware(CostorahMiddleware)


@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "docs": "/docs"}


@app.post("/chat")
def chat(prompt: str) -> dict[str, str]:
    """Calls OpenAI's chat completions API. The OpenAIInstrumentor
    installed above automatically captures the resulting token usage
    and cost and submits it to COSTORAH — this handler contains no
    COSTORAH-specific code at all."""
    from openai import OpenAI

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return {"reply": response.choices[0].message.content or ""}
