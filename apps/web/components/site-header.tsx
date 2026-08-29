"use client";

import Link from "next/link";
import { Menu, X } from "lucide-react";
import { useState } from "react";
import { Brand } from "@/components/brand";

export function SiteHeader() {
  const [open, setOpen] = useState(false);
  return (
    <header className="site-header">
      <div className="site-header-inner">
        <Brand />
        <nav className={open ? "site-nav is-open" : "site-nav"} aria-label="Main navigation">
          <Link href="/projects" onClick={() => setOpen(false)}>Projects</Link>
          <Link href="/#how-it-works" onClick={() => setOpen(false)}>How it works</Link>
          <Link href="/auth" onClick={() => setOpen(false)}>Sign in</Link>
          <Link className="button button-small button-primary" href="/upload" onClick={() => setOpen(false)}>Transcribe a song</Link>
        </nav>
        <button className="nav-toggle" type="button" onClick={() => setOpen((value) => !value)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
          {open ? <X /> : <Menu />}
        </button>
      </div>
    </header>
  );
}
