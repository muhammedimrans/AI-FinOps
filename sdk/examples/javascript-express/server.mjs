/**
 * Minimal Express app instrumented with COSTORAH — run with:
 *
 *   npm install @costorah/sdk express openai
 *   export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
 *   export OPENAI_API_KEY=sk-...          # only needed for /chat
 *   node server.mjs
 *
 * See README.md in this directory for the full walkthrough and expected
 * output.
 */

import express from "express";
import { OpenAIInstrumentor } from "@costorah/sdk";
import { costorahMiddleware } from "@costorah/sdk/express";

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site.
new OpenAIInstrumentor().instrument();

const app = express();

// Everything below this line is what a real app adds: one middleware
// line. It auto-initializes a Costorah client from COSTORAH_API_KEY,
// wires it as the default client the instrumentor above submits
// through, and attaches request context (request ID, path, method) to
// every usage event captured during each request.
app.use(costorahMiddleware());

app.get("/", (_req, res) => {
  res.json({ status: "ok" });
});

app.post("/chat", express.json(), async (req, res) => {
  // The OpenAIInstrumentor installed above automatically captures the
  // resulting token usage and cost and submits it to COSTORAH — this
  // handler contains no COSTORAH-specific code at all.
  const { default: OpenAI } = await import("openai");
  const client = new OpenAI();
  const response = await client.chat.completions.create({
    model: "gpt-4o-mini",
    messages: [{ role: "user", content: req.body.prompt ?? "Say hi" }],
  });
  res.json({ reply: response.choices[0]?.message?.content ?? "" });
});

const port = process.env.PORT ?? 3000;
app.listen(port, () => {
  console.log(`listening on http://127.0.0.1:${port}`);
});
