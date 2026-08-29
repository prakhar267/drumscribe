"use client";

import { useRef, useState } from "react";
import type { DrumProject } from "@/lib/domain";

export function Waveform({ project, currentTime, loop, peaks, onSeek, onLoopChange }: {
  project: DrumProject;
  currentTime: number;
  loop: { enabled: boolean; start: number; end: number };
  peaks: number[] | null;
  onSeek: (time: number) => void;
  onLoopChange: (loop: { enabled: boolean; start: number; end: number }) => void;
}) {
  const dragStart = useRef<{ x: number; time: number } | null>(null);
  const [preview, setPreview] = useState<{ start: number; end: number } | null>(null);
  const timeAtPointer = (event: React.PointerEvent<HTMLDivElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(project.durationSeconds, (event.clientX - rect.left) / rect.width * project.durationSeconds));
  };
  const pointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    const time = timeAtPointer(event);
    dragStart.current = { x: event.clientX, time };
    setPreview({ start: time, end: time });
  };
  const pointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const time = timeAtPointer(event);
    setPreview({ start: Math.min(dragStart.current.time, time), end: Math.max(dragStart.current.time, time) });
  };
  const pointerUp = (event: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const time = timeAtPointer(event);
    if (Math.abs(event.clientX - dragStart.current.x) < 6) onSeek(time);
    else onLoopChange({ enabled: true, start: Math.min(dragStart.current.time, time), end: Math.max(dragStart.current.time, time) });
    dragStart.current = null;
    setPreview(null);
  };
  return (
    <section className="editor-waveform-panel" aria-label="Audio waveform">
      <div className="waveform-ruler">
        {Array.from({ length: 7 }, (_, index) => <span key={index} style={{ left: `${index / 6 * 100}%` }}>{index * 2 + 1}</span>)}
        <em>Click to seek · drag to set a loop</em>
      </div>
      <div className="editor-waveform" onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} data-testid="editor-waveform">
        {peaks?.length ? peaks.map((height, index) => <i key={index} style={{ height: `${Math.max(.03, height) * 90}%` }} />) : <span className="waveform-unavailable">Waveform peaks are still preparing</span>}
        {loop.enabled && <div className="wave-loop" style={{ left: `${loop.start / project.durationSeconds * 100}%`, width: `${(loop.end - loop.start) / project.durationSeconds * 100}%` }} />}
        {preview && <div className="wave-loop is-preview" style={{ left: `${preview.start / project.durationSeconds * 100}%`, width: `${(preview.end - preview.start) / project.durationSeconds * 100}%` }} />}
        <div className="editor-playhead" style={{ left: `${currentTime / project.durationSeconds * 100}%` }} />
      </div>
    </section>
  );
}
