import * as Sentry from "@sentry/nextjs";

const dsn = process.env.NEXT_PUBLIC_SENTRY_DSN;
const configuredSampleRate = Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? "0.05");
const tracesSampleRate = Number.isFinite(configuredSampleRate)
  ? Math.min(1, Math.max(0, configuredSampleRate))
  : 0.05;

Sentry.init({
  dsn,
  enabled: Boolean(dsn) && process.env.NODE_ENV === "production",
  environment: process.env.NEXT_PUBLIC_APP_ENV ?? process.env.NODE_ENV,
  sendDefaultPii: false,
  tracesSampleRate,
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
