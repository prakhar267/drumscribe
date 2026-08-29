import type { Metadata } from "next";
import { Brand } from "@/components/brand";
import { MagicLinkConsumer } from "@/components/magic-link-consumer";

export const metadata: Metadata = { title: "Verify sign-in", robots: { index: false, follow: false } };

export default async function VerifyPage({ searchParams }: { searchParams: Promise<{ token?: string }> }) {
  const { token } = await searchParams;
  return <main className="auth-page" id="main-content"><section className="auth-art"><Brand /><div className="auth-quote"><blockquote>One link. No password. Back to the music.</blockquote><p>Secure email sign-in</p></div></section><section className="auth-panel"><MagicLinkConsumer token={token} /></section></main>;
}
