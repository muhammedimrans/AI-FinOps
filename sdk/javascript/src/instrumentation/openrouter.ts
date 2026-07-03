/**
 * OpenRouterInstrumentor — automatic usage capture for OpenRouter calls
 * made through the official `openai` package pointed at OpenRouter's
 * OpenAI-compatible endpoint (OpenRouter's documented integration path;
 * it has no bespoke npm SDK). Detected via `baseURL` containing
 * "openrouter.ai".
 */

import { OpenAICompatibleInstrumentor } from "./openaiCompatible.js";

export class OpenRouterInstrumentor extends OpenAICompatibleInstrumentor {
  readonly name = "openrouter";
  readonly fixedProvider = "openrouter";
}
