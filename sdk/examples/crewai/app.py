"""CrewAI + COSTORAH example (EP-18.7).

Demonstrates CrewAIInstrumentor().instrument() capturing usage from
every LLM call made inside a Crew run, with task_name/agent_role
enrichment — zero manual tracking calls.
"""

from __future__ import annotations

import os

from crewai import Agent, Crew, Task

from costorah import Costorah
from costorah.instrumentation import set_default_client
from costorah.instrumentation.crewai import CrewAIInstrumentor

api_key = os.environ.get("COSTORAH_API_KEY")
if api_key:
    set_default_client(Costorah(api_key=api_key))

instrumentor = CrewAIInstrumentor()
instrumentor.instrument()

researcher = Agent(
    role="researcher",
    goal="Summarize a topic in one sentence",
    backstory="A concise research assistant.",
)
task = Task(
    description="Summarize what COSTORAH (an AI FinOps platform) does, in one sentence.",
    expected_output="A single sentence.",
    agent=researcher,
)
crew = Crew(agents=[researcher], tasks=[task])


def main() -> None:
    result = crew.kickoff()
    print("Result:", result)
    print(f"Events captured by CrewAIInstrumentor: {instrumentor.events_captured_total}")


if __name__ == "__main__":
    main()
