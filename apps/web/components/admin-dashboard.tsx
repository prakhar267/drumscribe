"use client";

import { Activity, Braces, Database, Search, ShieldCheck, Waves } from "lucide-react";
import { useState } from "react";
import { api, type AdminJobDiagnostics } from "@/lib/api/client";

export function AdminDashboard() {
  const [jobId, setJobId] = useState("");
  const [diagnostics, setDiagnostics] = useState<AdminJobDiagnostics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inspect = async () => {
    setLoading(true);
    setError(null);
    setDiagnostics(null);
    try {
      setDiagnostics(await api.getAdminJobDiagnostics(jobId.trim()));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Diagnostics could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="admin-shell" id="main-content">
      <header className="admin-header">
        <div><p className="eyebrow">Internal tools</p><h1>Pipeline debugger</h1><p>Inspect one authorized job at a time. Raw customer audio, object contents, and filenames are deliberately excluded.</p></div>
        <div className="admin-health"><ShieldCheck /><span><strong>Restricted diagnostics</strong>Requires the UI key and an authenticated ADMIN account</span></div>
      </header>
      <section className="surface settings-section">
        <h2>Look up a processing job</h2>
        <form onSubmit={(event) => { event.preventDefault(); if (jobId.trim()) void inspect(); }} style={{ display: "flex", gap: 10, alignItems: "end", flexWrap: "wrap" }}>
          <label className="field" style={{ flex: "1 1 320px" }}><span className="field-label">Job UUID</span><input className="text-input" value={jobId} onChange={(event) => setJobId(event.target.value)} placeholder="00000000-0000-0000-0000-000000000000" required /></label>
          <button className="button button-primary button-small" type="submit" disabled={loading || !jobId.trim()}><Search size={15} /> {loading ? "Inspecting…" : "Inspect job"}</button>
        </form>
        {error && <p className="form-error" role="alert">{error}</p>}
      </section>
      {!diagnostics && !error && <section className="surface settings-section empty-state"><p className="muted">Enter a job ID from an operational alert or support case. No customer jobs are listed or searchable from this screen.</p></section>}
      {diagnostics && <>
        <section className="admin-stats">
          <article><Activity /><span>Job stage</span><strong>{diagnostics.job.stage}</strong><small>{diagnostics.job.approximateProgress}% approximate</small></article>
          <article><Waves /><span>Quantized hits</span><strong>{diagnostics.eventCount}</strong><small>{diagnostics.lowConfidenceEventCount} flagged for review</small></article>
          <article><Database /><span>Private assets</span><strong>{diagnostics.assets.length}</strong><small>metadata only</small></article>
          <article><ShieldCheck /><span>Job retries</span><strong>{diagnostics.job.retryCount}</strong><small>durable queue attempts</small></article>
        </section>
        <div className="admin-grid">
          <section className="surface admin-card"><header><div><Activity /><span><strong>Stage timings</strong><small>{diagnostics.job.id}</small></span></div><span className="pill pill-lime">{diagnostics.job.stage}</span></header><div className="debug-code"><code>{JSON.stringify(diagnostics.stageTimings, null, 2)}</code></div></section>
          <section className="surface admin-card"><header><div><Database /><span><strong>Asset metadata</strong><small>private content excluded</small></span></div></header><div className="debug-code"><code>{JSON.stringify(diagnostics.assets, null, 2)}</code></div></section>
          <section className="surface admin-card admin-wide"><header><div><Braces /><span><strong>Providers & model runs</strong><small>reproducibility record</small></span></div></header><div className="debug-code"><code>{JSON.stringify({ providerVersions: diagnostics.providerVersions, modelRuns: diagnostics.modelRuns, technicalErrorDetail: diagnostics.technicalErrorDetail }, null, 2)}</code></div></section>
        </div>
      </>}
    </main>
  );
}
