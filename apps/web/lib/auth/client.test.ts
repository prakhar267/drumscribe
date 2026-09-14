import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  createAuthClient: vi.fn(),
  getSession: vi.fn(),
  signOut: vi.fn(),
  exchangeNeonSession: vi.fn(),
  deleteAccount: vi.fn(),
  logout: vi.fn(),
}));

vi.mock("@neondatabase/auth/next", () => ({
  createAuthClient: mocks.createAuthClient,
}));

vi.mock("@/lib/api/client", () => ({
  api: {
    exchangeNeonSession: mocks.exchangeNeonSession,
    deleteAccount: mocks.deleteAccount,
    logout: mocks.logout,
  },
}));

beforeEach(() => {
  mocks.createAuthClient.mockReturnValue({
    getSession: mocks.getSession,
    signOut: mocks.signOut,
  });
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("Neon account bridge", () => {
  it("does not initialize the browser SDK in module scope", async () => {
    await import("@/lib/auth/client");

    expect(mocks.createAuthClient).not.toHaveBeenCalled();
  });

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

  it("clears the Neon session after deleting the product account", async () => {
    vi.stubEnv("NEXT_PUBLIC_AUTH_PROVIDER", "neon");
    mocks.deleteAccount.mockResolvedValue({ accepted: true });
    mocks.logout.mockResolvedValue(undefined);
    mocks.signOut.mockResolvedValue({ error: null });

    const { deleteAccountEverywhere } = await import("@/lib/auth/client");
    await deleteAccountEverywhere();

    expect(mocks.deleteAccount).toHaveBeenCalledOnce();
    expect(mocks.logout).toHaveBeenCalledOnce();
    expect(mocks.signOut).toHaveBeenCalledOnce();
    expect(mocks.deleteAccount.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.signOut.mock.invocationCallOrder[0],
    );
  });
});
