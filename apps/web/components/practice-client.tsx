"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { ChevronLeft, Headphones, ListMusic, Pause, Play, Repeat2, SlidersHorizontal } from "lucide-react";
import { useEffect, useState } from "react";
import { Brand } from "@/components/brand";
import { useTransport } from "@/components/transport-provider";
import { api } from "@/lib/api/client";
import { createDemoEvents, demoProject } from "@/lib/demo-data";
import type { DrumEvent, DrumProject } from "@/lib/domain";
import { formatTime } from "@/lib/file-validation";

const NotationView = dynamic(() => import("@/components/editor/notation-view"), { ssr: false });

export function PracticeClient({ projectId }: { projectId: string }) {
  const transport = useTransport();
  const { loadAudioSources } = transport;
  const [project, setProject] = useState<DrumProject>({ ...demoProject, id: projectId });
  const [events, setEvents] = useState<DrumEvent[]>(createDemoEvents());
  const [countIn, setCountIn] = useState<0 | 1 | 2>(1);
  const measureDuration = project.beatsPerMeasure * 60 / project.bpm;
  const activeMeasure = Math.floor(transport.currentTime / measureDuration);

  useEffect(() => {
    let active = true;
    let audioRefreshTimer: number | undefined;
    const refreshAudio = async (bpm: number, beatsPerMeasure: number, preservePosition: boolean) => {
      try {
        const sources = await api.getAudioSources(projectId);
        if (!active || !sources) return;
        loadAudioSources({ ...sources, bpm, beatsPerMeasure, preservePosition });
        const refreshIn = Math.max(5_000, Date.parse(sources.expiresAt) - Date.now() - 60_000);
        audioRefreshTimer = window.setTimeout(() => void refreshAudio(bpm, beatsPerMeasure, true), Number.isFinite(refreshIn) ? refreshIn : 8 * 60_000);
      } catch { /* Keep any already buffered audio available. */ }
    };
    void api.getProject(projectId).then((result) => {
      if (!active) return;
      setProject(result.project);
      setEvents(result.events);
      void refreshAudio(result.project.bpm, result.project.beatsPerMeasure, false);
    });
    return () => { active = false; if (audioRefreshTimer) window.clearTimeout(audioRefreshTimer); };
  }, [loadAudioSources, projectId]);
  const setMeasureLoop = (measure: number, extend: boolean) => {
    const selectedStart = measure * measureDuration;
    const selectedEnd = Math.min(project.durationSeconds, selectedStart + measureDuration);
    const start = extend && transport.loop.enabled ? Math.min(transport.loop.start, selectedStart) : selectedStart;
    const end = extend && transport.loop.enabled ? Math.max(transport.loop.end, selectedEnd) : selectedEnd;
    transport.setLoop({ enabled: true, start, end });
    transport.seek(start);
  };

  return (
    <main className="practice-shell" id="main-content">
      <header className="practice-header"><Brand /><div><p className="eyebrow">Practice mode</p><h1>{project.title}</h1></div><Link className="button button-small" href={`/projects/${project.id}`}><ChevronLeft size={15} /> Back to editor</Link></header>
      <section className="practice-stage">
        <div className="practice-status"><span>Measure {activeMeasure + 1}</span><strong>{project.bpm} BPM · {project.beatsPerMeasure}/4</strong><span>{formatTime(transport.currentTime)}</span></div>
        <div className="practice-score"><NotationView project={project} events={events} selectedIds={new Set()} currentTime={transport.currentTime} onSelect={(id) => { const event = events.find((item) => item.id === id); if (event) transport.seek(event.quantizedOnset); }} /></div>
        <div className="measure-loop-strip" aria-label="Choose measures to loop">{Array.from({ length: Math.ceil(project.durationSeconds / measureDuration) }, (_, measure) => { const measureStart = measure * measureDuration; const selected = transport.loop.enabled && measureStart >= transport.loop.start - .05 && measureStart < transport.loop.end - .05; return <button className={selected ? "is-active" : ""} type="button" key={measure} onClick={(event) => setMeasureLoop(measure, event.shiftKey)} title="Click for one measure; Shift-click to extend the loop">{measure + 1}</button>; })}</div>
      </section>
      <section className="practice-controls">
        <div className="practice-control-group"><button className="practice-play" type="button" onClick={() => transport.playWithCountIn(countIn)} aria-label={transport.playing ? "Pause" : transport.countingIn ? "Cancel count-in" : "Play"}>{transport.playing ? <Pause /> : <Play />}</button><div><span className="field-label">Transport</span><strong>{transport.countingIn ? `${countIn}-bar count-in` : transport.playing ? "Playing" : "Ready"}</strong></div></div>
        <label className="practice-control"><span><SlidersHorizontal /> Speed</span><select value={transport.playbackRate} onChange={(event) => transport.setPlaybackRate(Number(event.target.value))}>{[.25,.5,.75,.9,1,1.1,1.25,1.5].map((rate) => <option key={rate} value={rate}>{rate}×</option>)}</select></label>
        <button className={`practice-control${transport.loop.enabled ? " is-active" : ""}`} type="button" onClick={() => transport.setLoop({ ...transport.loop, enabled: !transport.loop.enabled })}><span><Repeat2 /> Loop</span><strong>{transport.loop.enabled ? "On" : "Off"}</strong></button>
        <button className={`practice-control${transport.mixer.metronome > 0 ? " is-active" : ""}`} type="button" onClick={() => transport.setMixer({ ...transport.mixer, metronome: transport.mixer.metronome > 0 ? 0 : .75 })}><span><ListMusic /> Click</span><strong>{transport.mixer.metronome > 0 ? "On" : "Off"}</strong></button>
        <label className="practice-control"><span><Repeat2 /> Count-in</span><select value={countIn} onChange={(event) => setCountIn(Number(event.target.value) as 0 | 1 | 2)}><option value="0">Off</option><option value="1">1 bar</option><option value="2">2 bars</option></select></label>
        <div className="practice-mix"><span><Headphones /> Mix</span><label>Song<input type="range" min="0" max="1" step=".01" value={transport.mixer.original} onChange={(event) => transport.setMixer({ ...transport.mixer, original: Number(event.target.value) })} /></label><label>Drums<input type="range" min="0" max="1" step=".01" value={transport.mixer.drums} onChange={(event) => transport.setMixer({ ...transport.mixer, drums: Number(event.target.value) })} /></label></div>
      </section>
    </main>
  );
}
