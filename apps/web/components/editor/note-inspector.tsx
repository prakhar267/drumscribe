"use client";

import { AlertCircle, Crosshair, MousePointer2, WandSparkles } from "lucide-react";
import { INSTRUMENT_LABELS, INSTRUMENTS, type DrumEvent, type Instrument } from "@/lib/domain";
import { formatTime } from "@/lib/file-validation";

export function NoteInspector({ selected, uncertainCount, onChange, onReviewNext, onDelete }: {
  selected: DrumEvent[];
  uncertainCount: number;
  onChange: (changes: Partial<Pick<DrumEvent, "instrument" | "velocity">>) => void;
  onReviewNext: () => void;
  onDelete: () => void;
}) {
  const event = selected[0];
  if (!event) {
    return (
      <aside className="note-inspector" aria-label="Selection inspector">
        <div className="inspector-empty">
          <MousePointer2 />
          <h2>Select a note</h2>
          <p>Click a hit in the score or grid to adjust its drum, timing and velocity.</p>
        </div>
        <div className="review-card">
          <span className="review-icon"><Crosshair /></span>
          <div><strong>{uncertainCount} notes to review</strong><p>Jump through the least certain parts of this chart.</p></div>
          <button className="button button-small" type="button" onClick={onReviewNext} disabled={!uncertainCount} data-testid="review-next">Review next</button>
        </div>
      </aside>
    );
  }
  return (
    <aside className="note-inspector" aria-label="Selected note properties">
      <div className="inspector-header">
        <div><p className="eyebrow">{selected.length > 1 ? `${selected.length} notes` : "Selected note"}</p><h2>{selected.length > 1 ? "Multiple hits" : INSTRUMENT_LABELS[event.instrument]}</h2></div>
        <span className="source-badge"><WandSparkles /> {event.source === "MODEL" ? "Generated" : "Manual"}</span>
      </div>
      <div className="inspector-fields">
        <label className="field"><span className="field-label">Instrument</span><select className="select-input" value={event.instrument} onChange={(change) => onChange({ instrument: change.target.value as Instrument })}>{INSTRUMENTS.map((instrument) => <option value={instrument} key={instrument}>{INSTRUMENT_LABELS[instrument]}</option>)}</select></label>
        <div className="inspector-split"><div><span className="field-label">Position</span><strong>M{event.measureIndex + 1} · {(event.beatPosition + 1).toFixed(2)}</strong></div><div><span className="field-label">Time</span><strong>{formatTime(event.quantizedOnset)}</strong></div></div>
        <label className="field"><span className="field-label">Velocity <output>{event.velocity}</output></span><input className="velocity-slider" type="range" min="1" max="127" value={event.velocity} onChange={(change) => onChange({ velocity: Number(change.target.value) })} data-testid="velocity-slider" /></label>
        <div className="confidence-row"><span><AlertCircle /> Model confidence</span><span className={event.confidence < 0.7 ? "confidence-low" : ""}>{event.confidence < 0.7 ? "Needs a listen" : "Likely right"}</span></div>
      </div>
      <button className="button button-danger button-small" type="button" onClick={onDelete}>Delete {selected.length > 1 ? "notes" : "note"}</button>
      <p className="inspector-tip">Tip: use arrow keys to nudge by the current snap value. Shift-click selects more than one hit.</p>
    </aside>
  );
}
