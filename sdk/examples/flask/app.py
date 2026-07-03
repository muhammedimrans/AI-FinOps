"""
Minimal Flask app instrumented with COSTORAH — run with:

    pip install costorah flask openai
    export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
    export OPENAI_API_KEY=sk-...          # only needed for /chat
    flask --app app run

See README.md in this directory for the full walkthrough and expected
output.
"""

from flask import Flask, jsonify, request

from costorah.instrumentation import OpenAIInstrumentor
from costorah.integrations.flask import CostorahExtension

# Auto-captures every openai.* call made anywhere in the process after
# this point — no code changes needed at the call site.
OpenAIInstrumentor().instrument()

app = Flask(__name__)

# Everything below this line is what a real app adds: one line.
CostorahExtension(app)


@app.get("/")
def root() -> dict:
    return {"status": "ok"}


@app.post("/chat")
def chat() -> dict:
    """Calls OpenAI's chat completions API. The OpenAIInstrumentor
    installed above automatically captures the resulting token usage
    and cost and submits it to COSTORAH — this view contains no
    COSTORAH-specific code at all."""
    from openai import OpenAI

    prompt = request.args.get("prompt", "Say hi")
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return jsonify({"reply": response.choices[0].message.content or ""})
