import "server-only";
import { createHmac, timingSafeEqual } from "node:crypto";

const MESSAGE = "drumscribe-admin-session-v1";

export function adminToken() {
  const secret = process.env.ADMIN_UI_KEY;
  if (!secret) return null;
  return createHmac("sha256", secret).update(MESSAGE).digest("hex");
}

export function verifyAdminToken(value?: string) {
  const expected = adminToken();
  if (!expected || !value || expected.length !== value.length) return false;
  return timingSafeEqual(Buffer.from(expected), Buffer.from(value));
}
