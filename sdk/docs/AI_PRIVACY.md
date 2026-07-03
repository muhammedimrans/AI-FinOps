# AI Framework Instrumentation — Privacy

Every instrumentor added in EP-18.7 (`costorah.instrumentation.langchain`,
`.crewai`, `.mcp` in Python; `LangChainInstrumentor`, `VercelAIInstrumentor`
in JavaScript) follows the same rule already established by EP-18.2's
provider instrumentors: **capture metadata only, never content.**

## Never stored, logged, or transmitted by any AI framework instrumentor

- Prompt text / input messages
- Response text / generated content
- Tool call arguments and tool call results
- Retrieved documents (no retrieval-specific instrumentor exists yet — see
  `AI_FRAMEWORK_INTEGRATIONS.md`'s deferred list)
- Embeddings or vectors (no embeddings/vector-DB instrumentor exists yet)
- MCP resource contents or prompt contents
- API keys, secrets, cookies, headers

## What is captured

- Provider, model name, token counts (input/output/total/reasoning/cached),
  cost, currency
- Latency, status (success/error), finish reason
- Trace/span/parent-span IDs
- Framework-specific names: LangChain chain/tool name; CrewAI task
  name/agent role; MCP tool/resource/prompt name
- Local-only counters (`events_captured_total`) and debug-level structured
  log lines for lifecycle events that don't produce a usage record

## How this is enforced, not just documented

Each instrumentor's usage-extraction function reads a small, explicit set
of fields off the framework's own structured event/result objects — e.g.
LangChain's `LLMResult.generations[].message.usage_metadata` (a typed
token-count structure), not `.content`. There is no code path in any of
these five instrumentors that reads a `content`, `text`, `messages`,
`prompt`, `arguments`, or `output` field from an LLM/tool/resource
response and forwards it anywhere.

Every test suite for these instrumentors includes an explicit privacy
assertion in its end-to-end test: after running a real call through the
real framework package with an intentionally distinctive prompt/response
string, the test asserts that string never appears anywhere in the
JSON-serialized captured usage payload. This is checked, not just
documented — see e.g. `sdk/python/tests/instrumentation/test_langchain.py::
test_end_to_end_via_real_chatopenai`, `test_crewai.py::
test_llm_call_completed_submits_real_usage`, `test_mcp.py::
test_call_tool_is_captured_and_result_content_never_logged`,
`sdk/javascript/tests/instrumentation/langchainJs.test.ts` and
`vercelAi.test.ts`'s end-to-end tests.
