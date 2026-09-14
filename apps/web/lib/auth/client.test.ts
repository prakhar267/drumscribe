import { afterEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  getSession: vi.fn(),
  signOut: vi.fn(),
  exchangeNeonSession: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@neondatabase/auth/next", () => ({
  createAuthClient: () => ({
    getSession: mocks.getSession,
    signOut: mocks.signOut,
  }),
}));

vi.mock("@/lib/api/client", () => ({
  api: {
    exchangeNeonSession: mocks.exchangeNeonSession,
    logout: mocks.logout,
  },
}));

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("Neon account bridge", () => {
  it("exchanges the verified OAuth session for a DrumToScore API session", async () => {
    mocks.getSession.mockResolvedValue({
      data: { session: { id: "session-1" }, user: { id: "user-1" } },
      error: null,
    });
    mocks.exchangeNeonSession.mockResolvedValue({ user: { id: "user-1" } });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ token: "signed-neon-jwt" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { completeNeonAuthentication } = await import("@/lib/auth/client");
    await completeNeonAuthentication();

    expect(mocks.getSession).toHaveBeenCalledOnce();
    expect(fetchMock).toHaveBeenCalledWith("/api/auth/token", {
      credentials: "include",
      headers: { "X-Force-Fetch": "true" },
    });
    expect(mocks.exchangeNeonSession).toHaveBeenCalledWith("signed-neon-jwt");
  });

  it("fails closed when the auth server does not return a JWT", async () => {
    mocks.getSession.mockResolvedValue({
      data: { session: { id: "session-1" }, user: { id: "user-1" } },
      error: null,
    });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ message: "Unauthorized" }), {
          status: 401,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const { completeNeonAuthentication } = await import("@/lib/auth/client");

    await expect(completeNeonAuthentication()).rejects.toThrow("Unauthorized");
    expect(mocks.exchangeNeonSession).not.toHaveBeenCalled();
  });
});
