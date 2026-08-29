"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api/client";

export function AuthForm() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  if (sent) {
    return (
      <div className="auth-form" role="status">
        <CheckCircle2 size={36} color="var(--lime)" />
        <h1>Check your inbox.</h1>
        <p>We sent a secure sign-in link to <strong style={{ color: "var(--paper)" }}>{email}</strong>. It expires in 15 minutes.</p>
        {devToken && <div className="notice"><span><strong>Local development shortcut</strong><br />Email delivery is disabled in this environment.</span><Link className="button button-primary button-small" href={`/auth/verify?token=${encodeURIComponent(devToken)}`}>Continue sign-in</Link></div>}
        <button className="button" type="button" onClick={() => setSent(false)}>Use another email</button>
      </div>
    );
  }
  return (
    <div className="auth-form">
      <p className="eyebrow">Save your work</p>
      <h1>Pick up where you left off.</h1>
      <p>Sign in with a magic link. No password to remember, and your anonymous project comes with you.</p>
      <form onSubmit={(event) => { event.preventDefault(); if (!email) return; setSending(true); setError(null); setDevToken(null); void api.requestMagicLink(email).then((result) => { setDevToken(result.devToken ?? null); setSent(true); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "We couldn’t send that link.")).finally(() => setSending(false)); }}>
        <div className="field"><label htmlFor="email">Email address</label><input className="text-input" id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" required /></div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={sending}>{sending ? "Sending securely…" : "Email me a sign-in link"} {!sending && <ArrowRight size={16} />}</button>
      </form>
      <p className="auth-note">By continuing, you agree to the <a href="/legal/terms" style={{ color: "var(--paper)" }}>Terms</a> and acknowledge the <a href="/legal/privacy" style={{ color: "var(--paper)" }}>Privacy Policy</a>.</p>
    </div>
  );
}
