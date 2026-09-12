const requiredValues = new Map([
  ["NEXT_PUBLIC_API_URL", "/api/v1"],
  ["NEXT_PUBLIC_DEMO_MODE", "false"],
  ["NEXT_PUBLIC_APP_ENV", "production"],
]);

const failures = [];

for (const [name, expected] of requiredValues) {
  const actual = process.env[name];
  if (actual !== expected) {
    failures.push(`${name} must be ${JSON.stringify(expected)}`);
  }
}

const apiOrigin = process.env.API_ORIGIN;
if (!apiOrigin) {
  failures.push("API_ORIGIN is required");
} else {
  try {
    const parsed = new URL(apiOrigin);
    if (parsed.protocol !== "https:" || parsed.pathname !== "/") {
      failures.push("API_ORIGIN must be an HTTPS origin without a path");
    }
  } catch {
    failures.push("API_ORIGIN must be a valid absolute URL");
  }
}

if (!["true", "false"].includes(process.env.NEXT_PUBLIC_BILLING_ENABLED ?? "")) {
  failures.push("NEXT_PUBLIC_BILLING_ENABLED must be explicitly true or false");
}

for (const name of ["NEXT_PUBLIC_SENTRY_DSN", "SENTRY_DSN"]) {
  if (!process.env[name]) failures.push(`${name} is required`);
}

if (failures.length) {
  console.error("Refusing production web deployment:\n- " + failures.join("\n- "));
  process.exit(1);
}

console.log("Production web deployment environment is complete.");
