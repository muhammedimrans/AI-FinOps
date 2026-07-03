/**
 * OllamaInstrumentor — automatic usage capture for local Ollama calls
 * made through the official `openai` package pointed at Ollama's
 * OpenAI-compatible endpoint. Detected via `baseURL` containing
 * "localhost:11434"/"127.0.0.1:11434".
 */

import { OpenAICompatibleInstrumentor } from "./openaiCompatible.js";

export class OllamaInstrumentor extends OpenAICompatibleInstrumentor {
  readonly name = "ollama";
  readonly fixedProvider = "ollama";
}
