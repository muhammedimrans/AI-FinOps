/**
 * Minimal Next.js App Router Route Handler instrumented with COSTORAH —
 * demonstrating the integration named in EP-18.6's Success Criteria:
 * `export const POST = costorahHandler(async (req) => { ... })`.
 *
 * Run with (from sdk/examples/nextjs/):
 *
 *   npm install
 *   export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
 *   export OPENAI_API_KEY=sk-...
 *   npm run dev
 *
 * See README.md in this directory for the full walkthrough and expected
 * output.
 */

import { OpenAIInstrumentor } from "@costorah/sdk";
import { costorahHandler } from "@costorah/sdk/next";

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site.
new OpenAIInstrumentor().instrument();

export const POST = costorahHandler(async (req: Request) => {
  const { prompt } = (await req.json()) as { prompt?: string };

  // The OpenAIInstrumentor installed above automatically captures the
  // resulting token usage and cost and submits it to COSTORAH — this
  // route handler contains no COSTORAH-specific code at all.
  const { default: OpenAI } = await import("openai");
  const client = new OpenAI();
  const response = await client.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: prompt ?? "Say hi" }],
  });

  return Response.json({ reply: response.choices[0]?.message?.content ?? "" });
});
