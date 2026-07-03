/**
 * Minimal Cloudflare Worker instrumented with COSTORAH — deploy with:
 *
 *   npm install
 *   wrangler secret put COSTORAH_API_KEY
 *   wrangler secret put OPENAI_API_KEY   # only needed for /chat
 *   wrangler deploy
 *
 * See README.md in this directory for the full walkthrough, expected
 * output, and local dev instructions (wrangler dev).
 */

import { OpenAIInstrumentor } from "@costorah/sdk";
import { costorahWorker } from "@costorah/sdk/cloudflare";

interface Env {
  COSTORAH_API_KEY: string;
  OPENAI_API_KEY?: string;
}

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site.
new OpenAIInstrumentor().instrument();

export default costorahWorker<Env>(async (request, env) => {
  const url = new URL(request.url);

  if (url.pathname === "/") {
    return Response.json({ status: "ok" });
  }

  if (url.pathname === "/chat" && request.method === "POST") {
    const { default: OpenAI } = await import("openai");
    const client = new OpenAI({ apiKey: env.OPENAI_API_KEY });
    const prompt = url.searchParams.get("prompt") ?? "Say hi";
    const response = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
    });
    return Response.json({ reply: response.choices[0]?.message?.content ?? "" });
  }

  return new Response(null, { status: 404 });
});
