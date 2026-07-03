import { Body, Controller, Get, Post } from "@nestjs/common";
import { OpenAIInstrumentor } from "@costorah/sdk";

// Auto-captures every OpenAI SDK call made anywhere in the process
// after this point — no code changes needed at the call site.
new OpenAIInstrumentor().instrument();

@Controller()
export class AppController {
  @Get()
  root(): { status: string } {
    return { status: "ok" };
  }

  @Post("chat")
  async chat(@Body("prompt") prompt: string): Promise<{ reply: string }> {
    // The OpenAIInstrumentor installed above automatically captures the
    // resulting token usage and cost and submits it to COSTORAH — this
    // controller method contains no COSTORAH-specific code at all.
    const { default: OpenAI } = await import("openai");
    const client = new OpenAI();
    const response = await client.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [{ role: "user", content: prompt ?? "Say hi" }],
    });
    return { reply: response.choices[0]?.message?.content ?? "" };
  }
}
