import { beforeEach, describe, expect, it } from "vitest";
import { consumeSessionHandoff } from "../lib/consumeSessionHandoff";
import { useAuthStore } from "../stores/auth";
import { useOrgStore } from "../stores/org";

function setHash(hash: string) {
  window.history.replaceState(null, "", `/onboarding${hash}`);
}

const user = {
  id: "usr_1",
  email: "ada@example.com",
  username: null,
  display_name: "Ada",
  status: "active",
  email_verified: false,
};

function encodePayload(payload: unknown): string {
  return encodeURIComponent(btoa(JSON.stringify(payload)));
}

describe("consumeSessionHandoff", () => {
  beforeEach(() => {
    useAuthStore.getState().clearAuth();
    useOrgStore.getState().clearOrganization();
    setHash("");
  });

  it("returns false and changes nothing when there is no session fragment", () => {
    setHash("");
    const result = consumeSessionHandoff();
    expect(result).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull();
  });

  it("populates the auth store from a valid handoff and strips the hash", () => {
    const encoded = encodePayload({
      access_token: "a.b.c",
      refresh_token: "r-token",
      user,
      workspace: { id: "org_1", name: "Ada's Workspace" },
    });
    setHash(`#session=${encoded}`);

    const result = consumeSessionHandoff();

    expect(result).toBe(true);
    expect(useAuthStore.getState().accessToken).toBe("a.b.c");
    expect(useAuthStore.getState().refreshToken).toBe("r-token");
    expect(useAuthStore.getState().user?.email).toBe("ada@example.com");
    expect(useOrgStore.getState().organizationId).toBe("org_1");
    expect(useOrgStore.getState().organizationName).toBe("Ada's Workspace");
    expect(window.location.hash).toBe("");
  });

  it("works without a workspace (login handoff has no workspace field)", () => {
    const encoded = encodePayload({ access_token: "a.b.c", refresh_token: "r-token", user });
    setHash(`#session=${encoded}`);

    const result = consumeSessionHandoff();

    expect(result).toBe(true);
    expect(useAuthStore.getState().accessToken).toBe("a.b.c");
    expect(useOrgStore.getState().organizationId).toBeNull();
  });

  it("carries onboarding_completed through into the auth store (EP-21.3)", () => {
    const encoded = encodePayload({
      access_token: "a.b.c",
      refresh_token: "r-token",
      user: { ...user, onboarding_completed: false },
    });
    setHash(`#session=${encoded}`);

    consumeSessionHandoff();

    expect(useAuthStore.getState().user?.onboarding_completed).toBe(false);
  });

  it("strips the hash and returns false on malformed base64", () => {
    setHash("#session=not-valid-base64!!!");
    const result = consumeSessionHandoff();
    expect(result).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(window.location.hash).toBe("");
  });

  it("strips the hash and returns false when required fields are missing", () => {
    const encoded = encodePayload({ access_token: "a.b.c" }); // missing refresh_token, user
    setHash(`#session=${encoded}`);
    const result = consumeSessionHandoff();
    expect(result).toBe(false);
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(window.location.hash).toBe("");
  });

  it("ignores an unrelated hash", () => {
    setHash("#some-other-fragment");
    const result = consumeSessionHandoff();
    expect(result).toBe(false);
  });
});
