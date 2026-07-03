/**
 * Minimal standalone Node http server instrumented with COSTORAH — run with:
 *
 *   npm install @costorah/sdk openai
 *   export COSTORAH_API_KEY=costorah_live_xxxxxxxxx
 *   export OPENAI_API_KEY=sk-...          # only needed for /chat
 *   node server.mjs
 *
 * See README.md in this directory for the full walkthrough and expected
 * output.
 */

import http from "node:http";

import { OpenAIInstrumentor } from "@costorah/sdk";
import { costorahNodeMiddleware } from "@costorah/sdk/node";

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site.
new OpenAIInstrumentor().instrument();

// Everything below this line is what a real app adds: one middleware
// wrapper. It auto-initializes a Costorah client from COSTORAH_API_KEY,
// wires it as the default client the instrumentor above submits
// through, and attaches request context (request ID, path, method) to
// every usage event captured during each request.
const withCostorah = costorahNodeMiddleware();

const server = http.createServer((req, res) => {
  withCostorah(req, res, async () => {
    if (req.url === "/") {
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ status: "ok" }));
      return;
    }

    if (req.url?.startsWith("/chat") && req.method === "POST") {
      const { default: OpenAI } = await import("openai");
      const client = new OpenAI();
      const url = new URL(req.url, "http://localhost");
      const prompt = url.searchParams.get("prompt") ?? "Say hi";
      const response = await client.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [{ role: "user", content: prompt }],
      });
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ reply: response.choices[0]?.message?.content ?? "" }));
      return;
    }

    res.statusCode = 404;
    res.end();
  });
});

const port = process.env.PORT ?? 3000;
server.listen(port, () => {
  console.log(`listening on http://127.0.0.1:${port}`);
});
