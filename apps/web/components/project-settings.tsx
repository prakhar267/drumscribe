"use client";

import Link from "next/link";
import { RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type ProjectRevision } from "@/lib/api/client";

export function ProjectSettings({ projectId }: { projectId: string }) {
  const [title, setTitle] = useState("Loading…");
  const [artist, setArtist] = useState("");
  const [bpm, setBpm] = useState<number | null>(null);
  const [beatsPerMeasure, setBeatsPerMeasure] = useState<number | null>(null);
  const [revisions, setRevisions] = useState<ProjectRevision[]>([]);
  const [restored, setRestored] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [deleted, setDeleted] = useState(false);
  const [deletePending, setDeletePending] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  useEffect(() => {
    void api.getProject(projectId).then(({ project }) => { setTitle(project.title); setArtist(project.artist ?? ""); setBpm(project.bpm); setBeatsPerMeasure(project.beatsPerMeasure); });
    void api.listRevisions(projectId).then(setRevisions).catch(() => setRevisions([]));
  }, [projectId]);
  return (
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Project settings"><Link className="is-active" href={`/projects/${projectId}/settings`}>Project details</Link><Link href="#timing">Timing & notation</Link><Link href="#versions">Version history</Link><Link href="#danger">Delete project</Link></nav>
      <div className="settings-content">
        <section className="surface settings-section"><h2>Project details</h2><p>Shown in your project library and on exported scores.</p><div className="settings-form-grid"><label className="field"><span className="field-label">Title</span><input className="text-input" value={title} onChange={(event) => { setTitle(event.target.value); setSaved(false); }} /></label><label className="field"><span className="field-label">Artist / label</span><input className="text-input" value={artist} onChange={(event) => { setArtist(event.target.value); setSaved(false); }} /></label></div><button className="button button-primary button-small" type="button" style={{ marginTop: 18 }} onClick={() => { void api.updateProject(projectId, { title, artist: artist || null }).then(() => setSaved(true)); }}>{saved ? "Saved" : "Save changes"}</button></section>
        <section className="surface settings-section" id="timing"><h2>Detected timing</h2><p>Timing is read-only here in this release. Moving notes in the editor preserves original audio timing.</p><div className="settings-form-grid"><label className="field"><span className="field-label">Tempo</span><input className="text-input" value={bpm === null ? "Loading…" : `${bpm} BPM`} readOnly /></label><label className="field"><span className="field-label">Time signature</span><input className="text-input" value={beatsPerMeasure === null ? "Loading…" : `${beatsPerMeasure}/4`} readOnly /></label></div></section>
        <section className="surface settings-section" id="versions"><h2>Version history</h2><p>Snapshots are created after meaningful saved edit groups.</p>{restored && <div className="notice">Revision restored. <Link href={`/projects/${projectId}`}>Open the refreshed chart</Link></div>}{revisions.length ? revisions.map((revision, index) => <div className="version-row" key={revision.id}><span>{revision.label} · {revision.eventCount} hits · {new Date(revision.createdAt).toLocaleString()}</span><button className="button button-small" type="button" disabled={index === 0} onClick={() => { void api.restoreRevision(projectId, revision.id).then(() => setRestored(revision.id)); }}><RotateCcw size={14} /> Restore</button></div>) : <div className="empty-state"><p className="muted">No server revisions yet. Your first saved edit creates one.</p></div>}</section>
        <section className="surface settings-section danger-zone" id="danger"><h2>Delete project</h2><p>Moves the project and private audio to deleted items. Permanent object removal runs after the configured recovery window.</p>{deleted ? <div className="notice">Project moved to deleted items. <button type="button" className="inline-action" disabled={deletePending} onClick={() => { setDeletePending(true); setDeleteError(null); void api.restoreProject(projectId).then(() => setDeleted(false)).catch((reason: unknown) => setDeleteError(reason instanceof Error ? reason.message : "The project could not be restored.")).finally(() => setDeletePending(false)); }}>{deletePending ? "Restoring…" : "Undo"}</button></div> : <button className="button button-danger button-small" type="button" disabled={deletePending} onClick={() => { setDeletePending(true); setDeleteError(null); void api.deleteProject(projectId).then(() => setDeleted(true)).catch((reason: unknown) => setDeleteError(reason instanceof Error ? reason.message : "The project could not be deleted.")).finally(() => setDeletePending(false)); }}><Trash2 size={14} /> {deletePending ? "Deleting…" : "Delete project"}</button>}{deleteError && <p className="form-error" role="alert">{deleteError}</p>}</section>
      </div>
    </div>
  );
}
