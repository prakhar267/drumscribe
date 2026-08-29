"use client";

import {
  Gauge,
  LocateFixed,
  MousePointer2,
  Plus,
  RotateCcw,
  Save,
  Trash2,
} from "lucide-react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { useMemo, useRef, useState } from "react";
import { api } from "@/lib/api/client";
import type {
  DrumProject,
  RequantizeMode,
  TimingBeat,
  TimingMap,
  TimingSegment,
} from "@/lib/domain";

interface TimingEditorProps {
  project: DrumProject;
  timing: TimingMap;
  peaks: number[] | null;
  currentTime: number;
  onSeek: (time: number) => void;
  onApplied: (timing: TimingMap) => Promise<void>;
}

type TimingSaveState = "idle" | "saving" | "saved" | "error";

function clamp(value: number, minimum: number, maximum: number) {
  return Math.max(minimum, Math.min(maximum, value));
}

function segmentAt(segments: TimingSegment[], time: number) {
  return [...segments]
    .reverse()
    .find((segment) => segment.startSeconds <= time) ?? segments[0];
}

function buildBeatGrid(
  segments: TimingSegment[],
  duration: number,
): TimingBeat[] {
  const output: TimingBeat[] = [];
  const ordered = [...segments].sort((a, b) => a.startSeconds - b.startSeconds);
  ordered.forEach((segment, segmentIndex) => {
    const end = ordered[segmentIndex + 1]?.startSeconds ?? duration;
    const beatDuration = 60 / segment.bpm * 4 / segment.timeSignatureDenominator;
    let index = 0;
    for (
      let time = segment.startSeconds;
      time <= end + 0.000001 && output.length < 50_000;
      time = segment.startSeconds + ++index * beatDuration
    ) {
      const beatInMeasure = index % segment.timeSignatureNumerator + 1;
      if (output.some((beat) => Math.abs(beat.timeSeconds - time) < 0.000001)) continue;
      output.push({
        timeSeconds: Number(time.toFixed(6)),
        beatInMeasure,
        measureIndex: segment.startMeasure + Math.floor(index / segment.timeSignatureNumerator),
        isDownbeat: beatInMeasure === 1,
        confidence: null,
      });
    }
  });
  return output;
}

function relabelBeats(beats: TimingBeat[], segments: TimingSegment[]) {
  return [...beats]
    .sort((a, b) => a.timeSeconds - b.timeSeconds)
    .map((beat) => {
      const segment = segmentAt(segments, beat.timeSeconds);
      const segmentBeats = beats.filter(
        (candidate) =>
          candidate.timeSeconds >= segment.startSeconds &&
          candidate.timeSeconds <= beat.timeSeconds,
      ).length - 1;
      const beatInMeasure = segmentBeats % segment.timeSignatureNumerator + 1;
      return {
        ...beat,
        beatInMeasure,
        measureIndex: segment.startMeasure + Math.floor(segmentBeats / segment.timeSignatureNumerator),
        isDownbeat: beatInMeasure === 1,
        confidence: null,
      };
    });
}

function signatureLabel(segment: TimingSegment) {
  return `${segment.timeSignatureNumerator}/${segment.timeSignatureDenominator}`;
}

export function TimingEditor({
  project,
  timing,
  peaks,
  currentTime,
  onSeek,
  onApplied,
}: TimingEditorProps) {
  const [segments, setSegments] = useState<TimingSegment[]>(timing.segments);
  const [beats, setBeats] = useState<TimingBeat[]>(timing.beats);
  const [barOne, setBarOne] = useState(timing.barOneSeconds);
  const [selectedBeat, setSelectedBeat] = useState<number | null>(null);
  const [draggingBeat, setDraggingBeat] = useState<number | null>(null);
  const [requantize, setRequantize] = useState<RequantizeMode>("all");
  const [measureStart, setMeasureStart] = useState(1);
  const [measureEnd, setMeasureEnd] = useState(4);
  const [preserveManual, setPreserveManual] = useState(true);
  const [saveState, setSaveState] = useState<TimingSaveState>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const [taps, setTaps] = useState<number[]>([]);
  const timelineRef = useRef<HTMLDivElement>(null);

  const activeSegment = useMemo(
    () => segmentAt(segments, currentTime),
    [currentTime, segments],
  );
  const selected = selectedBeat === null ? null : beats[selectedBeat] ?? null;

  const realign = (nextSegments = segments, nextBarOne = barOne) => {
    const normalizedSegments = nextSegments.map((segment, index) =>
      index === 0 ? { ...segment, startSeconds: nextBarOne, startMeasure: 0 } : segment,
    );
    setSegments(normalizedSegments);
    setBeats(buildBeatGrid(normalizedSegments, project.durationSeconds));
    setSelectedBeat(null);
    setSaveState("idle");
    setMessage("Grid realigned. Save timing to update notation.");
  };

  const updatePrimarySegment = (changes: Partial<TimingSegment>) => {
    const next = segments.map((segment, index) =>
      index === 0 ? { ...segment, ...changes } : segment,
    );
    setSegments(next);
    setSaveState("idle");
  };

  const setBarOneHere = () => {
    const nextBarOne = clamp(currentTime, 0, project.durationSeconds);
    setBarOne(nextBarOne);
    realign(segments, nextBarOne);
    setMessage(`Bar 1 set at ${nextBarOne.toFixed(3)} seconds.`);
  };

  const tapTempo = () => {
    const now = performance.now();
    const recent = taps.length && now - taps[taps.length - 1] < 2_500 ? [...taps, now] : [now];
    const bounded = recent.slice(-6);
    setTaps(bounded);
    if (bounded.length < 2) {
      setMessage("Keep tapping the beat…");
      return;
    }
    const intervals = bounded.slice(1).map((value, index) => value - bounded[index]);
    const bpm = clamp(60_000 / (intervals.reduce((sum, value) => sum + value, 0) / intervals.length), 20, 400);
    const next = segments.map((segment, index) =>
      index === 0 ? { ...segment, bpm: Number(bpm.toFixed(2)) } : segment,
    );
    setSegments(next);
    setMessage(`${bpm.toFixed(1)} BPM from ${bounded.length} taps. Realign when ready.`);
  };

  const addTempoChange = () => {
    const nearest = [...beats]
      .filter((beat) => beat.isDownbeat)
      .sort((a, b) => Math.abs(a.timeSeconds - currentTime) - Math.abs(b.timeSeconds - currentTime))[0];
    const startSeconds = nearest?.timeSeconds ?? currentTime;
    if (segments.some((segment) => Math.abs(segment.startSeconds - startSeconds) < 0.001)) {
      setMessage("A tempo section already starts at this measure.");
      return;
    }
    const next = [
      ...segments,
      {
        ...activeSegment,
        startSeconds,
        startMeasure: nearest?.measureIndex ?? 0,
      },
    ].sort((a, b) => a.startSeconds - b.startSeconds);
    setSegments(next);
    setSaveState("idle");
    setMessage(`Tempo change added at measure ${(nearest?.measureIndex ?? 0) + 1}.`);
  };

  const insertBeat = () => {
    const next = relabelBeats(
      [
        ...beats,
        {
          timeSeconds: clamp(currentTime, barOne, project.durationSeconds),
          beatInMeasure: 1,
          measureIndex: 0,
          isDownbeat: false,
          confidence: null,
        },
      ],
      segments,
    );
    setBeats(next);
    setSelectedBeat(next.findIndex((beat) => Math.abs(beat.timeSeconds - currentTime) < 0.001));
    setSaveState("idle");
  };

  const deleteBeat = () => {
    if (selectedBeat === null || beats.length <= 2) return;
    if (beats[selectedBeat]?.isDownbeat && beats[selectedBeat]?.timeSeconds === barOne) {
      setMessage("Bar 1 cannot be deleted. Set a new bar 1 first.");
      return;
    }
    setBeats(relabelBeats(beats.filter((_, index) => index !== selectedBeat), segments));
    setSelectedBeat(null);
    setSaveState("idle");
  };

  const moveSelectedToPlayhead = () => {
    if (selectedBeat === null) return;
    const selectedItem = beats[selectedBeat];
    if (
      selectedItem?.isDownbeat &&
      Math.abs(selectedItem.timeSeconds - barOne) < 0.001
    ) {
      setMessage("Use Set Bar 1 Here to move the first downbeat.");
      return;
    }
    const next = beats.map((beat, index) =>
      index === selectedBeat
        ? { ...beat, timeSeconds: clamp(currentTime, barOne, project.durationSeconds) }
        : beat,
    );
    setBeats(relabelBeats(next, segments));
    setSelectedBeat(null);
    setSaveState("idle");
  };

  const dragBeat = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (draggingBeat === null || !timelineRef.current) return;
    const bounds = timelineRef.current.getBoundingClientRect();
    const time = clamp(
      ((event.clientX - bounds.left) / bounds.width) * project.durationSeconds,
      barOne,
      project.durationSeconds,
    );
    setBeats((current) =>
      current.map((beat, index) =>
        index === draggingBeat ? { ...beat, timeSeconds: Number(time.toFixed(4)) } : beat,
      ),
    );
  };

  const beginBeatDrag = (index: number) => {
    const beat = beats[index];
    if (
      beat?.isDownbeat &&
      Math.abs(beat.timeSeconds - barOne) < 0.001
    ) {
      setMessage("Use Set Bar 1 Here to move the first downbeat.");
      return;
    }
    setDraggingBeat(index);
    setSelectedBeat(index);
  };

  const endBeatDrag = () => {
    if (draggingBeat === null) return;
    setBeats((current) => relabelBeats(current, segments));
    setDraggingBeat(null);
    setSelectedBeat(null);
    setSaveState("idle");
  };

  const save = async () => {
    setSaveState("saving");
    setMessage(null);
    try {
      const result = await api.updateTiming(project.id, {
        expectedVersion: timing.timingVersion,
        barOneSeconds: barOne,
        segments,
        beats,
        requantize,
        measureStart: requantize === "selected" ? measureStart - 1 : undefined,
        measureEnd: requantize === "selected" ? measureEnd - 1 : undefined,
        preserveManualEdits: preserveManual,
      });
      await onApplied(result);
      setSaveState("saved");
      setMessage(
        `Timing saved. ${result.requantizedEventCount} model hit${result.requantizedEventCount === 1 ? "" : "s"} remapped; raw onsets preserved.`,
      );
    } catch (error) {
      setSaveState("error");
      setMessage(error instanceof Error ? error.message : "Timing could not be saved.");
    }
  };

  const reset = async () => {
    setSaveState("saving");
    try {
      const result = await api.resetTiming(project.id, {
        expectedVersion: timing.timingVersion,
        requantize,
        measureStart: requantize === "selected" ? measureStart - 1 : undefined,
        measureEnd: requantize === "selected" ? measureEnd - 1 : undefined,
        preserveManualEdits: preserveManual,
      });
      await onApplied(result);
      setSaveState("saved");
      setMessage("AI timing restored. Manual hit edits were preserved.");
    } catch (error) {
      setSaveState("error");
      setMessage(error instanceof Error ? error.message : "AI timing could not be restored.");
    }
  };

  return (
    <section className="timing-mode" aria-label="Timing editor">
      <header className="timing-mode-header">
        <div>
          <span className={`timing-source source-${timing.source.toLowerCase()}`}>
            {timing.source === "AI" ? "AI timing" : "Manually corrected"}
          </span>
          <h2>Align the musical grid to the recording</h2>
          <p>Move beats and tempo sections without changing any raw drum-hit timestamp.</p>
        </div>
        <div className="timing-header-actions">
          <button className="button button-small" type="button" onClick={() => void reset()} disabled={saveState === "saving"}>
            <RotateCcw size={14} /> Reset to AI timing
          </button>
          <button className="button button-primary button-small" type="button" onClick={() => void save()} disabled={saveState === "saving"}>
            <Save size={14} /> {saveState === "saving" ? "Saving…" : "Save timing"}
          </button>
        </div>
      </header>

      <div className="timing-layout">
        <div className="timing-canvas-panel">
          <div className="timing-readout">
            <span><strong>{activeSegment.bpm.toFixed(1)}</strong> BPM</span>
            <span><strong>{signatureLabel(activeSegment)}</strong> meter</span>
            <span><strong>{beats.filter((beat) => beat.isDownbeat).length}</strong> measures</span>
            <span><strong>{barOne.toFixed(3)}s</strong> bar 1</span>
          </div>
          <div
            className="timing-timeline"
            ref={timelineRef}
            onPointerMove={dragBeat}
            onPointerUp={endBeatDrag}
            onPointerCancel={endBeatDrag}
            onDoubleClick={(event) => {
              const bounds = event.currentTarget.getBoundingClientRect();
              onSeek(((event.clientX - bounds.left) / bounds.width) * project.durationSeconds);
            }}
          >
            <div className="timing-waveform" aria-hidden="true">
              {(peaks ?? []).map((height, index) => (
                <i key={index} style={{ height: `${Math.max(4, height * 78)}%` }} />
              ))}
              {!peaks?.length && <span>Waveform data unavailable</span>}
            </div>
            {segments.map((segment, index) => (
              <span
                className="tempo-section-marker"
                key={`${segment.startSeconds}-${index}`}
                style={{ left: `${(segment.startSeconds / project.durationSeconds) * 100}%` }}
              >
                {segment.bpm.toFixed(1)} · {signatureLabel(segment)}
              </span>
            ))}
            {beats.map((beat, index) => (
              <button
                className={`timing-beat${beat.isDownbeat ? " is-downbeat" : ""}${selectedBeat === index ? " is-selected" : ""}`}
                key={`${beat.timeSeconds}-${index}`}
                style={{ left: `${(beat.timeSeconds / project.durationSeconds) * 100}%` }}
                type="button"
                aria-label={`${beat.isDownbeat ? "Downbeat" : "Beat"} ${beat.beatInMeasure}, measure ${beat.measureIndex + 1}, ${beat.timeSeconds.toFixed(3)} seconds`}
                onClick={() => {
                  setSelectedBeat(index);
                  onSeek(beat.timeSeconds);
                }}
                onPointerDown={(event) => {
                  event.currentTarget.setPointerCapture(event.pointerId);
                  beginBeatDrag(index);
                }}
              >
                {beat.isDownbeat && <span>{beat.measureIndex + 1}</span>}
              </button>
            ))}
            <span
              className="timing-playhead"
              style={{ left: `${(currentTime / project.durationSeconds) * 100}%` }}
            />
          </div>
          <p className="timing-help"><MousePointer2 size={13} /> Drag beat markers. Double-click the waveform to move the playhead.</p>

          <div className="timing-quick-actions">
            <button type="button" onClick={setBarOneHere}><LocateFixed /> Set Bar 1 Here</button>
            <button type="button" onClick={tapTempo}><Gauge /> Tap Tempo</button>
            <button type="button" onClick={() => realign()}><RotateCcw /> Realign Grid</button>
            <button type="button" onClick={addTempoChange}><Plus /> Add Tempo Change</button>
            <button type="button" onClick={insertBeat}><Plus /> Insert Beat</button>
            <button type="button" onClick={deleteBeat} disabled={selectedBeat === null}><Trash2 /> Delete Beat</button>
          </div>
        </div>

        <aside className="timing-inspector">
          <div className="timing-control-section">
            <span className="field-label">Primary timing</span>
            <div className="timing-field-grid">
              <label>
                <span>BPM</span>
                <input type="number" min="20" max="400" step="0.1" value={segments[0].bpm} onChange={(event) => updatePrimarySegment({ bpm: clamp(Number(event.target.value), 20, 400) })} />
              </label>
              <label>
                <span>Time signature</span>
                <select
                  value={signatureLabel(segments[0])}
                  onChange={(event) => {
                    const [numerator, denominator] = event.target.value.split("/").map(Number);
                    updatePrimarySegment({ timeSignatureNumerator: numerator, timeSignatureDenominator: denominator });
                  }}
                >
                  <option value="4/4">4/4</option>
                  <option value="3/4">3/4</option>
                  <option value="6/8">6/8</option>
                  <option value="12/8">12/8</option>
                </select>
              </label>
            </div>
            <button className="button button-small" type="button" onClick={() => realign()}>Apply BPM & meter to grid</button>
          </div>

          <div className="timing-control-section">
            <span className="field-label">Selected beat</span>
            {selected ? (
              <>
                <div className="timing-selected-readout">
                  <strong>M{selected.measureIndex + 1} · beat {selected.beatInMeasure}</strong>
                  <span>{selected.timeSeconds.toFixed(4)} seconds</span>
                </div>
                <button className="button button-small" type="button" onClick={moveSelectedToPlayhead}>Move beat to playhead</button>
              </>
            ) : <p>Select or drag a beat marker to correct it.</p>}
          </div>

          <div className="timing-control-section">
            <span className="field-label">After timing changes</span>
            <label className="timing-stack-field">
              <span>Requantize</span>
              <select value={requantize} onChange={(event) => setRequantize(event.target.value as RequantizeMode)}>
                <option value="all">All measures</option>
                <option value="selected">Selected measures</option>
                <option value="none">Timing only</option>
              </select>
            </label>
            {requantize === "selected" && (
              <div className="timing-field-grid">
                <label><span>From measure</span><input type="number" min="1" value={measureStart} onChange={(event) => setMeasureStart(Math.max(1, Number(event.target.value)))} /></label>
                <label><span>To measure</span><input type="number" min={measureStart} value={measureEnd} onChange={(event) => setMeasureEnd(Math.max(measureStart, Number(event.target.value)))} /></label>
              </div>
            )}
            <label className="timing-checkbox">
              <input type="checkbox" checked={preserveManual} onChange={(event) => setPreserveManual(event.target.checked)} />
              <span>Preserve manually edited hits</span>
            </label>
          </div>

          {message && <p className={`timing-message${saveState === "error" ? " is-error" : ""}`} role={saveState === "error" ? "alert" : "status"}>{message}</p>}
        </aside>
      </div>
    </section>
  );
}
