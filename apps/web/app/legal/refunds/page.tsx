import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Refund policy" };

export default function RefundsPage() {
  return <LegalPage title="Refund policy" updated="10 September 2026" intro="DrumToScore checkout is currently disabled, so the service is not accepting payment. This pre-launch policy records how credits and refund requests are intended to work once a merchant-of-record checkout is enabled." sections={[
    { title: "Before payment", paragraphs: ["The checkout page must identify the merchant of record, final price, transaction currency, applicable taxes and the refund or cancellation terms that govern the purchase. Do not complete a purchase if those details are missing or incorrect."] },
    { title: "Credits and processing failures", paragraphs: ["The intended paid offer is a one-time pack of ten transcription credits, not a recurring subscription. One credit is reserved when a new song starts processing. Retrying the same job does not use another credit, and a failed or cancelled processing job returns the reserved credit automatically."] },
    { title: "Requesting a refund", paragraphs: ["For an accidental or duplicate purchase, a technical failure that prevents use of the purchased service, or another billing problem, contact support@drumtoscore.com with the account email, merchant order reference, purchase date and a short description. Never email complete card details.", "The merchant of record will process approved refunds to the original payment method under the terms shown at checkout. Processing time depends on the merchant and payment network. No refund window or discretionary eligibility rule is final until merchant onboarding and legal review are complete."] },
    { title: "Consumer rights", paragraphs: ["Nothing in this policy limits a refund, cancellation, chargeback or other remedy that applicable law requires. Region-specific digital-service consent and cancellation wording must be reviewed before international paid launch."] },
    { title: "Current status", paragraphs: ["Production billing remains disabled. This page must be updated with the merchant’s legal name, support route, final currency, refund window and effective date before the first paid transaction."] },
  ]} />;
}
