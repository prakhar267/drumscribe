import type { Metadata } from "next";
import { cookies } from "next/headers";
import { AdminDashboard } from "@/components/admin-dashboard";
import { Brand } from "@/components/brand";
import { verifyAdminToken } from "@/lib/admin-auth";

export const metadata: Metadata = { title: "Internal pipeline debugger", robots: { index: false, follow: false } };

export default async function AdminPage({ searchParams }: { searchParams: Promise<{ error?: string }> }) {
  const cookieStore = await cookies();
  const authorized = verifyAdminToken(cookieStore.get("ds_admin_session")?.value);
  if (authorized) return <AdminDashboard />;
  const { error } = await searchParams;
  const configured = Boolean(process.env.ADMIN_UI_KEY);
  return (
    <main className="centered-page" id="main-content">
      <Brand />
      <p className="eyebrow">Restricted</p>
      <h1>Internal access only.</h1>
      <p className="muted">Pipeline traces may contain sensitive operational details. This screen requires a server-side UI key, an HttpOnly session, and an account with the API ADMIN role.</p>
      {!configured ? <div className="notice">Admin access is disabled until ADMIN_UI_KEY is configured on the server.</div> : <form action="/api/admin/session" method="post" style={{ display: "grid", gap: 12, width: "min(100%, 380px)" }}><label className="field"><span className="field-label">Admin access key</span><input className="text-input" type="password" name="key" autoComplete="current-password" required /></label>{error && <p className="form-error">That key was not accepted.</p>}<button className="button button-primary" type="submit">Open debugger</button></form>}
    </main>
  );
}
