"use client";

import { useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { CheckCircle2 } from "lucide-react";
import { neonAuthClient } from "@/lib/auth/client";

export function PasswordResetForm() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (done) {
    return (
      <div className="auth-form" role="status">
        <CheckCircle2 size={36} color="var(--lime)" />
        <h1>Password updated.</h1>
        <p>You can now sign in normally with your new password.</p>
        <Link className="button button-primary" href="/auth">Sign in</Link>
      </div>
    );
  }

  return (
    <div className="auth-form">
      <p className="eyebrow">Account recovery</p>
      <h1>Choose a new password.</h1>
      <p>Use at least 8 characters and avoid reusing a password from another service.</p>
      <form onSubmit={(event) => { event.preventDefault(); setBusy(true); setError(null); void neonAuthClient.resetPassword({ newPassword: password, token }).then(({ error: resetError }) => { if (resetError) throw new Error(resetError.message || "Password reset failed."); setDone(true); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Password reset failed.")).finally(() => setBusy(false)); }}>
        <div className="field"><label htmlFor="new-password">New password</label><input className="text-input" id="new-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" minLength={8} maxLength={128} required /></div>
        {!token && <p className="form-error" role="alert">This password-reset link is incomplete. Request a new one.</p>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={busy || !token}>{busy ? "Updating securely…" : "Update password"}</button>
      </form>
      <Link href="/auth" style={{ color: "var(--lime)" }}>Back to sign in</Link>
    </div>
  );
}
