# CrewAI + COSTORAH example

A minimal single-agent Crew demonstrating EP-18.7's Success Criteria:
`CrewAIInstrumentor().instrument()` followed by `crew.kickoff()` — every
LLM call inside the crew automatically generates telemetry.

## Setup

```bash
cd sdk/examples/crewai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export COSTORAH_API_KEY=costorah_live_...   # optional — see below
export OPENAI_API_KEY=sk-...                 # CrewAI's default LLM provider
```

## Run

```bash
python3 app.py
```

## Expected telemetry

One or more usage events (depending on CrewAI's internal retry/planning
behavior), each with `provider=openai` (inferred from CrewAI's default
model), real token counts and cost, and `metadata.framework=crewai`,
`metadata.task_name="Summarize what COSTORAH..."`,
`metadata.agent_role="researcher"`.

## Without `COSTORAH_API_KEY`

The crew still runs — `CrewAIInstrumentor` still captures events locally
(`instrumentor.events_captured_total`), it just has nowhere to submit
usage records to.
