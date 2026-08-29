import Link from "next/link";
import { Brand } from "@/components/brand";

interface Section { title: string; paragraphs: string[]; bullets?: string[] }

export function LegalPage({ title, updated, intro, sections }: { title: string; updated: string; intro: string; sections: Section[] }) {
  return (
    <main className="legal-shell" id="main-content">
      <aside className="legal-aside"><Brand /><Link href="/">← Back home</Link><Link href="/legal/privacy">Privacy policy</Link><Link href="/legal/terms">Terms</Link><Link href="/legal/copyright">Copyright & uploads</Link></aside>
      <article className="legal-content"><p className="eyebrow">Legal · Updated {updated}</p><h1>{title}</h1><span className="legal-review">Draft placeholder · final legal review required before launch</span><p>{intro}</p>{sections.map((section) => <section key={section.title}><h2>{section.title}</h2>{section.paragraphs.map((paragraph) => <p key={paragraph}>{paragraph}</p>)}{section.bullets && <ul>{section.bullets.map((bullet) => <li key={bullet}>{bullet}</li>)}</ul>}</section>)}</article>
    </main>
  );
}
