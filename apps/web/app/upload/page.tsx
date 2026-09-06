import type { Metadata } from "next";
import Link from "next/link";
import { UploadForm } from "@/components/upload-form";
import { SiteHeader } from "@/components/site-header";

export const metadata: Metadata = { title: "Upload a recording", robots: { index: false, follow: false } };

export default function UploadPage() {
  return (
    <>
      <SiteHeader />
      <main className="page-shell" id="main-content">
        <div className="page-heading">
          <div><p className="eyebrow">New transcription</p><h1>Bring the song.<br />We’ll find the drums.</h1></div>
          <p>Try a short preview without an account, or sign in to claim one complete song free. After that, each new song uses one credit. <Link href="/legal/copyright" style={{ color: "var(--lime)" }}>Upload policy</Link></p>
        </div>
        <UploadForm />
      </main>
    </>
  );
}
