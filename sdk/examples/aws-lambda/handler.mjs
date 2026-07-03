/**
 * Minimal AWS Lambda function (Function URL / API Gateway) instrumented
 * with COSTORAH — deploy however you normally deploy a Lambda (SAM,
 * CDK, Serverless Framework, or the console), with:
 *
 *   COSTORAH_API_KEY=costorah_live_xxxxxxxxx
 *   OPENAI_API_KEY=sk-...          # only needed for /chat
 *
 * set as environment variables on the function.
 *
 * See README.md in this directory for local testing instructions
 * (invoking the handler directly with sample events) and expected
 * output.
 */

import { OpenAIInstrumentor } from "@costorah/sdk";
import { costorahLambda } from "@costorah/sdk/lambda";

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site, and
// module-level (outside the handler) so it only runs once per cold
// start, not per invocation.
new OpenAIInstrumentor().instrument();

export const handler = costorahLambda(async (event) => {
  const path = event.rawPath ?? event.path ?? "/";
  const method = event.requestContext?.http?.method ?? event.httpMethod ?? "GET";

  if (path === "/") {
    return { statusCode: 200, body: JSON.stringify({ status: "ok" }) };
  }

  if (path === "/chat" && method === "POST") {
    const { default: OpenAI } = await import("openai");
    const client = new OpenAI();
    const params = new URLSearchParams(event.rawQueryString ?? event.queryStringParameters ?? "");
    const prompt = params.get("prompt") ?? "Say hi";
    const response = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt }],
    });
    return {
      statusCode: 200,
      body: JSON.stringify({ reply: response.choices[0]?.message?.content ?? "" }),
    };
  }

  return { statusCode: 404, body: "" };
});
