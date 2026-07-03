/**
 * GrokInstrumentor — automatic usage capture for xAI Grok calls made
 * through the official `openai` package pointed at xAI's OpenAI-compatible
 * endpoint. Detected via `baseURL` containing "api.x.ai".
 */

import { OpenAICompatibleInstrumentor } from "./openaiCompatible.js";

export class GrokInstrumentor extends OpenAICompatibleInstrumentor {
  readonly name = "grok";
  readonly fixedProvider = "grok";
}
