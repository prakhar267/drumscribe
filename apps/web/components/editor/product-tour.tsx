"use client";

import Link from "next/link";
import { ArrowLeft, ArrowRight, Check, CirclePlay, Download, Sparkles, X } from "lucide-react";
import { useEffect } from "react";

const TOUR_STEPS = [
  {
    eyebrow: "The AI first draft",
    title: "Audio becomes readable notation.",
    body: "A prepared, rights-safe recording is loaded for this tour. DrumToScore has already separated the drums, found the pulse and placed every detected hit on the score.",
    detail: "Waveform and notation share one playhead",
  },
  {
    eyebrow: "Confidence review",
    title: "Attention goes where it matters.",
    body: "Review mode surfaces quieter or ambiguous hits instead of pretending every prediction is certain. Confirm a note, change its instrument, or move straight to the next one.",
    detail: "Lower-confidence hits queued for review",
  },
  {
    eyebrow: "Drummer-first editing",
    title: "Correct the groove, not a spreadsheet.",
    body: "Add, move, duplicate, quantize or delete hits directly on instrument lanes. The engraved score updates with every edit, and undo is always available.",
    detail: "Kick, snare, toms, hi-hat and cymbals",
  },
  {
    eyebrow: "Practice mode",
    title: "Turn the chart into a rehearsal tool.",
    body: "Loop a difficult measure, slow the song down and blend the original recording, isolated drums and metronome while the notation follows along.",
    detail: "Synchronized audio, loop and score",
  },
  {
    eyebrow: "Ready for your workflow",
    title: "Export a chart you can keep editing.",
    body: "Take the corrected result to rehearsal, a DAW or another notation app. Export PDF, MIDI, MusicXML or the structured event data.",
    detail: "PDF · MIDI · MusicXML · JSON",
  },
] as const;

type ProductTourProps = {
  projectId: string;
  step: number;
  uncertainCount: number;
  onClose: () => void;
  onStepChange: (step: number) => void;
  onExport: () => void;
};

export function ProductTour({ projectId, step, uncertainCount, onClose, onStepChange, onExport }: ProductTourProps) {
  const item = TOUR_STEPS[step];
  const lastStep = step === TOUR_STEPS.length - 1;

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <aside className="product-tour" aria-label="DrumToScore product tour" data-testid="product-tour">
      <div className="product-tour-progress" aria-label={`Step ${step + 1} of ${TOUR_STEPS.length}`}>
        {TOUR_STEPS.map((tourStep, index) => (
          <button
            aria-label={`Go to step ${index + 1}: ${tourStep.eyebrow}`}
            className={index <= step ? "is-complete" : ""}
            key={tourStep.eyebrow}
            onClick={() => onStepChange(index)}
            type="button"
          />
        ))}
      </div>
      <div className="product-tour-topline">
        <span><Sparkles /> Live product tour · about 2 min</span>
        <button aria-label="Close product tour" onClick={onClose} type="button"><X /></button>
      </div>
      <p className="product-tour-eyebrow">{String(step + 1).padStart(2, "0")} · {item.eyebrow}</p>
      <h2>{item.title}</h2>
      <p className="product-tour-copy">{item.body}</p>
      <div className="product-tour-detail"><Check /> {step === 1 ? `${uncertainCount} lower-confidence hits queued` : item.detail}</div>

      <div className="product-tour-footer">
        <span>{step + 1} / {TOUR_STEPS.length}</span>
        <div>
          {step > 0 && (
            <button className="product-tour-back" onClick={() => onStepChange(step - 1)} type="button">
              <ArrowLeft /> Back
            </button>
          )}
          {step === 3 && (
            <Link className="product-tour-action" href={`/projects/${projectId}/practice`}>
              <CirclePlay /> Open practice
            </Link>
          )}
          {lastStep ? (
            <button className="product-tour-action" onClick={onExport} type="button" data-testid="tour-export">
              <Download /> See exports
            </button>
          ) : (
            <button className="product-tour-action" onClick={() => onStepChange(step + 1)} type="button" data-testid="tour-next">
              Next <ArrowRight />
            </button>
          )}
        </div>
      </div>
    </aside>
  );
}
