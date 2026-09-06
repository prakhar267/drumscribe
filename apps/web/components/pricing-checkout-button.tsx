"use client";

import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Account } from "@/lib/api/client";

const BILLING_ENABLED = process.env.NEXT_PUBLIC_BILLING_ENABLED === "true";

export function PricingCheckoutButton() {
  const [account, setAccount] = useState<Account | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void api.getAccount()
      .then((next) => { if (active) setAccount(next); })
      .catch(() => undefined)
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  if (!BILLING_ENABLED) {
    return (
      <>
        <span className="button button-primary is-disabled" aria-disabled="true">Secure checkout is being activated</span>
        <p className="pricing-checkout-note">Purchases open as soon as Merchant-of-Record verification is complete.</p>
      </>
    );
  }
  if (loading) return <span className="button button-primary is-disabled" aria-disabled="true">Checking account…</span>;
  if (account?.kind !== "REGISTERED") {
    return <Link className="button button-primary" href="/auth">Sign in to buy credits <ArrowRight size={16} /></Link>;
  }
  return (
    <>
      <button
        className="button button-primary"
        type="button"
        disabled={starting}
        onClick={() => {
          setStarting(true);
          setError(null);
          void api.createCreditCheckout()
            .then(({ checkoutUrl }) => { window.location.assign(checkoutUrl); })
            .catch((reason: unknown) => {
              setError(reason instanceof Error ? reason.message : "Secure checkout could not be started.");
              setStarting(false);
            });
        }}
      >
        {starting ? "Opening secure checkout…" : "Buy 10 credits securely"}
        {!starting && <ArrowRight size={16} />}
      </button>
      {error && <p className="form-error pricing-checkout-error" role="alert">{error}</p>}
    </>
  );
}
