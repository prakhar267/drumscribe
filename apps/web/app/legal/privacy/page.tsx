import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Privacy policy" };

export default function PrivacyPage() {
  return <LegalPage title="Privacy policy" updated="29 August 2026" intro="DrumScribe is designed around private musical work. This draft describes the intended data practices and must be reviewed by qualified counsel for every launch jurisdiction." sections={[
    { title: "What we collect", paragraphs: ["We collect account details, private project metadata, uploaded audio, generated drum stems, transcriptions, edits, exports, and limited service telemetry needed to operate and secure the product."] },
    { title: "How audio is used", paragraphs: ["Audio is processed only to provide the features you request. Projects are private, are not indexed, and are not used for model training unless you separately opt in. The model-improvement preference defaults to off."] },
    { title: "Storage and deletion", paragraphs: ["Customer audio is stored in private object storage and accessed through short-lived signed links. Temporary processing assets and abandoned anonymous uploads follow configurable lifecycle deletion. Project and account deletion controls are available in Settings."] },
    { title: "Your choices", paragraphs: ["You may request a data export, disable optional analytics, decline model-improvement participation, delete a project, or permanently delete your account."], bullets: ["No public project gallery", "No raw audio or filenames in analytics", "No sale of customer audio", "No automatic model training from uploads"] },
    { title: "Contact", paragraphs: ["A verified privacy contact, controller identity, processor list, international-transfer language, retention schedule, and jurisdiction-specific rights must be added before public launch."] },
  ]} />;
}
