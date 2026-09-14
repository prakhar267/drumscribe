"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { CheckCircle2, LoaderCircle, XCircle } from "lucide-react";
import { completeNeonAuthentication } from "@/lib/auth/client";

export function AuthCompleter() {
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void completeNeonAuthentication()
      .then(() => window.location.replace("/projects"))
      .catch((reason: unknown) => {
        setError(reason instanceof Error ? reason.message : "The account session could not be opened.");
      });
  }, []);

  return (
    <div className="auth-form" role="status">
      {error ? (
        <>
          <XCircle size={36} color="var(--danger)" />
          <h1>Sign-in needs another try.</h1>
          <p>{error}</p>
          <Link className="button button-primary" href="/auth">Back to sign in</Link>
        </>
      ) : (
        <>
          <LoaderCircle className="spin" size={36} color="var(--lime)" />
          <h1>Opening your projects…</h1>
          <p>Your verified account is being connected to the work you started here.</p>
          <span className="sr-only"><CheckCircle2 /> Account verification in progress</span>
        </>
      )}
    </div>
  );
}
