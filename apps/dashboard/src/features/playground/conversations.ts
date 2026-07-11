import type { ConversationTurn } from "./types";

// EP-25.4.3 Part 8/9/12 — Costorah's backend has no server-side "chat" or
// "conversation" entity (unchanged since EP-25.4/EP-25.4.1 — every
// PlaygroundExecution row is one independent prompt/response pair). This
// module is the client-only conversation-memory layer that gives the
// Playground a real ChatGPT-like multi-chat experience without pretending
// the backend has something it doesn't: conversations, names, pins, and
// folders are all local (persisted to localStorage per organization), while
// every *turn* inside a conversation is still backed by a real, persisted
// PlaygroundExecution once it succeeds (visible in the History tab exactly
// as before). Renaming/deleting/duplicating a *conversation* is purely a
// local-memory operation; it does not touch any backend row. Deleting an
// individual *message* inside a conversation still calls the real
// DELETE .../history/{id} endpoint (unchanged from EP-25.4.1, see
// MessageBubble's onDelete wiring in Playground.tsx).

export interface Conversation {
  id: string;
  name: string;
  pinned: boolean;
  turns: ConversationTurn[];
  createdAt: string;
  updatedAt: string;
}

const STORAGE_PREFIX = "costorah:playground:conversations:";

function storageKey(organizationId: string): string {
  return `${STORAGE_PREFIX}${organizationId}`;
}

export function loadConversations(organizationId: string): Conversation[] {
  try {
    const raw = window.localStorage.getItem(storageKey(organizationId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch {
    return [];
  }
}

export function persistConversations(organizationId: string, conversations: Conversation[]): void {
  try {
    window.localStorage.setItem(storageKey(organizationId), JSON.stringify(conversations));
  } catch {
    // Storage unavailable/full — conversation memory degrades to
    // session-only (current render state), never a hard failure.
  }
}

export function newConversation(name = "New chat"): Conversation {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    name,
    pinned: false,
    turns: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function conversationTitle(conversation: Conversation): string {
  if (conversation.name !== "New chat") return conversation.name;
  const firstUserPrompt = conversation.turns.find((t) => t.userPrompt.trim())?.userPrompt;
  return firstUserPrompt ? firstUserPrompt.slice(0, 48) : conversation.name;
}

/** EP-25.4.3 Part 12 — ChatGPT-style Today/Yesterday/This Week/Older
 * grouping, plus a separate Pinned bucket shown first regardless of date.
 * Grouped by `updatedAt` (last activity), not `createdAt`, so a chat you
 * keep coming back to stays near the top. */
export function groupConversationsByRecency(
  conversations: Conversation[],
): { label: string; items: Conversation[] }[] {
  const pinned = conversations.filter((c) => c.pinned);
  const unpinned = conversations.filter((c) => !c.pinned);

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const buckets: Record<"Today" | "Yesterday" | "This Week" | "Older", Conversation[]> = {
    Today: [],
    Yesterday: [],
    "This Week": [],
    Older: [],
  };
  for (const c of unpinned) {
    const updated = new Date(c.updatedAt);
    const startOfUpdated = new Date(updated.getFullYear(), updated.getMonth(), updated.getDate());
    const diffDays = Math.round((startOfToday.getTime() - startOfUpdated.getTime()) / 86_400_000);
    if (diffDays <= 0) buckets.Today.push(c);
    else if (diffDays === 1) buckets.Yesterday.push(c);
    else if (diffDays <= 7) buckets["This Week"].push(c);
    else buckets.Older.push(c);
  }

  const groups: { label: string; items: Conversation[] }[] = [];
  if (pinned.length > 0) groups.push({ label: "Pinned", items: pinned });
  for (const label of ["Today", "Yesterday", "This Week", "Older"] as const) {
    if (buckets[label].length > 0) groups.push({ label, items: buckets[label] });
  }
  return groups;
}

export function exportConversationMarkdown(conversation: Conversation): string {
  const header = `# ${conversationTitle(conversation)}\n\n`;
  const body = conversation.turns
    .map((t) => {
      const sys = t.systemPrompt ? `**System:** ${t.systemPrompt}\n\n` : "";
      const user = `**You:** ${t.userPrompt}\n\n`;
      const resp = t.execution?.response_text
        ? `**${t.providerType} / ${t.model}:**\n${t.execution.response_text}\n`
        : t.error
          ? `**Error:** ${t.error}\n`
          : "";
      return sys + user + resp;
    })
    .join("\n---\n\n");
  return header + body;
}
