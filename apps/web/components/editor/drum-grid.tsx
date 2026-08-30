"use client";

import { CheckCircle2, Copy, Crosshair, Repeat2, TimerReset, Trash2 } from "lucide-react";
import { memo, useEffect, useRef, useState } from "react";
import { EDITOR_ROWS, INSTRUMENT_LABELS, type DrumEvent, type Instrument, type SnapValue } from "@/lib/domain";
import { snapSeconds } from "@/lib/music";

const ROW_HEIGHT = 30;

interface Point { x: number; y: number }
type GridContext =
  | { kind: "hit"; x: number; y: number; item: DrumEvent; ids: Set<string> }
  | { kind: "measure"; x: number; y: number; measureIndex: number; ids: Set<string> };

export const DrumGrid = memo(function DrumGrid({ events, duration, bpm, beatsPerMeasure, selectedIds, snap, zoom, confidenceOverlay, onAdd, onSelect, onMove, onDuplicate, onDeleteIds, onChangeInstrument, onQuantize, onMarkCorrect, onLoopMeasure, onOpenTiming }: {
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
  onDuplicate: (events: DrumEvent[]) => void;
  onDeleteIds: (ids: Set<string>) => void;
  onChangeInstrument: (ids: Set<string>, instrument: Instrument) => void;
  onQuantize: (ids: Set<string>) => void;
  onMarkCorrect: (ids: Set<string>) => void;
  onLoopMeasure: (measureIndex: number) => void;
  onOpenTiming: (measureIndex: number) => void;
}) {
  const gridRef = useRef<HTMLDivElement>(null);
  const labelTrackRef = useRef<HTMLDivElement>(null);
  const [marquee, setMarquee] = useState<{ start: Point; end: Point } | null>(null);
  const [drag, setDrag] = useState<{ start: Point; ids: Set<string>; dx: number; dy: number } | null>(null);
  const [context, setContext] = useState<GridContext | null>(null);
  const measureDuration = beatsPerMeasure * 60 / bpm;
  const measureCount = Math.ceil(duration / measureDuration);

  useEffect(() => {
    if (!context) return;
    const close = () => setContext(null);
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") close(); };
    window.addEventListener("pointerdown", close, { once: true });
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      window.removeEventListener("pointerdown", close);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [context]);

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

  const menuPosition = (clientX: number, clientY: number) => ({
    x: Math.max(8, Math.min(window.innerWidth - 196, clientX)),
    y: Math.max(8, Math.min(window.innerHeight - 238, clientY)),
  });

  const openHitMenu = (event: React.MouseEvent<HTMLButtonElement>, item: DrumEvent) => {
    event.preventDefault();
    event.stopPropagation();
    const ids = selectedIds.has(item.id) ? new Set(selectedIds) : new Set([item.id]);
    onSelect(ids);
    const position = menuPosition(event.clientX, event.clientY);
    setContext({ kind: "hit", ...position, item, ids });
  };

  const openMeasureMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    if ((event.target as Element).closest(".grid-hit")) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    const time = Math.max(0, Math.min(duration, (event.clientX - rect.left) / rect.width * duration));
    const measureIndex = Math.max(0, Math.min(measureCount - 1, Math.floor(time / measureDuration)));
    const ids = new Set(events.filter((item) => item.measureIndex === measureIndex).map((item) => item.id));
    const position = menuPosition(event.clientX, event.clientY);
    setContext({ kind: "measure", ...position, measureIndex, ids });
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
          onContextMenu={openMeasureMenu}
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
                onContextMenu={(event) => openHitMenu(event, item)}
                aria-label={`${INSTRUMENT_LABELS[item.instrument]} hit at ${item.quantizedOnset.toFixed(2)} seconds`}
                data-testid="grid-hit"
              />
            );
          })}
          {marquee && <div className="grid-marquee" style={marqueeStyle} />}
        </div>
      </div>
      {context && (
        <div className="grid-context-menu" role="menu" style={{ left: context.x, top: context.y }} onPointerDown={(event) => event.stopPropagation()} onContextMenu={(event) => event.preventDefault()}>
          <div className="grid-context-title">{context.kind === "hit" ? `${INSTRUMENT_LABELS[context.item.instrument]} · ${context.ids.size} selected` : `Measure ${context.measureIndex + 1}`}</div>
          {context.kind === "hit" ? <>
            <label>Instrument<select value={context.item.instrument} onChange={(event) => { onChangeInstrument(context.ids, event.target.value as Instrument); setContext(null); }}>{EDITOR_ROWS.map((instrument) => <option value={instrument} key={instrument}>{INSTRUMENT_LABELS[instrument]}</option>)}</select></label>
            <button type="button" role="menuitem" onClick={() => { onDuplicate(events.filter((item) => context.ids.has(item.id))); setContext(null); }}><Copy /> Duplicate</button>
            <button type="button" role="menuitem" onClick={() => { onQuantize(context.ids); setContext(null); }}><TimerReset /> Quantize to snap</button>
            <button type="button" role="menuitem" onClick={() => { onMarkCorrect(context.ids); setContext(null); }}><CheckCircle2 /> Mark correct</button>
            <button className="is-danger" type="button" role="menuitem" onClick={() => { onDeleteIds(context.ids); setContext(null); }}><Trash2 /> Delete</button>
          </> : <>
            <button type="button" role="menuitem" onClick={() => { onLoopMeasure(context.measureIndex); setContext(null); }}><Repeat2 /> Loop measure</button>
            <button type="button" role="menuitem" disabled={!context.ids.size} onClick={() => { onQuantize(context.ids); setContext(null); }}><TimerReset /> Requantize measure</button>
            <button type="button" role="menuitem" disabled={!context.ids.size} onClick={() => { onSelect(context.ids); setContext(null); }}><Crosshair /> Select measure hits</button>
            <button type="button" role="menuitem" onClick={() => { onOpenTiming(context.measureIndex); setContext(null); }}><TimerReset /> Open in Timing</button>
          </>}
        </div>
      )}
    </section>
  );
});
