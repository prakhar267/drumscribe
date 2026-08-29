"use client";

import { memo, useRef, useState } from "react";
import { EDITOR_ROWS, INSTRUMENT_LABELS, type DrumEvent, type Instrument, type SnapValue } from "@/lib/domain";
import { snapSeconds } from "@/lib/music";

const ROW_HEIGHT = 30;

interface Point { x: number; y: number }

export const DrumGrid = memo(function DrumGrid({ events, duration, bpm, beatsPerMeasure, selectedIds, snap, zoom, confidenceOverlay, onAdd, onSelect, onMove }: {
  events: DrumEvent[];
  duration: number;
  bpm: number;
  beatsPerMeasure: number;
  selectedIds: Set<string>;
  snap: SnapValue;
  zoom: number;
  confidenceOverlay: boolean;
  onAdd: (time: number, instrument: Instrument) => void;
  onSelect: (ids: Set<string>) => void;
  onMove: (ids: Set<string>, deltaTime: number, deltaRows: number) => void;
}) {
  const gridRef = useRef<HTMLDivElement>(null);
  const labelTrackRef = useRef<HTMLDivElement>(null);
  const [marquee, setMarquee] = useState<{ start: Point; end: Point } | null>(null);
  const [drag, setDrag] = useState<{ start: Point; ids: Set<string>; dx: number; dy: number } | null>(null);
  const measureDuration = beatsPerMeasure * 60 / bpm;
  const measureCount = Math.ceil(duration / measureDuration);

  const pointFromEvent = (event: React.PointerEvent) => {
    const rect = gridRef.current!.getBoundingClientRect();
    return { x: event.clientX - rect.left, y: event.clientY - rect.top };
  };

  const backgroundDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    const point = pointFromEvent(event);
    setMarquee({ start: point, end: point });
  };

  const backgroundMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (marquee) setMarquee({ ...marquee, end: pointFromEvent(event) });
  };

  const backgroundUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!marquee || !gridRef.current) return;
    const end = pointFromEvent(event);
    const distance = Math.hypot(end.x - marquee.start.x, end.y - marquee.start.y);
    const rect = gridRef.current.getBoundingClientRect();
    if (distance < 6) {
      const time = snapSeconds(end.x / rect.width * duration, bpm, snap);
      const row = Math.max(0, Math.min(EDITOR_ROWS.length - 1, Math.floor(end.y / ROW_HEIGHT)));
      onAdd(time, EDITOR_ROWS[row]);
    } else {
      const left = Math.min(marquee.start.x, end.x);
      const right = Math.max(marquee.start.x, end.x);
      const top = Math.min(marquee.start.y, end.y);
      const bottom = Math.max(marquee.start.y, end.y);
      onSelect(new Set(events.filter((item) => {
        const x = item.quantizedOnset / duration * rect.width;
        const y = (EDITOR_ROWS.indexOf(item.instrument) + 0.5) * ROW_HEIGHT;
        return x >= left && x <= right && y >= top && y <= bottom;
      }).map((item) => item.id)));
    }
    setMarquee(null);
  };

  const hitDown = (event: React.PointerEvent<HTMLButtonElement>, item: DrumEvent) => {
    event.stopPropagation();
    const additive = event.shiftKey || event.metaKey || event.ctrlKey;
    let ids = new Set(selectedIds);
    if (!ids.has(item.id)) ids = additive ? new Set([...ids, item.id]) : new Set([item.id]);
    onSelect(ids);
    event.currentTarget.setPointerCapture(event.pointerId);
    setDrag({ start: { x: event.clientX, y: event.clientY }, ids, dx: 0, dy: 0 });
  };

  const hitMove = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (!drag) return;
    setDrag({ ...drag, dx: event.clientX - drag.start.x, dy: event.clientY - drag.start.y });
  };

  const hitUp = (event: React.PointerEvent<HTMLButtonElement>) => {
    if (!drag || !gridRef.current) return;
    const rect = gridRef.current.getBoundingClientRect();
    if (Math.abs(drag.dx) > 3 || Math.abs(drag.dy) > 3) {
      const rawDelta = drag.dx / rect.width * duration;
      const anchor = events.find((item) => drag.ids.has(item.id));
      const snappedDelta = anchor ? snapSeconds(anchor.quantizedOnset + rawDelta, bpm, snap) - anchor.quantizedOnset : rawDelta;
      onMove(drag.ids, snappedDelta, Math.round(drag.dy / ROW_HEIGHT));
    }
    try { event.currentTarget.releasePointerCapture(event.pointerId); } catch { /* Capture may already be released by the browser. */ }
    setDrag(null);
  };

  const marqueeStyle = marquee ? {
    left: Math.min(marquee.start.x, marquee.end.x),
    top: Math.min(marquee.start.y, marquee.end.y),
    width: Math.abs(marquee.start.x - marquee.end.x),
    height: Math.abs(marquee.start.y - marquee.end.y),
  } : undefined;

  return (
    <section className="grid-panel" aria-label="Drum grid editor">
      <div className="grid-row-labels" aria-hidden="true">
        <div className="grid-row-labels-track" ref={labelTrackRef}>
          {EDITOR_ROWS.map((instrument) => <div key={instrument}>{INSTRUMENT_LABELS[instrument]}</div>)}
        </div>
      </div>
      <div className="grid-scroll" onScroll={(event) => {
        if (labelTrackRef.current) labelTrackRef.current.style.transform = `translateY(-${event.currentTarget.scrollTop}px)`;
      }}>
        <div className="grid-ruler" style={{ width: `${zoom * 100}%` }}>{Array.from({ length: measureCount }, (_, index) => <span key={index} style={{ width: `${100 / measureCount}%` }}>{index + 1}</span>)}</div>
        <div
          className="grid-canvas"
          ref={gridRef}
          style={{ width: `${zoom * 100}%`, height: EDITOR_ROWS.length * ROW_HEIGHT, "--measures": measureCount } as React.CSSProperties}
          onPointerDown={backgroundDown}
          onPointerMove={backgroundMove}
          onPointerUp={backgroundUp}
          data-testid="drum-grid"
        >
          {events.filter((item) => EDITOR_ROWS.includes(item.instrument)).map((item) => {
            const isSelected = selectedIds.has(item.id);
            const isDragging = Boolean(drag?.ids.has(item.id));
            return (
              <button
                className={`grid-hit${isSelected ? " is-selected" : ""}${item.confidence < 0.7 ? " is-uncertain" : ""}`}
                key={item.id}
                type="button"
                style={{
                  left: `${item.quantizedOnset / duration * 100}%`,
                  top: EDITOR_ROWS.indexOf(item.instrument) * ROW_HEIGHT + ROW_HEIGHT / 2,
                  opacity: confidenceOverlay ? Math.max(0.38, item.confidence) : 1,
                  transform: isDragging ? `translate(calc(-50% + ${drag?.dx ?? 0}px), calc(-50% + ${drag?.dy ?? 0}px))` : undefined,
                }}
                onPointerDown={(event) => hitDown(event, item)}
                onPointerMove={hitMove}
                onPointerUp={hitUp}
                aria-label={`${INSTRUMENT_LABELS[item.instrument]} hit at ${item.quantizedOnset.toFixed(2)} seconds`}
                data-testid="grid-hit"
              />
            );
          })}
          {marquee && <div className="grid-marquee" style={marqueeStyle} />}
        </div>
      </div>
    </section>
  );
});
