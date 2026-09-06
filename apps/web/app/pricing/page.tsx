import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check, Music2, ShieldCheck } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { PricingCheckoutButton } from "@/components/pricing-checkout-button";

export const metadata: Metadata = {
  title: "Pricing",
  description: "Transcribe one full song free, then buy 10 DrumScribe transcription credits for $15.",
};

export default function PricingPage() {
  return (
    <>
      <SiteHeader />
      <main className="pricing-page" id="main-content">
        <header className="pricing-hero">
          <p className="eyebrow">Simple, drummer-friendly pricing</p>
          <h1>One song free.<br /><em>Pay only when you need more.</em></h1>
          <p>No subscription at launch. Try the complete workflow, keep your chart, then add credits when your next song is ready.</p>
        </header>

        <section className="pricing-grid" aria-label="DrumScribe pricing plans">
          <article className="surface pricing-card">
            <div className="pricing-card-kicker"><Music2 aria-hidden="true" /> Free</div>
            <h2>First song</h2>
            <p className="pricing-price"><strong>$0</strong><span>once per verified account</span></p>
            <ul>
              <li><Check /> One complete-song transcription</li>
              <li><Check /> Drum isolation and notation</li>
              <li><Check /> Editing and practice tools</li>
              <li><Check /> PDF, MIDI and MusicXML exports</li>
            </ul>
            <Link className="button" href="/auth">Claim your free song <ArrowRight size={16} /></Link>
          </article>

          <article className="surface pricing-card pricing-card-featured">
            <div className="pricing-popular">Best for your next songs</div>
            <div className="pricing-card-kicker"><ShieldCheck aria-hidden="true" /> Credit pack</div>
            <h2>10 transcriptions</h2>
            <p className="pricing-price"><strong>$15</strong><span>one-time payment · $1.50 per song</span></p>
            <ul>
              <li><Check /> Ten new complete-song transcriptions</li>
              <li><Check /> Same full editor, practice and exports</li>
              <li><Check /> No recurring subscription</li>
              <li><Check /> Failed or cancelled jobs return the credit</li>
            </ul>
            <PricingCheckoutButton />
          </article>
        </section>

        <section className="pricing-faq" aria-labelledby="pricing-faq-title">
          <div><p className="eyebrow">Clear rules</p><h2 id="pricing-faq-title">No surprise charges.</h2></div>
          <dl>
            <div><dt>What counts as one credit?</dt><dd>Starting a new song. Retrying the same processing job never uses another credit.</dd></div>
            <div><dt>What if processing fails?</dt><dd>The reserved free use or paid credit is returned automatically when a job fails or is cancelled.</dd></div>
            <div><dt>Is this a subscription?</dt><dd>No. The launch offer is a one-time 10-credit pack.</dd></div>
            <div><dt>Are taxes included?</dt><dd>The secure checkout calculates any applicable tax from the customer’s billing location before payment.</dd></div>
          </dl>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
