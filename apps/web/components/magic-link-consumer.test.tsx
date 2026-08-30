import { render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MagicLinkConsumer } from "@/components/magic-link-consumer";
import { api } from "@/lib/api/client";

afterEach(() => vi.restoreAllMocks());

describe("MagicLinkConsumer", () => {
  it("consumes a one-time token only once under React Strict Mode", async () => {
    const consume = vi.spyOn(api, "consumeMagicLink").mockResolvedValue({
      user: { id: "user-id", email: "user@example.com" },
      expiresAt: "2026-08-30T12:00:00Z",
    });

    render(
      <StrictMode>
        <MagicLinkConsumer token="one-time-token" />
      </StrictMode>,
    );

    expect(await screen.findByRole("heading", { name: "You’re signed in." })).toBeVisible();
    expect(consume).toHaveBeenCalledOnce();
    expect(consume).toHaveBeenCalledWith("one-time-token");
  });
});
