import type { Metadata } from "next";
import { Suspense } from "react";
import { Brand } from "@/components/brand";
import { PasswordResetForm } from "@/components/password-reset-form";

export const metadata: Metadata = { title: "Reset password", robots: { index: false, follow: false } };

export default function ResetPasswordPage() {
  return (
    <main className="auth-page" id="main-content">
      <section className="auth-art"><Brand /><div className="auth-quote"><blockquote>Back to your charts.</blockquote><p>Secure account recovery</p></div></section>
      <section className="auth-panel"><Suspense fallback={<div className="auth-form"><p>Loading…</p></div>}><PasswordResetForm /></Suspense></section>
    </main>
  );
}
