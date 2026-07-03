"""LangChain + COSTORAH example (EP-18.7).

Demonstrates LangChainInstrumentor().instrument() capturing usage from a
real ChatOpenAI call with zero manual tracking calls.
"""

from __future__ import annotations

import os

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from costorah import Costorah
from costorah.instrumentation import set_default_client
from costorah.instrumentation.langchain import LangChainInstrumentor

api_key = os.environ.get("COSTORAH_API_KEY")
if api_key:
    set_default_client(Costorah(api_key=api_key))

LangChainInstrumentor().instrument()

prompt = ChatPromptTemplate.from_template("Say hi to {name} in five words.")
model = ChatOpenAI(model="gpt-4o-mini")
chain = prompt | model


def main() -> None:
    result = chain.invoke({"name": "COSTORAH"})
    print("Response:", result.content)
    print(
        "Usage was captured automatically by LangChainInstrumentor — "
        "check your COSTORAH dashboard, or run with COSTORAH_API_KEY unset "
        "to see it captured locally only."
    )


if __name__ == "__main__":
    main()
