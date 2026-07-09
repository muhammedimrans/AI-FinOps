import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";

// EP-21.2 cross-origin auth handoff: apps/website's /signup and /login
// redirect here with the token pair + user + personal workspace encoded
// in the URL *fragment* (never sent over the network to any server, per
// RFC 3986 — unlike a query string, so this is not the "token-in-URL"
// anti-pattern CLAUDE.md warns against for the cookie architecture; it's
// specifically chosen because fragments are browser-only).
//
// This exists only because apps/dashboard hasn't migrated off its
// Zustand-held bearer token yet (CLAUDE.md §6, "optional... natural
// cleanup"). Once it adopts `credentials: "include"` everywhere, this
// module can be deleted — the httpOnly session cookie the backend
// already sets on register/login will carry the session across the
// subdomain redirect with no handoff payload needed at all.
//
// Runs synchronously at module load (imported once in main.tsx before
// the app renders) so the Zustand store is already populated by the
// time ProtectedRoute's first render checks it — no login-screen flash.

interface HandoffUser {
  id: string;
  email: string;
  username: string | null;
  display_name: string;
  status: string;
  email_verified: boolean;
}

interface HandoffWorkspace {
  id: string;
  name: string;
}

interface HandoffPayload {
  access_token: string;
  refresh_token: string;
  user: HandoffUser;
  workspace?: HandoffWorkspace;
}

function isHandoffPayload(value: unknown): value is HandoffPayload {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v["access_token"] === "string" &&
    typeof v["refresh_token"] === "string" &&
    typeof v["user"] === "object" &&
    v["user"] !== null
  );
}

/** Returns true if a session handoff was found and consumed. */
export function consumeSessionHandoff(): boolean {
  const hash = window.location.hash;
  const match = /(?:^#|&)session=([^&]+)/.exec(hash);
  if (!match || !match[1]) return false;

  // Strip the fragment immediately regardless of outcome — a token pair
  // must never linger in the address bar / browser history.
  const stripHash = () => {
    const url = new URL(window.location.href);
    url.hash = "";
    window.history.replaceState(null, "", url.toString());
  };

  try {
    const json = atob(decodeURIComponent(match[1]));
    const payload: unknown = JSON.parse(json);
    if (!isHandoffPayload(payload)) {
      stripHash();
      return false;
    }

    useAuthStore.getState().setLogin(
      payload.access_token,
      payload.refresh_token,
      {
        id: payload.user.id,
        email: payload.user.email,
        username: payload.user.username,
        display_name: payload.user.display_name,
        status: payload.user.status,
        email_verified: payload.user.email_verified,
      },
      false, // handoff sessions are not "remembered" past this browser session
    );

    if (payload.workspace) {
      useOrgStore.getState().setOrganization(payload.workspace.id, payload.workspace.name);
    }

    stripHash();
    return true;
  } catch {
    stripHash();
    return false;
  }
}
