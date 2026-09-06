"use client";

import Link from "next/link";
import { CheckCircle2, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

export function BillingSuccess() {
  const [credits, setCredits] = useState<number | null>(null);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    let active = true;
    let attempt = 0;
    const check = async () => {
      try {
        const account = await api.getAccount();
        if (!active) return;
        if (account.paidCredits > 0) {
          setCredits(account.paidCredits);
          setChecking(false);
          return;
        }
      } catch {
        // The verified webhook can still arrive while the confirmation page waits.
      }
      attempt += 1;
      if (active && attempt < 10) window.setTimeout(() => { void check(); }, 1500);
      else if (active) setChecking(false);
    };
    void check();
    return () => { active = false; };
  }, []);

  return (
    <div className="billing-success-card surface">
      {credits !== null ? <CheckCircle2 className="billing-success-icon" /> : <LoaderCircle className={checking ? "billing-success-icon spin" : "billing-success-icon"} />}
      <p className="eyebrow">Payment confirmation</p>
      <h1>{credits !== null ? "Credits added." : checking ? "Confirming your payment…" : "Payment is still confirming."}</h1>
      <p>{credits !== null ? `Your account now has ${credits} paid transcription credits.` : "Credits are granted only after DrumScribe receives a signed confirmation from the payment provider. This normally takes a few seconds."}</p>
      <div className="hero-actions">
        <Link className="button button-primary" href="/upload">Transcribe a song</Link>
        <Link className="button" href="/settings/account">Check account balance</Link>
      </div>
    </div>
  );
}
