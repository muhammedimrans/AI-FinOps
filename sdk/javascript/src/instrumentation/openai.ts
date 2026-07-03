/**
 * OpenAIInstrumentor — automatic usage capture for the official `openai`
 * npm package's Chat Completions and Responses APIs (streaming and
 * non-streaming).
 *
 *     import OpenAI from "openai";
 *     import { OpenAIInstrumentor } from "@costorah/sdk";
 *
 *     new OpenAIInstrumentor().instrument();
 *
 *     const client = new OpenAI();
 *     await client.responses.create({ model: "gpt-4.1", input: "Hello" });
 */

import { OpenAICompatibleInstrumentor } from "./openaiCompatible.js";

export class OpenAIInstrumentor extends OpenAICompatibleInstrumentor {
  readonly name = "openai";
  readonly fixedProvider = "openai";
}
