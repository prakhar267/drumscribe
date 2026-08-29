import Link from "next/link";
import { Brand } from "@/components/brand";

export default function NotFound() {
  return (
    <main className="centered-page" id="main-content">
      <Brand />
      <p className="eyebrow">404 · Lost the beat</p>
      <h1>That page isn’t in this arrangement.</h1>
      <p className="muted">The project may have moved or been deleted.</p>
      <Link className="button button-primary" href="/projects">Back to projects</Link>
    </main>
  );
}
