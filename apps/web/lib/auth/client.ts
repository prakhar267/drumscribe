"use client";

import { api } from "@/lib/api/client";

type NeonAuthClient = ReturnType<
  (typeof import("@neondatabase/auth/next"))["createAuthClient"]
>;

export const neonAuthEnabled = process.env.NEXT_PUBLIC_AUTH_PROVIDER === "neon";
export const neonAuthSocialProviders = (process.env.NEXT_PUBLIC_AUTH_SOCIAL_PROVIDERS ?? "")
  .split(",")
  .map((provider) => provider.trim())
  .filter((provider): provider is "google" | "github" => provider === "google" || provider === "github");

let clientPromise: Promise<NeonAuthClient> | null = null;

/**
 * Create the browser SDK only when an auth action actually runs. Cloudflare
 * Workers forbid random-number generation and asynchronous I/O in module
 * scope, both of which the SDK may perform during construction.
 */
export async function getNeonAuthClient() {
  if (!clientPromise) {
    clientPromise = import("@neondatabase/auth/next").then(({ createAuthClient }) =>
      createAuthClient(),
    );
  }
  return clientPromise;
}

export async function completeNeonAuthentication() {
  // OAuth returns with a one-time verifier in the callback URL. `getSession()`
  // exchanges that verifier for the signed, first-party session cookie before
  // we ask Neon for the JWT that our API validates.
  const authClient = await getNeonAuthClient();
  const { data: session, error: sessionError } = await authClient.getSession();
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
  const neonSignOut = neonAuthEnabled
    ? getNeonAuthClient().then((authClient) => authClient.signOut())
    : null;
  await Promise.allSettled([api.logout(), neonSignOut]);
}

export async function deleteAccountEverywhere() {
  // Delete the product account first, then clear both authentication layers.
  // Otherwise a still-valid Neon browser session can immediately recreate the
  // deleted identity on the next OAuth attempt.
  await api.deleteAccount();
  await signOutEverywhere();
}
