import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, googleOAuthStartUrl, login, register } from "./api";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("register()", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to /v1/auth/register with credentials included", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(201, {
        access_token: "a",
        refresh_token: "r",
        token_type: "bearer",
        expires_in: 1800,
        user: {
          id: "usr_1",
          email: "ada@example.com",
          username: null,
          display_name: "Ada",
          status: "active",
          email_verified: false,
        },
        workspace: {
          id: "org_1",
          name: "Ada's Workspace",
          slug: "ada-workspace",
          is_personal: true,
        },
      }),
    );

    const result = await register({
      email: "ada@example.com",
      password: "correct-horse-battery-staple",
      display_name: "Ada",
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/auth/register");
    expect(init.credentials).toBe("include");
    expect(init.method).toBe("POST");
    expect(result.workspace.is_personal).toBe(true);
    expect(result.user.email).toBe("ada@example.com");
  });

  it("throws ApiError with status 409 on duplicate email", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(409, { detail: "An account with this email already exists" }),
    );

    await expect(
      register({ email: "taken@example.com", password: "x".repeat(10), display_name: "X" }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("throws ApiError with the backend's detail message", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(422, { detail: "Invalid input" }));

    try {
      await register({ email: "x@example.com", password: "x".repeat(10), display_name: "X" });
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).message).toBe("Invalid input");
    }
  });
});

describe("login()", () => {
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts to /v1/auth/login with credentials included", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse(200, {
        access_token: "a",
        refresh_token: "r",
        token_type: "bearer",
        expires_in: 1800,
        user: {
          id: "usr_1",
          email: "ada@example.com",
          username: null,
          display_name: "Ada",
          status: "active",
          email_verified: false,
        },
      }),
    );

    await login({ email: "ada@example.com", password: "whatever" });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/v1/auth/login");
    expect(init.credentials).toBe("include");
  });

  it("throws ApiError with status 401 on invalid credentials", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(401, { detail: "Invalid email or password" }));

    await expect(login({ email: "ada@example.com", password: "wrong" })).rejects.toMatchObject({
      status: 401,
    });
  });
});

describe("googleOAuthStartUrl()", () => {
  it("points at the backend's GET /v1/auth/google/start", () => {
    expect(googleOAuthStartUrl()).toMatch(/\/v1\/auth\/google\/start$/);
  });
});
