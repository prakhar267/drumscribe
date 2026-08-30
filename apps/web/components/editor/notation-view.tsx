"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { INSTRUMENT_LABELS, type DrumEvent, type DrumProject } from "@/lib/domain";
import { eventsToMusicXml } from "@/lib/music";
import { engraveMusicXml, mountSanitizedSvg, sanitizeVerovioSvg } from "@/lib/notation";

type EngravingState =
  | { status: "loading"; source: string }
  | { status: "ready"; source: string; svg: string }
  | { status: "error"; source: string; message: string };

export default function NotationView({ project, events, selectedIds, currentTime, onSelect, onSeek }: {
  project: DrumProject;
  events: DrumEvent[];
  selectedIds: Set<string>;
  currentTime: number;
  onSelect: (id: string, additive: boolean) => void;
  onSeek?: (time: number) => void;
}) {
  const measuresPerPage = 8;
  const measureDuration = project.beatsPerMeasure * 60 / project.bpm;
  const measureCount = Math.max(1, Math.ceil(project.durationSeconds / measureDuration));
  const activeMeasure = Math.min(measureCount - 1, Math.max(0, Math.floor(currentTime / measureDuration)));
  const pageIndex = Math.floor(activeMeasure / measuresPerPage);
  const pageCount = Math.max(1, Math.ceil(measureCount / measuresPerPage));
  const firstMeasure = pageIndex * measuresPerPage;
  const pageMeasureCount = Math.min(measuresPerPage, measureCount - firstMeasure);
  const pageDuration = pageMeasureCount * measureDuration;
  const pageOffset = firstMeasure * measureDuration;
  const playheadPosition = pageDuration > 0
    ? Math.max(0, Math.min(100, (currentTime - pageOffset) / pageDuration * 100))
    : 0;
  const hostRef = useRef<HTMLDivElement>(null);
  const visibleEvents = useMemo(() => events
    .filter((event) => event.measureIndex >= firstMeasure && event.measureIndex < firstMeasure + measuresPerPage)
    .map((event) => ({ ...event, measureIndex: event.measureIndex - firstMeasure })), [events, firstMeasure]);
  const musicXml = useMemo(() => eventsToMusicXml(visibleEvents, {
    title: project.title,
    bpm: project.bpm,
    beatsPerMeasure: project.beatsPerMeasure,
    durationSeconds: pageDuration,
    firstMeasureNumber: firstMeasure + 1,
    systemBreakEvery: 4,
  }), [firstMeasure, pageDuration, project.beatsPerMeasure, project.bpm, project.title, visibleEvents]);
  const descriptors = useMemo(() => visibleEvents.map((event) => ({
    id: event.id,
    label: `${INSTRUMENT_LABELS[event.instrument]} on beat ${(event.beatPosition + 1).toFixed(2)}, measure ${event.measureIndex + firstMeasure + 1}`,
  })), [firstMeasure, visibleEvents]);
  const [engraving, setEngraving] = useState<EngravingState>({ status: "loading", source: "" });

  useEffect(() => {
    let active = true;
    void engraveMusicXml(musicXml, pageMeasureCount).then((svg) => {
      if (!active) return;
      setEngraving({ status: "ready", source: musicXml, svg: sanitizeVerovioSvg(svg, descriptors) });
    }).catch((reason: unknown) => {
      if (!active) return;
      setEngraving({
        status: "error",
        source: musicXml,
        message: reason instanceof Error ? reason.message : "The notation renderer is unavailable.",
      });
    });
    return () => { active = false; };
  }, [descriptors, musicXml, pageMeasureCount]);

  const isCurrent = engraving.source === musicXml;
  const isLoading = !isCurrent || engraving.status === "loading";
  const svg = engraving.status === "ready" ? engraving.svg : undefined;

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !svg) return;
    mountSanitizedSvg(host, svg);
    return () => { host.replaceChildren(); };
  }, [svg]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    host.querySelectorAll<SVGElement>("[data-drumscribe-event-id]").forEach((note) => {
      note.classList.toggle("is-selected", selectedIds.has(note.dataset.drumscribeEventId ?? ""));
    });
    host.querySelectorAll<SVGElement>("[data-measure-index]").forEach((measure) => {
      measure.classList.toggle("is-playing", Number(measure.dataset.measureIndex) === activeMeasure - firstMeasure);
    });
  }, [activeMeasure, firstMeasure, selectedIds, svg]);

  const selectFromTarget = (target: EventTarget | null, additive: boolean) => {
    if (!(target instanceof Element)) return;
    const note = target.closest<SVGElement>("[data-drumscribe-event-id]");
    const id = note?.dataset.drumscribeEventId;
    if (id) onSelect(id, additive);
  };

  return (
    <section className="notation-panel" aria-label="Drum notation" data-testid="notation-view" aria-busy={isLoading}>
      <div className="notation-heading"><span>Drum set</span><span>{project.bpm} BPM · {project.beatsPerMeasure}/4</span></div>
      <div className="notation-scroll">
        <div className="notation-score">
          {isLoading && !svg && <div className="notation-state" role="status"><span className="notation-state-pulse" />Engraving score…</div>}
          {isCurrent && engraving.status === "error" && (
            <div className="notation-state notation-state-error" role="alert">
              <strong>Notation is temporarily unavailable.</strong>
              <span>{engraving.message} Your {events.length} drum hits remain editable in the grid.</span>
            </div>
          )}
          <div
            className={`notation-engraving${isLoading && svg ? " is-refreshing" : ""}`}
            ref={hostRef}
            onClick={(event) => selectFromTarget(event.target, event.shiftKey || event.metaKey || event.ctrlKey)}
            onKeyDown={(event) => {
              if (event.key !== "Enter" && event.key !== " ") return;
              event.preventDefault();
              selectFromTarget(event.target, event.shiftKey || event.metaKey || event.ctrlKey);
            }}
          />
          {svg && <div className="notation-playhead" style={{ left: `${playheadPosition}%` }} aria-hidden="true" />}
        </div>
      </div>
      <footer className="notation-pagination" aria-label="Score page">
        <button type="button" aria-label="Previous score page" disabled={pageIndex === 0} onClick={() => onSeek?.(Math.max(0, pageOffset - pageDuration))}><ChevronLeft /></button>
        <span>Page {pageIndex + 1} of {pageCount}</span>
        <button type="button" aria-label="Next score page" disabled={pageIndex >= pageCount - 1} onClick={() => onSeek?.(Math.min(project.durationSeconds, pageOffset + pageDuration))}><ChevronRight /></button>
      </footer>
    </section>
  );
}
