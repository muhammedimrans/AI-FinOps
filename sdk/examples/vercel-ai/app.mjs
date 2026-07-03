// Vercel AI SDK + COSTORAH example (EP-18.7).
//
// Demonstrates VercelAIInstrumentor capturing usage from a real
// generateText() call, via wrapModel() — zero manual tracking calls.

import { openai } from "@ai-sdk/openai";
import { generateText } from "ai";
import { Costorah, VercelAIInstrumentor, setDefaultClient } from "@costorah/sdk";

const apiKey = process.env.COSTORAH_API_KEY;
if (apiKey) {
  setDefaultClient(new Costorah({ apiKey }));
}

const instrumentor = new VercelAIInstrumentor();
instrumentor.instrument();

const model = instrumentor.wrapModel(openai("gpt-4o-mini"));

const result = await generateText({
  model,
  prompt: "Say hi to COSTORAH in five words.",
});

console.log("Response:", result.text);
console.log(`Events captured by VercelAIInstrumentor: ${instrumentor.eventsCaptured}`);
