import Link from "next/link";
import { ArrowRight, PlayCircle } from "lucide-react";
import { HomeDemo } from "@/components/home-demo";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export default function HomePage() {
  return (
    <>
      <SiteHeader />
      <main className="home-main" id="main-content">
        <section className="home-hero">
          <div className="hero-copy">
            <p className="eyebrow">AI-assisted drum transcription</p>
            <h1 className="display-title">Turn any song into an <em>editable</em> drum chart.</h1>
            <div className="hero-lede">
              <div>
                <div className="hero-actions">
                  <Link className="button button-primary" href="/upload">Transcribe a song <ArrowRight size={17} /></Link>
                  <Link className="button" href="/projects/demo-groove"><PlayCircle size={17} /> Try demo</Link>
                </div>
              </div>
              <p>Upload a recording. DrumScribe isolates the drums, detects the groove, creates notation, and lets you correct, practise and export it.</p>
            </div>
          </div>
          <div className="hero-sticker" aria-hidden="true">A strong first draft.<br />You keep the feel.</div>
        </section>

        <HomeDemo />

        <section className="benefits-section" aria-labelledby="benefits-title">
          <h2 className="sr-only" id="benefits-title">Why drummers use DrumScribe</h2>
          <div className="benefit-grid">
            <article className="benefit-item">
              <span className="benefit-number">01</span>
              <h3>Transcribe faster.</h3>
              <p>Start with a useful first draft instead of a blank page, then spend your time on the details that matter.</p>
            </article>
            <article className="benefit-item">
              <span className="benefit-number">02</span>
              <h3>Fix mistakes easily.</h3>
              <p>Move, add, delete and audition hits directly on a drum-first timeline. Every edit can be undone.</p>
            </article>
            <article className="benefit-item">
              <span className="benefit-number">03</span>
              <h3>Practise from the chart.</h3>
              <p>Loop the awkward fill, slow it down, blend the original and drum stem, then bring it back to tempo.</p>
            </article>
          </div>
        </section>

        <section className="workflow-section" id="how-it-works">
          <div>
            <p className="eyebrow">From recording to rehearsal</p>
            <h2 className="section-title">Less charting.<br />More playing.</h2>
          </div>
          <div className="workflow-steps">
            <article className="workflow-step"><span>1</span><div><strong>Drop in your audio</strong><p>MP3, WAV, M4A or FLAC. No account wall before you hear the result.</p></div></article>
            <article className="workflow-step"><span>2</span><div><strong>We build the first draft</strong><p>Drum isolation, hit detection, beat alignment and readable notation work as one pipeline.</p></div></article>
            <article className="workflow-step"><span>3</span><div><strong>Make it yours</strong><p>Review uncertain notes, correct the groove, practise in sync, and export PDF, MIDI or MusicXML.</p></div></article>
          </div>
        </section>

        <section className="home-cta">
          <p className="eyebrow">Your next chart starts here</p>
          <h2>Hear it. See it. Fix it. Play it.</h2>
          <Link className="button" href="/upload">Transcribe a song <ArrowRight size={17} /></Link>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
