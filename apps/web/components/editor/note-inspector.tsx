"use client";

import { AlertCircle, Crosshair, SlidersHorizontal, Trash2, WandSparkles, X } from "lucide-react";
import { useState } from "react";
import { INSTRUMENT_LABELS, INSTRUMENTS, type DrumEvent, type Instrument, type NotationSubdivision } from "@/lib/domain";
import { formatTime } from "@/lib/file-validation";

const SUBDIVISIONS: NotationSubdivision[] = ["1/8", "1/16", "1/32", "1/8T"];

export function NoteInspector({ selected, uncertainCount, reviewMode, onChange, onReviewNext, onDelete, onClose }: {
  selected: DrumEvent[];
  uncertainCount: number;
  reviewMode: boolean;
  onChange: (changes: Partial<Pick<DrumEvent, "instrument" | "velocity" | "subdivision">>) => void;
  onReviewNext: () => void;
  onDelete: () => void;
  onClose: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const event = selected[0];
  if (!event) {
    if (!reviewMode) return null;
    return (
      <aside className="note-inspector note-inspector-review" aria-label="AI review">
        <div className="review-card">
          <span className="review-icon"><Crosshair /></span>
          <div><strong>{uncertainCount} notes to review</strong><p>Jump through the least certain parts of this chart.</p></div>
          <button className="button button-small" type="button" onClick={onReviewNext} disabled={!uncertainCount} data-testid="review-next">Review next</button>
        </div>
      </aside>
    );
  }
  return (
    <aside className={`note-inspector note-inspector-floating${expanded ? " is-expanded" : ""}`} aria-label="Selected note properties">
      <div className="subdivision-picker" aria-label="Note value">
        {SUBDIVISIONS.map((subdivision) => <button className={event.subdivision === subdivision ? "is-active" : ""} type="button" key={subdivision} onClick={() => onChange({ subdivision })}>{subdivision.replace("T", " triplet")}</button>)}
      </div>
      <div className="inspector-compact-summary">
        <div><strong>{selected.length > 1 ? `${selected.length} notes` : INSTRUMENT_LABELS[event.instrument]}</strong><span>M{event.measureIndex + 1} · {(event.beatPosition + 1).toFixed(2)} · {formatTime(event.quantizedOnset)}</span></div>
        <button type="button" aria-label={expanded ? "Hide detailed note properties" : "Show detailed note properties"} aria-expanded={expanded} onClick={() => setExpanded((value) => !value)}><SlidersHorizontal /></button>
        <button type="button" aria-label="Close note properties" onClick={onClose}><X /></button>
      </div>
      {expanded && <>
        <div className="inspector-expanded-meta"><span className="source-badge"><WandSparkles /> {event.source === "MODEL" ? "Generated" : "Manual"}</span><span>{selected.length > 1 ? `${selected.length} selected hits` : "Canonical drum event"}</span></div>
        <div className="inspector-fields">
          <label className="field inspector-instrument"><span className="field-label">Instrument</span><select className="select-input" value={event.instrument} onChange={(change) => onChange({ instrument: change.target.value as Instrument })}>{INSTRUMENTS.map((instrument) => <option value={instrument} key={instrument}>{INSTRUMENT_LABELS[instrument]}</option>)}</select></label>
          <div className="inspector-split"><div><span className="field-label">Position</span><strong>M{event.measureIndex + 1} · {(event.beatPosition + 1).toFixed(2)}</strong></div><div><span className="field-label">Time</span><strong>{formatTime(event.quantizedOnset)}</strong></div></div>
          <label className="field"><span className="field-label">Velocity <output>{event.velocity}</output></span><input className="velocity-slider" type="range" min="1" max="127" value={event.velocity} onChange={(change) => onChange({ velocity: Number(change.target.value) })} data-testid="velocity-slider" /></label>
          <div className="confidence-row"><span><AlertCircle /> Model confidence</span><span className={event.confidence < 0.7 ? "confidence-low" : ""}>{event.confidence < 0.7 ? "Needs a listen" : "Likely right"}</span></div>
        </div>
        <div className="inspector-footer"><span>Arrow keys nudge · Shift-click adds</span><button type="button" onClick={onDelete}><Trash2 /> Delete</button></div>
      </>}
    </aside>
  );
}
