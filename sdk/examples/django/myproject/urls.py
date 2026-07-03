"""
Minimal Django app instrumented with COSTORAH — run with:

    pip install costorah django openai
    export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
    export OPENAI_API_KEY=sk-...          # only needed for /chat
    python manage.py migrate
    python manage.py runserver

See README.md in this directory for the full walkthrough and expected
output. `CostorahMiddleware` and the `costorah_doctor` management
command are wired up entirely in myproject/settings.py — nothing
COSTORAH-specific lives in this views/urls file except the
instrument() call, which is where a real app would also put it (e.g.
in an AppConfig.ready()).
"""

import json

from django.http import HttpRequest, JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from costorah.instrumentation import OpenAIInstrumentor

# Auto-captures every openai.* call made anywhere in the process after
# this point — no code changes needed at the call site.
OpenAIInstrumentor().instrument()


def root(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


@csrf_exempt
def chat(request: HttpRequest) -> JsonResponse:
    """Calls OpenAI's chat completions API. The OpenAIInstrumentor
    installed above automatically captures the resulting token usage
    and cost and submits it to COSTORAH — this view contains no
    COSTORAH-specific code at all."""
    from openai import OpenAI

    body = json.loads(request.body or b"{}")
    prompt = body.get("prompt", "Say hi")

    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return JsonResponse({"reply": response.choices[0].message.content or ""})


urlpatterns = [
    path("", root),
    path("chat", chat),
]
