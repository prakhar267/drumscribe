import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Refund policy" };

export default function RefundsPage() {
  return <LegalPage title="Refund policy" updated="12 September 2026" intro="Credit packs are digital services and are generally final sale once purchased. This strict no-change-of-mind policy does not remove refunds or remedies required by law or the merchant of record." sections={[
    { title: "Before payment", paragraphs: ["The checkout page identifies Dodo Payments as merchant of record and shows the final price, transaction currency, applicable taxes and purchase terms. Do not complete a purchase if those details are missing or incorrect."] },
    { title: "Credits and processing failures", paragraphs: ["The intended paid offer is a one-time pack of ten transcription credits, not a recurring subscription. One credit is reserved when a new song starts processing. Retrying the same job does not use another credit, and a failed or cancelled processing job returns the reserved credit automatically."] },
    { title: "No change-of-mind refunds", paragraphs: ["Except where an exception below or mandatory law applies, purchases are final and we do not refund unused credits, a change of mind, accidental failure to cancel a transcription before it begins, or dissatisfaction that results only from the disclosed limitations of machine-generated transcription. Starting or completing a transcription uses the associated credit."] },
    { title: "When a refund may be available", paragraphs: ["Contact support@drumtoscore.com if you were charged twice, did not receive purchased credits, believe a charge was unauthorized, or the paid service was materially defective or materially different from its description and we could not correct it. Refunds are also provided when required by applicable law or Dodo Payments’ terms. Never email complete card details.", "Include the account email, merchant order reference, purchase date and a short description. Dodo Payments processes approved refunds to the original payment method. Processing time depends on the payment method and network."] },
    { title: "Consumer rights", paragraphs: ["Nothing in this policy limits a refund, cancellation, chargeback or other remedy that applicable law requires. Region-specific digital-service consent and cancellation wording must be reviewed before international paid launch."] },
    { title: "Operator and current status", paragraphs: ["DrumToScore is a trade name used by Prakhar Gupta, an individual sole proprietor at 25/38 Kaveri Path, Mansarovar, Jaipur, Rajasthan 302020, India. The Operator is currently not registered for GST. Dodo Payments live configuration is staged, but public production checkout remains disabled while its review is pending."] },
  ]} />;
}
