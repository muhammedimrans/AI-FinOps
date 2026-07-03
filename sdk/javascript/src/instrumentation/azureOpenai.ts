/**
 * AzureOpenAIInstrumentor — automatic usage capture for Azure OpenAI
 * Service calls made through the official `openai` package's
 * `AzureOpenAI` client. Shares the same patched Completions/Responses
 * prototypes as every other OpenAI-family instrumentor (see
 * openaiCompatible.ts); only Azure clients (detected by class name) are
 * captured while this instrumentor is active.
 */

import { OpenAICompatibleInstrumentor } from "./openaiCompatible.js";

export class AzureOpenAIInstrumentor extends OpenAICompatibleInstrumentor {
  readonly name = "azure_openai";
  readonly fixedProvider = "azure_openai";
}
