import Link from "next/link";
import { Brand } from "@/components/brand";

export function SiteFooter() {
  return (
    <footer className="site-footer">
      <div>
        <Brand />
        <p>© 2026 DrumScribe. Built for the practice room.</p>
      </div>
      <nav className="footer-links" aria-label="Legal">
        <Link href="/legal/privacy">Privacy</Link>
        <Link href="/legal/terms">Terms</Link>
        <Link href="/legal/copyright">Upload policy</Link>
        <Link href="/settings/account">Account</Link>
      </nav>
    </footer>
  );
}
