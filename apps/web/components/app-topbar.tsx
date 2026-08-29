import Link from "next/link";
import { Bell, Settings } from "lucide-react";
import { Brand } from "@/components/brand";

export function AppTopbar() {
  return (
    <header className="app-topbar">
      <Brand />
      <nav className="app-topbar-actions" aria-label="Account">
        <Link className="icon-button" href="/settings/account" aria-label="Settings"><Settings /></Link>
        <button className="icon-button" type="button" aria-label="Notifications"><Bell /></button>
        <Link className="avatar" href="/settings/account" aria-label="Open account settings">PD</Link>
      </nav>
    </header>
  );
}
