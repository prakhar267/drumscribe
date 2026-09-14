"use client";

import { createAuthClient } from "@neondatabase/auth/next";
import { api } from "@/lib/api/client";

export const neonAuthEnabled = process.env.NEXT_PUBLIC_AUTH_PROVIDER === "neon";
export const neonAuthSocialProviders = (process.env.NEXT_PUBLIC_AUTH_SOCIAL_PROVIDERS ?? "")
  .split(",")
  .map((provider) => provider.trim())
  .filter((provider): provider is "google" | "github" => provider === "google" || provider === "github");
export const neonAuthClient = createAuthClient();

export async function completeNeonAuthentication() {
  // OAuth returns with a one-time verifier in the callback URL. `getSession()`
  // exchanges that verifier for the signed, first-party session cookie before
  // we ask Neon for the JWT that our API validates.
  const { data: session, error: sessionError } = await neonAuthClient.getSession();
  if (sessionError || !session?.user) {
    throw new Error(sessionError?.message ?? "Your verified account session could not be opened.");
  }
  // Fetch the JWT directly after the verifier exchange. Calling the SDK's
  // `token()` immediately can reuse its fresh session cache rather than
  // reaching the JWT endpoint.
  const tokenResponse = await fetch("/api/auth/token", {
    credentials: "include",
    headers: { "X-Force-Fetch": "true" },
  });
  const tokenPayload = (await tokenResponse.json().catch(() => null)) as
    | { token?: string; message?: string }
    | null;
  if (!tokenResponse.ok || !tokenPayload?.token) {
    throw new Error(tokenPayload?.message ?? "Your verified account session could not be opened.");
  }
  return api.exchangeNeonSession(tokenPayload.token);
}

export async function signOutEverywhere() {
  await Promise.allSettled([api.logout(), neonAuthEnabled ? neonAuthClient.signOut() : null]);
}
