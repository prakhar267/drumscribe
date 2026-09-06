import type { Metadata } from "next";
import { BillingSuccess } from "@/components/billing-success";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Payment confirmation", robots: { index: false, follow: false } };

export default function BillingSuccessPage() {
  return (
    <>
      <SiteHeader />
      <main className="billing-success-page" id="main-content"><BillingSuccess /></main>
    </>
  );
}
