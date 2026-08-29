"use client";

import Link from "next/link";
import { CheckCircle2, LoaderCircle, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

export function MagicLinkConsumer({ token }: { token?: string }) {
  const [state, setState] = useState<"loading" | "ready" | "error">(token ? "loading" : "error");
  useEffect(() => {
    if (!token) return;
    let active = true;
    void api.consumeMagicLink(token).then(() => { if (active) setState("ready"); }).catch(() => { if (active) setState("error"); });
    return () => { active = false; };
  }, [token]);
  return (
    <div className="auth-form" role="status">
      {state === "loading" && <><LoaderCircle className="spin" size={36} color="var(--lime)" /><h1>Signing you in…</h1><p>Verifying your one-time link and attaching any anonymous project to your account.</p></>}
      {state === "ready" && <><CheckCircle2 size={36} color="var(--lime)" /><h1>You’re signed in.</h1><p>Your projects are ready, including work you started before signing in.</p><Link className="button button-primary" href="/projects">Open projects</Link></>}
      {state === "error" && <><XCircle size={36} color="var(--danger)" /><h1>This link isn’t valid.</h1><p>Magic links expire after 15 minutes and can only be used once.</p><Link className="button button-primary" href="/auth">Request a new link</Link></>}
    </div>
  );
}
