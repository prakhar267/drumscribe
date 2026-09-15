import { withSentryConfig } from "@sentry/nextjs";
import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  turbopack: {
    // pnpm keeps the shared virtual store at the monorepo root.
    root: path.resolve(process.cwd(), "../.."),
  },
  experimental: {
    optimizePackageImports: ["lucide-react"],
    turbopackFileSystemCacheForDev: false,
  },
  async headers() {
    return [
      ...["/projects/:path*", "/jobs/:path*", "/settings/:path*", "/auth/:path*", "/upload", "/admin/:path*"].map((source) => ({
        source,
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow, noarchive" }],
      })),
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), geolocation=(), usb=()" },
        ],
      },
    ];
  },
  async rewrites() {
    if (!process.env.API_ORIGIN) return [];
    return [{ source: "/api/v1/:path*", destination: `${process.env.API_ORIGIN}/api/v1/:path*` }];
  },
};

export default withSentryConfig(nextConfig, {
  org: "prakharorg",
  project: "drumscribe-web",
  authToken: process.env.SENTRY_AUTH_TOKEN,
  silent: !process.env.CI,
  webpack: {
    treeshake: {
      removeDebugLogging: true,
    },
  },
});
