import type { Metadata } from "next";
import { LegalPage } from "@/components/legal-page";

export const metadata: Metadata = { title: "Terms" };

export default function TermsPage() {
  return <LegalPage title="Terms of use" updated="29 August 2026" intro="These draft terms explain the intended relationship between DrumScribe and its users. They are not final legal terms and require counsel review before public launch." sections={[
    { title: "The service", paragraphs: ["DrumScribe creates an editable first draft of a drum transcription from audio you provide. Generated results can be incomplete or inaccurate and must be reviewed before use."] },
    { title: "Your account and projects", paragraphs: ["You are responsible for activity under your account and for maintaining access to your sign-in email. Projects are private unless a future sharing feature is explicitly enabled by you."] },
    { title: "Acceptable use", paragraphs: ["Do not upload audio you are not authorized to process, attempt to access another person’s project, probe the service for vulnerabilities, or use the service to distribute infringing material."] },
    { title: "Ownership", paragraphs: ["You retain rights you hold in uploaded materials and edits. The service receives only the limited permissions needed to store, process and return those materials to you."] },
    { title: "Disclaimers and liability", paragraphs: ["Service availability, warranty, limitation-of-liability, dispute-resolution, governing-law, termination and age-eligibility language must be finalized by qualified counsel before launch."] },
  ]} />;
}
