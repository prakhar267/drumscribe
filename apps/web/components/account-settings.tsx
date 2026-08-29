"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { Download, LogOut, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/lib/api/client";

export function AccountSettings() {
  const router = useRouter();
  const [email, setEmail] = useState("Loading…");
  const [accountKind, setAccountKind] = useState("Account");
  const [allowModelImprovement, setAllowModelImprovement] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [accountDeleted, setAccountDeleted] = useState(false);
  useEffect(() => {
    void api.getAccount().then((account) => {
      setEmail(account.email ?? "Anonymous session — add an email from the sign-in page");
      setAccountKind(account.kind === "ANONYMOUS" ? "Anonymous workspace" : "Email account");
      setAllowModelImprovement(account.allowModelImprovement);
    }).catch(() => { setEmail("Account details unavailable"); setAccountKind("Reconnect to load"); });
  }, []);
  const exportData = async () => {
    setExporting(true);
    setExportError(null);
    try {
      const [account, projects] = await Promise.all([api.getAccount(), api.listProjects()]);
      const projectData = await Promise.all(projects.map(async (project) => {
        const [{ events, revision }, revisions] = await Promise.all([
          api.getProject(project.id),
          api.listRevisions(project.id),
        ]);
        return { project, activeRevision: revision, events, revisions };
      }));
      const payload = JSON.stringify({ schema: "drumscribe.user-export.v1", exportedAt: new Date().toISOString(), account, projects: projectData }, null, 2);
      const url = URL.createObjectURL(new Blob([payload], { type: "application/json" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `drumscribe-data-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 500);
    } catch (reason) {
      setExportError(reason instanceof Error ? reason.message : "Your data export could not be created.");
    } finally {
      setExporting(false);
    }
  };
  return (
    <div className="settings-layout">
      <nav className="settings-nav" aria-label="Account settings"><Link className="is-active" href="#profile">Profile</Link><Link href="#privacy">Privacy & data</Link><Link href="#retention">Audio retention</Link><Link href="#account-danger">Delete account</Link></nav>
      <div className="settings-content">
        <section className="surface settings-section" id="profile"><h2>Profile</h2><p>Your authenticated account details. DrumScribe does not invent or publicly display a profile name.</p><div className="settings-form-grid"><label className="field"><span className="field-label">Account type</span><input className="text-input" value={accountKind} readOnly /></label><label className="field"><span className="field-label">Email</span><input className="text-input" value={email} readOnly /></label></div><div style={{ display: "flex", gap: 10, marginTop: 18 }}><Link className="button button-small" href="/auth">Add or change email</Link><button className="button button-small" type="button" onClick={() => { void api.logout().then(() => { router.replace("/"); router.refresh(); }); }}><LogOut size={14} /> Sign out</button></div></section>
        <section className="surface settings-section" id="privacy"><h2>Privacy & data</h2><p>Your projects are private. Customer audio is never used for model training without explicit opt-in.</p><div className="toggle-row"><div><strong>Help improve transcription models</strong><span>Allow corrected examples to be considered for a separately governed, consented dataset. Off by default.</span></div><label className="switch"><input type="checkbox" checked={allowModelImprovement} onChange={(event) => { const next = event.target.checked; setAllowModelImprovement(next); void api.setModelImprovementConsent(next).catch(() => setAllowModelImprovement(!next)); }} /><span /></label></div><p className="muted">The downloadable JSON contains account metadata, project metadata, canonical drum events, and revision descriptors. Private audio remains available only through its project controls.</p><button className="button button-small" type="button" disabled={exporting} onClick={() => void exportData()}><Download size={14} /> {exporting ? "Preparing export…" : "Export my project data"}</button>{exportError && <p className="form-error" role="alert">{exportError}</p>}</section>
        <section className="surface settings-section" id="retention"><h2>Audio retention</h2><p>Active-project audio remains private while its project exists. Temporary processing files are deleted automatically; deleted-project recovery follows the deployed service policy.</p><Link href="/legal/privacy" className="button button-small">Read the retention policy</Link></section>
        <section className="surface settings-section danger-zone" id="account-danger"><h2>Delete account permanently</h2><p>Deletes your projects, exports and associated private audio after any required recovery delay. This cannot be undone after deletion finishes.</p>{accountDeleted ? <div className="notice">Account deletion has been accepted. Your session will now close.</div> : <><label className="field" style={{ maxWidth: 360 }}><span className="field-label">Type DELETE MY ACCOUNT to continue</span><input className="text-input" value={deleteConfirm} onChange={(event) => setDeleteConfirm(event.target.value)} /></label><button className="button button-danger button-small" type="button" disabled={deleteConfirm !== "DELETE MY ACCOUNT"} style={{ marginTop: 14 }} onClick={() => { void api.deleteAccount().then(() => setAccountDeleted(true)); }}><Trash2 size={14} /> Permanently delete account</button></>}</section>
      </div>
    </div>
  );
}
