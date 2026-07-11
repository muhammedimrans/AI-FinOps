import type { PlaygroundExecutionRecord } from "../../services/api";

// EP-25.4.1 — a "conversation turn" is a purely client-side pairing of one
// sent prompt with its (eventually arriving) execution result. Costorah's
// backend has no multi-turn conversation entity — every Playground request
// is an independent, one-shot prompt/response pair (EP-25.4) — so a "chat"
// in this UI is a local, in-memory sequence of turns, never something the
// backend persists as a thread. Individual turns *do* persist once they
// succeed (as a real PlaygroundExecution row, visible in History), which is
// what the History sidebar/tab actually browses.
export interface ConversationTurn {
  id: string;
  connectionId: string;
  providerType: string;
  model: string;
  systemPrompt: string;
  userPrompt: string;
  execution: PlaygroundExecutionRecord | null;
  error: string | null;
  isPending: boolean;
  /** Set when this turn was created by "Continue" — disclosed in the UI
   * rather than pretending real conversation history was sent. */
  isContinuation?: boolean;
}
