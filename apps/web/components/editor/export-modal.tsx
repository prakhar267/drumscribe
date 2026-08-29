"use client";

import { Download, FileCode2, FileMusic, FileText, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";
import type { DrumEvent, DrumProject } from "@/lib/domain";
import { eventsToMidi, eventsToMusicXml } from "@/lib/music";

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 500);
}

export function ExportModal({ project, events, beforeExport, onClose }: { project: DrumProject; events: DrumEvent[]; beforeExport: () => Promise<void>; onClose: () => void }) {
  const [generating, setGenerating] = useState<"midi" | "musicxml" | "pdf" | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const keydown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [onClose]);

  const slug = project.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  const download = async (format: "midi" | "musicxml" | "pdf") => {
    setGenerating(format);
    setError(null);
    try {
      await beforeExport();
      const url = await api.generateExport(project.id, format === "musicxml" ? "MUSICXML" : format.toUpperCase() as "MIDI" | "PDF");
      if (url) {
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.rel = "noopener";
        anchor.click();
      } else if (format === "midi") {
        downloadBlob(new Blob([eventsToMidi(events, project.bpm) as BlobPart], { type: "audio/midi" }), `${slug}.mid`);
      } else if (format === "musicxml") {
        downloadBlob(new Blob([eventsToMusicXml(events, { title: project.title, bpm: project.bpm, beatsPerMeasure: project.beatsPerMeasure, durationSeconds: project.durationSeconds })], { type: "application/vnd.recordare.musicxml+xml" }), `${slug}.musicxml`);
      } else {
        window.print();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The export could not be generated.");
    } finally {
      setGenerating(null);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose(); }}>
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="export-title" data-testid="export-modal">
        <header className="modal-header"><div><h2 id="export-title">Export latest chart</h2><p>Exports include every saved correction in the current version.</p></div><button className="icon-button" type="button" onClick={onClose} aria-label="Close export"><X /></button></header>
        <div className="modal-body">
          <button className="export-option" type="button" disabled={generating !== null} onClick={() => void download("pdf")}><span className="export-icon"><FileText /></span><span><strong>{generating === "pdf" ? "Generating PDF…" : "Printable PDF"}</strong><span>Clean notation with title, tempo and page numbers</span></span><Download size={17} /></button>
          <button className="export-option" type="button" disabled={generating !== null} onClick={() => void download("midi")} data-testid="export-midi"><span className="export-icon"><FileMusic /></span><span><strong>{generating === "midi" ? "Generating MIDI…" : "MIDI"}</strong><span>General MIDI percussion, ready for a DAW</span></span><Download size={17} /></button>
          <button className="export-option" type="button" disabled={generating !== null} onClick={() => void download("musicxml")}><span className="export-icon"><FileCode2 /></span><span><strong>{generating === "musicxml" ? "Generating MusicXML…" : "MusicXML 4.0"}</strong><span>Editable in major notation applications</span></span><Download size={17} /></button>
          {error && <p className="form-error" role="alert">{error}</p>}
          <div className="notice"><span>Large PDF exports may continue in the background when connected to the production service.</span></div>
        </div>
      </section>
    </div>
  );
}
