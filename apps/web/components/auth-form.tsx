"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, CheckCircle2, KeyRound } from "lucide-react";
import { api } from "@/lib/api/client";
import {
  completeNeonAuthentication,
  getNeonAuthClient,
  neonAuthEnabled,
  neonAuthSocialProviders,
} from "@/lib/auth/client";

function LegacyMagicLinkForm() {
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
      <p>Sign in with a private email link to claim one complete song free. Your anonymous project comes with you.</p>
      <form onSubmit={(event) => { event.preventDefault(); if (!email) return; setSending(true); setError(null); setDevToken(null); void api.requestMagicLink(email).then((result) => { setDevToken(result.devToken ?? null); setSent(true); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "We couldn’t send that link.")).finally(() => setSending(false)); }}>
        <div className="field"><label htmlFor="email">Email address</label><input className="text-input" id="email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" required /></div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={sending}>{sending ? "Sending securely…" : "Email me a sign-in link"} {!sending && <ArrowRight size={16} />}</button>
      </form>
      <LegalNote />
    </div>
  );
}

type AuthMode = "sign-in" | "sign-up" | "reset";

function NeonAccountForm({ verified }: { verified: boolean }) {
  const router = useRouter();
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const finish = async () => {
    await completeNeonAuthentication();
    router.replace("/projects");
    router.refresh();
  };

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      if (mode === "reset") {
        const authClient = await getNeonAuthClient();
        const { error: resetError } = await authClient.requestPasswordReset({
          email,
          redirectTo: `${window.location.origin}/auth/reset-password`,
        });
        if (resetError) throw new Error(resetError.message || "Password reset could not be sent.");
        setSent(true);
        return;
      }
      if (mode === "sign-up") {
        const authClient = await getNeonAuthClient();
        const { error: signUpError } = await authClient.signUp.email({
          name: name.trim(),
          email,
          password,
          callbackURL: `${window.location.origin}/auth?verified=1`,
        });
        if (signUpError) throw new Error(signUpError.message || "Account creation failed.");
        setSent(true);
        return;
      }
      const authClient = await getNeonAuthClient();
      const { error: signInError } = await authClient.signIn.email({
        email,
        password,
        rememberMe: true,
      });
      if (signInError) throw new Error(signInError.message || "Sign-in failed.");
      await finish();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Sign-in could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const socialSignIn = async (provider: "google" | "github") => {
    setBusy(true);
    setError(null);
    try {
      const authClient = await getNeonAuthClient();
      const { error: socialError } = await authClient.signIn.social({
        provider,
        callbackURL: `${window.location.origin}/auth/complete`,
        newUserCallbackURL: `${window.location.origin}/auth/complete`,
        errorCallbackURL: `${window.location.origin}/auth?social=failed`,
      });
      if (socialError) {
        throw new Error(socialError.message || `${provider} sign-in could not be started.`);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${provider} sign-in could not be started.`);
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <div className="auth-form" role="status">
        <CheckCircle2 size={36} color="var(--lime)" />
        <h1>Check your inbox once.</h1>
        <p>{mode === "reset" ? "Use the password-reset email we sent" : "Verify your new account using the email we sent"} to <strong style={{ color: "var(--paper)" }}>{email}</strong>.</p>
        <p>After verification, future sign-ins use your password—no repeated login links.</p>
        <button className="button" type="button" onClick={() => { setSent(false); setMode("sign-in"); }}>Back to sign in</button>
      </div>
    );
  }

  return (
    <div className="auth-form">
      <p className="eyebrow">Your DrumToScore account</p>
      <h1>{mode === "sign-up" ? "Create your account." : mode === "reset" ? "Reset your password." : "Welcome back."}</h1>
      <p>{mode === "sign-up" ? "Save your projects and claim one complete song free." : mode === "reset" ? "We’ll send one secure reset email." : "Use your password or continue with a trusted account."}</p>
      {verified && mode === "sign-in" && <p className="form-success" role="status">Email verified. Sign in with the password you chose.</p>}

      {mode !== "reset" && neonAuthSocialProviders.length > 0 && (
        <>
          <div className="auth-social-grid">
            {neonAuthSocialProviders.includes("google") && <button className="button auth-social-button" type="button" disabled={busy} onClick={() => void socialSignIn("google")}><span className="auth-provider-letter" aria-hidden="true">G</span> Continue with Google</button>}
            {neonAuthSocialProviders.includes("github") && <button className="button auth-social-button" type="button" disabled={busy} onClick={() => void socialSignIn("github")}><span className="auth-provider-letter" aria-hidden="true">GH</span> Continue with GitHub</button>}
          </div>
          <div className="auth-divider"><span>or use email</span></div>
        </>
      )}

      <form onSubmit={(event) => { event.preventDefault(); void submit(); }}>
        {mode === "sign-up" && <div className="field"><label htmlFor="auth-name">Name</label><input className="text-input" id="auth-name" type="text" value={name} onChange={(event) => setName(event.target.value)} placeholder="Your name" autoComplete="name" minLength={2} maxLength={100} required /></div>}
        <div className="field"><label htmlFor="auth-email">Email address</label><input className="text-input" id="auth-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" autoComplete="email" required /></div>
        {mode !== "reset" && <div className="field"><label htmlFor="auth-password">Password</label><input className="text-input" id="auth-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" autoComplete={mode === "sign-up" ? "new-password" : "current-password"} minLength={8} maxLength={128} required /></div>}
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-primary" type="submit" disabled={busy}>{busy ? "Working securely…" : mode === "sign-up" ? "Create account" : mode === "reset" ? "Send reset email" : "Sign in"} {!busy && <ArrowRight size={16} />}</button>
      </form>

      <div className="auth-mode-actions">
        {mode === "sign-in" && <><button type="button" onClick={() => { setMode("reset"); setError(null); }}><KeyRound size={14} /> Forgot password?</button><button type="button" onClick={() => { setMode("sign-up"); setError(null); }}>Create account</button></>}
        {mode !== "sign-in" && <button type="button" onClick={() => { setMode("sign-in"); setError(null); }}>Already have an account? Sign in</button>}
      </div>
      <LegalNote />
    </div>
  );
}

function LegalNote() {
  return <p className="auth-note">By continuing, you agree to the <a href="/legal/terms" style={{ color: "var(--paper)" }}>Terms</a> and acknowledge the <a href="/legal/privacy" style={{ color: "var(--paper)" }}>Privacy Policy</a>.</p>;
}

export function AuthForm({ verified = false }: { verified?: boolean }) {
  return neonAuthEnabled ? <NeonAccountForm verified={verified} /> : <LegacyMagicLinkForm />;
}
