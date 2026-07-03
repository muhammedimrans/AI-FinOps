import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  acknowledgeAlert,
  dismissAlert,
  listAlerts,
  resolveAlert,
  updateAlertPreferences,
} from "../services/api";
import { useAuthStore } from "../stores/auth";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("alerts API client (EP-19.3)", () => {
  beforeEach(() => {
    useAuthStore.setState({
      accessToken: "test-token",
      refreshToken: "refresh-token",
      user: { id: "u1", email: "a@b.com", display_name: "A" } as never,
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    useAuthStore.setState({ accessToken: null, refreshToken: null, user: null });
  });

  it("listAlerts sends filters as query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ alerts: [], total: 0 }));
    vi.stubGlobal("fetch", fetchMock);

    await listAlerts({
      organizationId: "org_1",
      status: "open",
      severity: "critical",
      search: "budget",
      limit: 25,
    });

    const calledUrl = new URL(fetchMock.mock.calls[0]![0] as string);
    expect(calledUrl.pathname).toBe("/v1/alerts");
    expect(calledUrl.searchParams.get("organization_id")).toBe("org_1");
    expect(calledUrl.searchParams.get("status")).toBe("open");
    expect(calledUrl.searchParams.get("severity")).toBe("critical");
    expect(calledUrl.searchParams.get("search")).toBe("budget");
    expect(calledUrl.searchParams.get("limit")).toBe("25");

    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.method).toBe("GET");
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer test-token");
  });

  it("acknowledgeAlert POSTs the reason and organization_id query param", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "alert_1",
        status: "acknowledged",
        acknowledgement_reason: "looking into it",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await acknowledgeAlert("org_1", "alert_1", "looking into it");

    const calledUrl = new URL(fetchMock.mock.calls[0]![0] as string);
    expect(calledUrl.pathname).toBe("/v1/alerts/alert_1/acknowledge");
    expect(calledUrl.searchParams.get("organization_id")).toBe("org_1");

    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ reason: "looking into it" });
    expect(result.status).toBe("acknowledged");
  });

  it("resolveAlert and dismissAlert hit the right sub-paths", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "alert_1", status: "resolved" }));
    vi.stubGlobal("fetch", fetchMock);
    await resolveAlert("org_1", "alert_1");
    expect(new URL(fetchMock.mock.calls[0]![0] as string).pathname).toBe(
      "/v1/alerts/alert_1/resolve",
    );

    fetchMock.mockResolvedValue(jsonResponse({ id: "alert_1", status: "dismissed" }));
    await dismissAlert("org_1", "alert_1");
    expect(new URL(fetchMock.mock.calls[1]![0] as string).pathname).toBe(
      "/v1/alerts/alert_1/dismiss",
    );
  });

  it("updateAlertPreferences PATCHes with organization_id in the query string", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ min_severity: "high" }));
    vi.stubGlobal("fetch", fetchMock);

    await updateAlertPreferences("org_1", { min_severity: "high" });

    const calledUrl = new URL(fetchMock.mock.calls[0]![0] as string);
    expect(calledUrl.pathname).toBe("/v1/alerts/preferences");
    expect(calledUrl.searchParams.get("organization_id")).toBe("org_1");
    const init = fetchMock.mock.calls[0]![1] as RequestInit;
    expect(init.method).toBe("PATCH");
  });

  it("throws ApiError with the backend detail message on failure", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ detail: "Alert not found" }, 404));
    vi.stubGlobal("fetch", fetchMock);

    await expect(resolveAlert("org_1", "missing")).rejects.toMatchObject({
      status: 404,
      message: "Alert not found",
    });
  });
});
