/**
 * Minimal Bun HTTP server instrumented with COSTORAH — run with:
 *
 *   bun install
 *   export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
 *   export OPENAI_API_KEY=sk-...          # only needed for /chat
 *   bun run server.ts
 *
 * See README.md in this directory for the full walkthrough and expected
 * output. Uses `costorahHandler` (from @costorah/sdk/next — despite the
 * name, it has no Next.js dependency; it's a generic Request -> Response
 * wrapper) since Bun.serve()'s fetch handler is fetch-API-shaped,
 * exactly what that wrapper targets. See sdk/docs/BUN.md.
 */

import { OpenAIInstrumentor } from "@costorah/sdk";
import { costorahHandler } from "@costorah/sdk/next";

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site.
new OpenAIInstrumentor().instrument();

const fetchHandler = costorahHandler(async (req: Request) => {
  const url = new URL(req.url);

  if (url.pathname === "/") {
    return Response.json({ status: "ok" });
  }

  if (url.pathname === "/chat" && req.method === "POST") {
    const { default: OpenAI } = await import("openai");
    const client = new OpenAI();
    const prompt = url.searchParams.get("prompt") ?? "Say hi";
    const response = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
    });
    return Response.json({ reply: response.choices[0]?.message?.content ?? "" });
  }

  return new Response(null, { status: 404 });
});

const server = Bun.serve({
  port: Number(process.env.PORT ?? 3000),
  fetch: fetchHandler,
});

console.log(`listening on http://127.0.0.1:${server.port}`);
