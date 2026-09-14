import type { Metadata } from "next";
import { AuthCompleter } from "@/components/auth-completer";
import { Brand } from "@/components/brand";

export const metadata: Metadata = { title: "Completing sign in", robots: { index: false, follow: false } };

export default function CompleteAuthPage() {
  return (
    <main className="auth-page" id="main-content">
      <section className="auth-art">
        <Brand />
        <div className="auth-quote"><blockquote>One account. Every chart.</blockquote><p>Secure account connection</p></div>
      </section>
      <section className="auth-panel"><AuthCompleter /></section>
    </main>
  );
}
