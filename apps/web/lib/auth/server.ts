type NeonAuth = ReturnType<
  (typeof import("@neondatabase/auth/next/server"))["createNeonAuth"]
>;

let instancePromise: Promise<NeonAuth> | null = null;

export async function getNeonAuth() {
  const baseUrl = process.env.NEON_AUTH_BASE_URL;
  const secret = process.env.NEON_AUTH_COOKIE_SECRET;
  if (!baseUrl || !secret || secret.length < 32) return null;
  if (!instancePromise) {
    // Vinext bundles every route into one Cloudflare Worker. Importing the
    // Neon server SDK in module scope can initialize async runtime state before
    // a request exists, which Workers reject. Load it inside the handler path.
    instancePromise = import("@neondatabase/auth/next/server").then(({ createNeonAuth }) =>
      createNeonAuth({
        baseUrl,
        cookies: { secret, sessionDataTtl: 300 },
        logLevel: process.env.NODE_ENV === "production" ? "warn" : "debug",
      }),
    );
  }
  return instancePromise;
}
