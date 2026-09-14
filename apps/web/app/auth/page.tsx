import type { Metadata } from "next";
import { AuthForm } from "@/components/auth-form";
import { Brand } from "@/components/brand";

export const metadata: Metadata = { title: "Sign in", robots: { index: false, follow: false } };

export default async function AuthPage({
  searchParams,
}: {
  searchParams: Promise<{ verified?: string }>;
}) {
  const verified = (await searchParams).verified === "1";
  return (
    <main className="auth-page" id="main-content">
      <section className="auth-art">
        <Brand />
        <div className="auth-quote">
          <blockquote>“The chart gets you close. Your ears finish the job.”</blockquote>
          <p>DrumToScore product principle</p>
        </div>
      </section>
      <section className="auth-panel"><AuthForm verified={verified} /></section>
    </main>
  );
}
