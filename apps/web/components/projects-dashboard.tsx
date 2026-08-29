"use client";

import Link from "next/link";
import { Download, MoreHorizontal, Plus, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import { demoWaveform } from "@/lib/demo-data";
import type { DrumProject } from "@/lib/domain";
import { formatTime } from "@/lib/file-validation";

type SortMode = "recent" | "oldest" | "name";

export function ProjectsDashboard() {
  const [projects, setProjects] = useState<DrumProject[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortMode>("recent");
  const [menu, setMenu] = useState<string | null>(null);
  const [deleted, setDeleted] = useState<DrumProject | null>(null);

  useEffect(() => { void api.listProjects().then(setProjects); }, []);

  const visible = useMemo(() => {
    const filtered = projects.filter((project) => project.title.toLowerCase().includes(query.toLowerCase()));
    return filtered.sort((a, b) => sort === "name" ? a.title.localeCompare(b.title) : sort === "oldest" ? a.updatedAt.localeCompare(b.updatedAt) : b.updatedAt.localeCompare(a.updatedAt));
  }, [projects, query, sort]);

  const rename = async (project: DrumProject) => {
    const title = window.prompt("Project title", project.title)?.trim();
    if (title) {
      setProjects((items) => items.map((item) => item.id === project.id ? { ...item, title, updatedAt: new Date().toISOString() } : item));
      try { await api.updateProject(project.id, { title }); } catch { setProjects((items) => items.map((item) => item.id === project.id ? project : item)); }
    }
    setMenu(null);
  };

  const duplicate = async (project: DrumProject) => {
    const duplicateTitle = `${project.title} copy`;
    const created = await api.duplicateProject(project.id, duplicateTitle).catch(() => null);
    setProjects((items) => [created ?? { ...project, id: `${project.id}-copy-${Date.now()}`, title: duplicateTitle, updatedAt: new Date().toISOString() }, ...items]);
    setMenu(null);
  };

  const remove = async (project: DrumProject) => {
    setProjects((items) => items.filter((item) => item.id !== project.id));
    setDeleted(project);
    setMenu(null);
    try { await api.deleteProject(project.id); } catch { setProjects((items) => [project, ...items]); setDeleted(null); }
  };

  return (
    <main className="dashboard-shell" id="main-content">
      <header className="dashboard-header">
        <div><p className="eyebrow">Your workspace</p><h1>Projects</h1></div>
        <Link className="button button-primary" href="/upload"><Plus size={17} /> New transcription</Link>
      </header>
      <div className="project-tools">
        <div className="search-field"><Search aria-hidden="true" /><label className="sr-only" htmlFor="project-search">Search projects</label><input className="text-input" id="project-search" type="search" placeholder="Search projects" value={query} onChange={(event) => setQuery(event.target.value)} /></div>
        <label className="field-label">Sort <select className="select-input" value={sort} onChange={(event) => setSort(event.target.value as SortMode)} style={{ width: 140, marginLeft: 8 }}><option value="recent">Recent</option><option value="oldest">Oldest</option><option value="name">Name</option></select></label>
      </div>
      {visible.length ? (
        <div className="project-grid" data-testid="project-grid">
          {visible.map((project, projectIndex) => (
            <article className="project-card" key={project.id}>
              <Link href={`/projects/${project.id}`} aria-label={`Open ${project.title}`}>
                <div className="project-wave" aria-hidden="true">{demoWaveform.slice(0, 42).map((height, index) => <i key={index} style={{ height: `${Math.max(12, height * (72 - projectIndex * 2))}%` }} />)}</div>
              </Link>
              <div className="project-card-body">
                <h2><Link href={`/projects/${project.id}`}>{project.title}</Link></h2>
                <span className="muted" style={{ fontSize: ".72rem" }}>{project.artist}</span>
                <div className="project-card-meta"><span>{formatTime(project.durationSeconds)} · {project.bpm} BPM</span><span>{new Date(project.updatedAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span></div>
                <div className="project-card-actions">
                  {project.reviewCount ? <span className="pill">{project.reviewCount} to review</span> : <span className="pill pill-lime">Reviewed</span>}
                  <div style={{ position: "relative" }}>
                    <button className="icon-button" type="button" aria-label={`Actions for ${project.title}`} aria-expanded={menu === project.id} onClick={() => setMenu(menu === project.id ? null : project.id)}><MoreHorizontal /></button>
                    {menu === project.id && (
                      <div style={{ position: "absolute", zIndex: 4, right: 0, bottom: 44, width: 150, padding: 6, border: "1px solid var(--line-strong)", borderRadius: 9, background: "#20252e", boxShadow: "var(--shadow)" }}>
                        <button className="menu-action" type="button" onClick={() => void rename(project)}>Rename</button>
                        <button className="menu-action" type="button" onClick={() => void duplicate(project)}>Duplicate</button>
                        <Link className="menu-action" href={`/projects/${project.id}?export=1`}><Download size={13} /> Export</Link>
                        <button className="menu-action danger-text" type="button" onClick={() => void remove(project)}>Delete</button>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            </article>
          ))}
        </div>
      ) : <div className="empty-state"><h2>No matching projects</h2><p className="muted">Try a different search, or start a new transcription.</p></div>}
      {deleted && (
        <div className="toast" role="status"><span>{deleted.title} moved to deleted projects.</span><button type="button" onClick={() => { const restoring = deleted; setProjects((items) => [restoring, ...items]); setDeleted(null); void api.restoreProject(restoring.id).catch(() => { setProjects((items) => items.filter((item) => item.id !== restoring.id)); }); }}>Undo</button></div>
      )}
    </main>
  );
}
