import type { Metadata } from "next";
import Link from "next/link";
import { ChevronLeft } from "lucide-react";
import { AccountSettings } from "@/components/account-settings";
import { AppTopbar } from "@/components/app-topbar";

export const metadata: Metadata = { title: "Account settings", robots: { index: false, follow: false } };

export default function AccountSettingsPage() {
  return <div className="app-shell"><AppTopbar /><main className="page-shell" id="main-content"><div className="page-heading"><div><p className="eyebrow">Account</p><h1>Settings</h1></div><Link className="button button-small" href="/projects"><ChevronLeft size={15} /> Projects</Link></div><AccountSettings /></main></div>;
}
