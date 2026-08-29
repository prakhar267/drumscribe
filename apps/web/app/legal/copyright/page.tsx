import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Copyright & uploads" };

export default function CopyrightPage() {
  return <LegalPage title="Copyright & upload policy" updated="29 August 2026" intro="DrumScribe is a private tool for audio the customer is entitled to process. It does not download from streaming platforms, host a public score catalogue, or automatically publish generated charts." sections={[
    { title: "Your confirmation", paragraphs: ["Before processing, you must confirm that you have the right to upload and process the audio. This may be because you created it, licensed it, received permission, or another applicable legal basis permits your use."] },
    { title: "What is not allowed", paragraphs: ["Do not upload recordings when you lack the necessary rights. Do not use DrumScribe to scrape, redistribute, publicly catalogue, or sell copyrighted recordings or sheet music without authorization."], bullets: ["No YouTube, Spotify or streaming-service downloads", "No searchable public library of user transcriptions", "No automatic publication of generated scores"] },
    { title: "Private processing and deletion", paragraphs: ["Projects stay private. You can delete a project and its audio from Settings; storage lifecycle jobs then remove the associated assets according to the disclosed recovery period."] },
    { title: "Rights-holder process", paragraphs: ["A verified copyright contact, notice-and-action procedure, repeat-infringer policy, counter-notice process and jurisdiction-specific safe-harbour language must be supplied by counsel before launch."] },
  ]} />;
}
