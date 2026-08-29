"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, Cloud, Download, Eye, EyeOff, Grid3X3, HelpCircle, Minus, Plus, Redo2, Settings, Undo2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Brand } from "@/components/brand";
import { useTransport } from "@/components/transport-provider";
import { api } from "@/lib/api/client";
import { createDemoEvents, demoProject, demoProjects, demoWaveform } from "@/lib/demo-data";
import { EDITOR_ROWS, type DrumEvent, type DrumProject, type Instrument, type SnapValue } from "@/lib/domain";
import { createEvent, diffDrumEvents, gridStepSeconds, lowConfidenceEvents, moveEvent } from "@/lib/music";
import { DrumGrid } from "@/components/editor/drum-grid";
import { ExportModal } from "@/components/editor/export-modal";
import { NoteInspector } from "@/components/editor/note-inspector";
import { ShortcutsModal } from "@/components/editor/shortcuts-modal";
import { TransportBar } from "@/components/editor/transport-bar";
import { useEditorHistory } from "@/components/editor/use-editor-history";
import { Waveform } from "@/components/editor/waveform";

const NotationView = dynamic(() => import("@/components/editor/notation-view"), {
  ssr: false,
  loading: () => <div className="notation-loading">Engraving notation…</div>,
});

type SaveState = "saved" | "editing" | "saving" | "error";

function nextId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const value = Math.floor(Math.random() * 16);
    return (character === "x" ? value : (value & 0x3) | 0x8).toString(16);
  });
}

export function EditorClient({ projectId }: { projectId: string }) {
  const searchParams = useSearchParams();
  const transport = useTransport();
  const { loadAudioSources } = transport;
  const [project, setProject] = useState<DrumProject>({ ...demoProject, id: projectId });
  const { events, apply, replace, undo, redo, canUndo, canRedo } = useEditorHistory(createDemoEvents().map((event) => ({ ...event, projectId })));
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [snap, setSnap] = useState<SnapValue>("sixteenth");
  const [zoom, setZoom] = useState(1.7);
  const [confidenceOverlay, setConfidenceOverlay] = useState(false);
  const [waveform, setWaveform] = useState<number[] | null>(() => demoProjects.some((item) => item.id === projectId) ? demoWaveform : null);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [exportOpen, setExportOpen] = useState(searchParams.get("export") === "1");
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const revisionRef = useRef(1);
  const clipboardRef = useRef<DrumEvent[]>([]);
  const hydratedRef = useRef(false);
  const savedEventsRef = useRef<DrumEvent[]>([]);
  const latestEventsRef = useRef(events);
  const savedTitleRef = useRef("");
  const latestTitleRef = useRef(project.title);
  const saveChainRef = useRef<Promise<void>>(Promise.resolve());

  const cleanAfter = useCallback((savedEvents: DrumEvent[], savedTitle: string) => {
    const pending = diffDrumEvents(savedEvents, latestEventsRef.current);
    return pending.upserts.length === 0 && pending.deleteIds.length === 0 && savedTitle === latestTitleRef.current.trim();
  }, []);

  const persistEvents = useCallback((snapshot: DrumEvent[]) => {
    const operation = saveChainRef.current.catch(() => undefined).then(async () => {
      const changes = diffDrumEvents(savedEventsRef.current, snapshot);
      if (!changes.upserts.length && !changes.deleteIds.length) return;
      setSaveState("saving");
      const result = await api.bulkUpdateEvents(projectId, { ...changes, snapshot }, revisionRef.current);
      revisionRef.current = result.revision;
      savedEventsRef.current = snapshot.map((event) => ({ ...event }));
      setSaveState(cleanAfter(savedEventsRef.current, savedTitleRef.current) ? "saved" : "editing");
    }).catch((reason) => {
      setSaveState("error");
      throw reason;
    });
    saveChainRef.current = operation.catch(() => undefined);
    return operation;
  }, [cleanAfter, projectId]);

  const persistTitle = useCallback((title: string) => {
    const normalized = title.trim();
    const operation = saveChainRef.current.catch(() => undefined).then(async () => {
      if (!normalized) throw new Error("Give the project a title before saving.");
      if (normalized === savedTitleRef.current) return;
      setSaveState("saving");
      await api.updateProject(projectId, { title: normalized });
      savedTitleRef.current = normalized;
      setSaveState(cleanAfter(savedEventsRef.current, savedTitleRef.current) ? "saved" : "editing");
    }).catch((reason) => {
      setSaveState("error");
      throw reason;
    });
    saveChainRef.current = operation.catch(() => undefined);
    return operation;
  }, [cleanAfter, projectId]);

  const flushPendingChanges = useCallback(async () => {
    await persistEvents(latestEventsRef.current);
    await persistTitle(latestTitleRef.current);
  }, [persistEvents, persistTitle]);

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
      } catch { /* Playback keeps its current buffered source and retries on the next page load. */ }
    };
    void api.getProject(projectId).then((result) => {
      if (!active) return;
      setProject(result.project);
      const hydratedEvents = result.events.map((event) => ({ ...event, projectId }));
      savedEventsRef.current = hydratedEvents.map((event) => ({ ...event }));
      latestEventsRef.current = hydratedEvents;
      savedTitleRef.current = result.project.title;
      latestTitleRef.current = result.project.title;
      replace(hydratedEvents);
      revisionRef.current = result.revision;
      hydratedRef.current = true;
      setSaveState("saved");
      void refreshAudio(result.project.bpm, result.project.beatsPerMeasure, false);
      void api.getWaveformPeaks(projectId).then((peaks) => { if (peaks) setWaveform(peaks); }).catch(() => undefined);
    });
    return () => { active = false; if (audioRefreshTimer) window.clearTimeout(audioRefreshTimer); };
  }, [loadAudioSources, projectId, replace]);

  useEffect(() => {
    latestEventsRef.current = events;
    if (!hydratedRef.current) return;
    const changes = diffDrumEvents(savedEventsRef.current, events);
    if (!changes.upserts.length && !changes.deleteIds.length) return;
    setSaveState("editing");
    const timer = window.setTimeout(() => {
      void persistEvents(events).catch(() => undefined);
    }, 650);
    return () => window.clearTimeout(timer);
  }, [events, persistEvents]);

  useEffect(() => {
    latestTitleRef.current = project.title;
    if (!hydratedRef.current || project.title.trim() === savedTitleRef.current) return;
    setSaveState("editing");
    const timer = window.setTimeout(() => void persistTitle(project.title).catch(() => undefined), 650);
    return () => window.clearTimeout(timer);
  }, [persistTitle, project.title]);

  const selected = useMemo(() => events.filter((event) => selectedIds.has(event.id)), [events, selectedIds]);
  const uncertain = useMemo(() => lowConfidenceEvents(events), [events]);

  const selectOne = useCallback((id: string, additive: boolean) => {
    setSelectedIds((current) => {
      if (!additive) return new Set([id]);
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  const addAt = useCallback((time: number, instrument: Instrument) => {
    const item = createEvent({ id: nextId(), projectId: project.id, instrument, time, bpm: project.bpm, snap });
    apply((currentEvents) => [...currentEvents, item]);
    setSelectedIds(new Set([item.id]));
  }, [apply, project.bpm, project.id, snap]);

  const deleteSelected = useCallback(() => {
    if (!selectedIds.size) return;
    apply((currentEvents) => currentEvents.filter((event) => !selectedIds.has(event.id)));
    setSelectedIds(new Set());
  }, [apply, selectedIds]);

  const moveSelected = useCallback((ids: Set<string>, deltaTime: number, deltaRows: number) => {
    apply((currentEvents) => currentEvents.map((event) => {
      if (!ids.has(event.id)) return event;
      const currentRow = EDITOR_ROWS.indexOf(event.instrument);
      const nextRow = currentRow < 0 ? currentRow : Math.max(0, Math.min(EDITOR_ROWS.length - 1, currentRow + deltaRows));
      return moveEvent(event, {
        instrument: nextRow < 0 ? event.instrument : EDITOR_ROWS[nextRow],
        onsetSeconds: Math.max(0, Math.min(project.durationSeconds, event.onsetSeconds + deltaTime)),
        quantizedOnset: Math.max(0, Math.min(project.durationSeconds, event.quantizedOnset + deltaTime)),
      }, project.bpm);
    }));
  }, [apply, project.bpm, project.durationSeconds]);

  const changeSelected = useCallback((changes: Partial<Pick<DrumEvent, "instrument" | "velocity">>) => {
    apply((currentEvents) => currentEvents.map((event) => selectedIds.has(event.id) ? moveEvent(event, changes, project.bpm) : event));
  }, [apply, project.bpm, selectedIds]);

  const reviewNext = useCallback(() => {
    if (!uncertain.length) return;
    const currentIndex = uncertain.findIndex((event) => selectedIds.has(event.id));
    const next = uncertain[(currentIndex + 1) % uncertain.length];
    setSelectedIds(new Set([next.id]));
    transport.seek(Math.max(0, next.quantizedOnset - 0.75));
  }, [selectedIds, transport, uncertain]);

  const duplicate = useCallback((source = selected) => {
    if (!source.length) return;
    const step = gridStepSeconds(project.bpm, snap);
    const copies = source.map((event) => moveEvent({ ...event, id: nextId(), source: "MANUAL", createdAt: new Date().toISOString() }, { onsetSeconds: event.onsetSeconds + step, quantizedOnset: event.quantizedOnset + step }, project.bpm));
    apply((currentEvents) => [...currentEvents, ...copies]);
    setSelectedIds(new Set(copies.map((event) => event.id)));
  }, [apply, project.bpm, selected, snap]);

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable) return;
      const modifier = event.metaKey || event.ctrlKey;
      if (event.code === "Space") { event.preventDefault(); transport.togglePlayback(); return; }
      if (modifier && event.key.toLowerCase() === "z") { event.preventDefault(); if (event.shiftKey) redo(); else undo(); return; }
      if (modifier && event.key.toLowerCase() === "c") { clipboardRef.current = selected.map((item) => ({ ...item })); return; }
      if (modifier && event.key.toLowerCase() === "v") { event.preventDefault(); duplicate(clipboardRef.current); return; }
      if (modifier && event.key.toLowerCase() === "d") { event.preventDefault(); duplicate(); return; }
      if (event.key === "Delete" || event.key === "Backspace") { event.preventDefault(); deleteSelected(); return; }
      if (event.key.toLowerCase() === "l") { transport.setLoop({ ...transport.loop, enabled: !transport.loop.enabled }); return; }
      if (event.key.toLowerCase() === "m") { transport.setMixer({ ...transport.mixer, metronome: transport.mixer.metronome > 0 ? 0 : 0.7 }); return; }
      if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key) && selectedIds.size) {
        event.preventDefault();
        const step = gridStepSeconds(project.bpm, snap);
        moveSelected(selectedIds, event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0, event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0);
        return;
      }
      if (event.key === "+" || event.key === "=") setZoom((value) => Math.min(4, value + 0.25));
      if (event.key === "-" || event.key === "_") setZoom((value) => Math.max(1, value - 0.25));
      if (event.key === "?") setShortcutsOpen(true);
    };
    window.addEventListener("keydown", keydown);
    return () => window.removeEventListener("keydown", keydown);
  }, [deleteSelected, duplicate, moveSelected, project.bpm, redo, selected, selectedIds, snap, transport, undo]);

  const saveLabel = saveState === "saved" ? "All changes saved" : saveState === "saving" ? "Saving…" : saveState === "error" ? "Save failed · retry" : "Unsaved changes";

  return (
    <div className="editor-shell" data-testid="editor">
      <header className="editor-toolbar">
        <div className="editor-brand"><Brand compact /><Link href="/projects" className="editor-back">Projects</Link><span className="toolbar-divider" /><label className="sr-only" htmlFor="project-title">Project title</label><input id="project-title" className="project-title-input" value={project.title} onChange={(event) => setProject({ ...project, title: event.target.value })} /></div>
        <div className="editor-history">
          <button className="icon-button" type="button" aria-label="Undo" disabled={!canUndo} onClick={undo} data-testid="undo"><Undo2 /></button>
          <button className="icon-button" type="button" aria-label="Redo" disabled={!canRedo} onClick={redo} data-testid="redo"><Redo2 /></button>
          <button className={`save-status save-${saveState}`} type="button" disabled={saveState !== "error"} onClick={() => void flushPendingChanges().catch(() => undefined)} title={saveState === "error" ? "Retry saving changes" : saveLabel}>{saveState === "saved" ? <Check /> : <Cloud />}{saveLabel}</button>
        </div>
        <div className="editor-actions">
          <button className="icon-button" type="button" aria-label="Keyboard shortcuts" onClick={() => setShortcutsOpen(true)}><HelpCircle /></button>
          <Link className="button button-small" href={`/projects/${project.id}/practice`}>Practice</Link>
          <button className="button button-primary button-small" type="button" onClick={() => setExportOpen(true)} data-testid="open-export"><Download size={15} /> Export</button>
          <Link className="icon-button" href={`/projects/${project.id}/settings`} aria-label="Project settings"><Settings /></Link>
        </div>
      </header>

      <div className="mobile-editor-notice">Editing is optimized for desktop and tablet. Mobile keeps playback, notation and review controls available.</div>

      <div className="editor-workspace">
        <div className="editor-main">
          <NotationView project={project} events={events} selectedIds={selectedIds} currentTime={transport.currentTime} onSelect={selectOne} />
          <Waveform project={project} currentTime={transport.currentTime} loop={transport.loop} peaks={waveform} onSeek={transport.seek} onLoopChange={transport.setLoop} />
          <div className="grid-tools">
            <div className="grid-tools-group"><Grid3X3 /><strong>Drum grid</strong><span>{events.length} hits</span></div>
            <div className="grid-tools-group">
              <label>Snap <select value={snap} onChange={(event) => setSnap(event.target.value as SnapValue)} data-testid="snap-select"><option value="off">Off</option><option value="quarter">1/4</option><option value="eighth">1/8</option><option value="sixteenth">1/16</option><option value="thirty-second">1/32</option><option value="triplet">Triplet · beta</option></select></label>
              <button className={`icon-button${confidenceOverlay ? " is-active" : ""}`} type="button" onClick={() => setConfidenceOverlay((value) => !value)} aria-label="Toggle confidence overlay">{confidenceOverlay ? <Eye /> : <EyeOff />}</button>
              <div className="zoom-control"><button type="button" onClick={() => setZoom((value) => Math.max(1, value - .25))} aria-label="Zoom out"><Minus /></button><span>{Math.round(zoom * 100)}%</span><button type="button" onClick={() => setZoom((value) => Math.min(4, value + .25))} aria-label="Zoom in"><Plus /></button></div>
            </div>
          </div>
          <DrumGrid events={events} duration={project.durationSeconds} bpm={project.bpm} beatsPerMeasure={project.beatsPerMeasure} selectedIds={selectedIds} snap={snap} zoom={zoom} confidenceOverlay={confidenceOverlay} onAdd={addAt} onSelect={setSelectedIds} onMove={moveSelected} />
        </div>
        <NoteInspector selected={selected} uncertainCount={uncertain.length} onChange={changeSelected} onReviewNext={reviewNext} onDelete={deleteSelected} />
      </div>
      <TransportBar />
      {exportOpen && <ExportModal project={project} events={events} beforeExport={flushPendingChanges} onClose={() => setExportOpen(false)} />}
      {shortcutsOpen && <ShortcutsModal onClose={() => setShortcutsOpen(false)} />}
    </div>
  );
}
