import { useCallback, useEffect, useMemo, useState } from "react";
import {
  loadConversations,
  newConversation,
  persistConversations,
  type Conversation,
} from "./conversations";
import type { ConversationTurn } from "./types";

/** EP-25.4.3 — the client-only conversation-memory layer (see
 * conversations.ts's own header comment for the honest disclosure of what
 * this does and doesn't persist). One hook, one localStorage-backed list,
 * shared by ChatTab, the History sidebar, and the homepage's "Recent
 * conversations" section — never a second, out-of-sync copy of this state. */
export function useConversations(organizationId: string) {
  const [conversations, setConversations] = useState<Conversation[]>(() => loadConversations(organizationId));
  const [activeId, setActiveId] = useState<string | null>(null);

  useEffect(() => {
    persistConversations(organizationId, conversations);
  }, [organizationId, conversations]);

  const active = useMemo(() => conversations.find((c) => c.id === activeId) ?? null, [conversations, activeId]);

  const createNew = useCallback(() => {
    const conv = newConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    return conv;
  }, []);

  const setTurns = useCallback(
    (conversationId: string, updater: (turns: ConversationTurn[]) => ConversationTurn[]) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id === conversationId
            ? { ...c, turns: updater(c.turns), updatedAt: new Date().toISOString() }
            : c,
        ),
      );
    },
    [],
  );

  const rename = useCallback((conversationId: string, name: string) => {
    setConversations((prev) =>
      prev.map((c) => (c.id === conversationId ? { ...c, name, updatedAt: new Date().toISOString() } : c)),
    );
  }, []);

  const togglePin = useCallback((conversationId: string) => {
    setConversations((prev) => prev.map((c) => (c.id === conversationId ? { ...c, pinned: !c.pinned } : c)));
  }, []);

  const remove = useCallback(
    (conversationId: string) => {
      setConversations((prev) => prev.filter((c) => c.id !== conversationId));
      setActiveId((prev) => (prev === conversationId ? null : prev));
    },
    [],
  );

  const duplicate = useCallback((conversationId: string) => {
    setConversations((prev) => {
      const source = prev.find((c) => c.id === conversationId);
      if (!source) return prev;
      const copy: Conversation = {
        ...source,
        id: crypto.randomUUID(),
        name: `${source.name} (copy)`,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      };
      return [copy, ...prev];
    });
  }, []);

  return {
    conversations,
    activeId,
    setActiveId,
    active,
    createNew,
    setTurns,
    rename,
    togglePin,
    remove,
    duplicate,
  };
}
