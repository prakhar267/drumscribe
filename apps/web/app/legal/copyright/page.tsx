import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Copyright & uploads" };

export default function CopyrightPage() {
  return <LegalPage title="Copyright & upload policy" updated="12 September 2026" intro="DrumToScore is a private processing tool for audio the customer is entitled to use. It does not download from streaming platforms, host a public score catalogue or automatically publish generated charts." sections={[
    { title: "Operator and contact", paragraphs: ["DrumToScore is a trade name used by Prakhar Gupta, an individual sole proprietor at 25/38 Kaveri Path, Mansarovar, Jaipur, Rajasthan 302020, India. Send rights-holder notices to copyright@drumtoscore.com."] },
    { title: "Your confirmation", paragraphs: ["Before processing, you must confirm that you have the right to upload and process the audio. This may be because you created it, licensed it, received permission, or another applicable legal basis permits your use."] },
    { title: "What is not allowed", paragraphs: ["Do not upload recordings when you lack the necessary rights. Do not use DrumToScore to scrape, redistribute, publicly catalogue, or sell copyrighted recordings or sheet music without authorization."], bullets: ["No YouTube, Spotify or streaming-service downloads", "No searchable public library of user transcriptions", "No automatic publication of generated scores"] },
    { title: "Private processing and deletion", paragraphs: ["Projects stay private. You can delete a project and its audio using the product controls; normal access is revoked immediately and storage cleanup follows the recovery period disclosed in the privacy policy."] },
    { title: "Rights-holder notices", paragraphs: ["Send a rights notice to copyright@drumtoscore.com with your name and contact details, identification of the protected work, the DrumToScore material or project involved, why you believe the use is unauthorized, and a statement that the information is accurate and you are the rights holder or authorized to act for them. Do not send the copyrighted recording unless requested.", "Because projects are private, DrumToScore may need enough information to locate the relevant account or project. The service may preserve evidence, restrict access or remove material while reviewing a sufficiently detailed notice."] },
    { title: "Counter-notices and repeat misuse", paragraphs: ["Users should have a fair way to respond to mistaken notices. The formal counter-notice, repeat-infringer and jurisdiction-specific safe-harbour procedures still require counsel approval before paid launch. Until then, disputed material must not be restored or disclosed without documented review."] },
  ]} />;
}
