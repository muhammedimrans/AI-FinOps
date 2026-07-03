# LangChain + COSTORAH example

A minimal script demonstrating EP-18.7's Success Criteria:
`LangChainInstrumentor().instrument()` followed by `ChatOpenAI().invoke(...)`
(here via a prompt-piped chain) auto-generating telemetry, with no manual
tracking calls.

## Setup

```bash
cd sdk/examples/langchain
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export COSTORAH_API_KEY=costorah_live_...   # optional — see below
export OPENAI_API_KEY=sk-...
```

## Run

```bash
python3 app.py
```

## Expected telemetry

One usage event: `provider=openai`, `model=gpt-4o-mini`, real
`input_tokens`/`output_tokens`/`cost`, plus `metadata.framework=langchain`,
`metadata.trace_id`/`span_id`, and `metadata.chain_name` (since the model
is invoked through a `prompt | model` chain, not called directly).

## Without `COSTORAH_API_KEY`

The script still runs — `LangChainInstrumentor` still captures the event
locally (`instrumentor.events_captured` after the call), it just has
nowhere to submit it.
