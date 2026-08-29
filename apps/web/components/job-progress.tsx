"use client";

import Link from "next/link";
import { Check, ExternalLink, RotateCcw, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api/client";
import { demoProject } from "@/lib/demo-data";
import { PROCESSING_STAGES } from "@/lib/domain";

export function JobProgress({ jobId }: { jobId: string }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [ready, setReady] = useState(false);
  const [projectId, setProjectId] = useState(demoProject.id);
  const [reportedProgress, setReportedProgress] = useState<number | null>(null);
  const [terminal, setTerminal] = useState<"FAILED" | "CANCELLED" | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [pollIssue, setPollIssue] = useState<string | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [cancelRequested, setCancelRequested] = useState(false);
  const [pollCycle, setPollCycle] = useState(0);

  useEffect(() => {
    if (jobId !== "demo-job") return;
    const timer = window.setInterval(() => {
      setActiveIndex((index) => {
        if (index >= PROCESSING_STAGES.length - 1) {
          window.clearInterval(timer);
          setReady(true);
          return index;
        }
        return index + 1;
      });
    }, 650);
    return () => window.clearInterval(timer);
  }, [jobId]);

  useEffect(() => {
    if (jobId === "demo-job") return;
    let active = true;
    let stopped = false;
    const stop = () => { stopped = true; window.clearInterval(interval); };
    const poll = async () => {
      if (stopped) return;
      try {
        const status = await api.getJob(jobId);
        if (!active) return;
        setPollIssue(null);
        setProjectId(status.projectId);
        setReportedProgress(status.approximateProgress);
        setStatusMessage(status.message);
        if (status.stage === "READY") { setReady(true); stop(); return; }
        if (status.stage === "FAILED" || status.stage === "CANCELLED") { setTerminal(status.stage); stop(); return; }
        const index = PROCESSING_STAGES.findIndex((stage) => stage.key === status.stage);
        if (index >= 0) setActiveIndex(index);
      } catch {
        if (active) setPollIssue("Connection interrupted. We’ll keep checking safely.");
      }
    };
    void poll();
    const interval = window.setInterval(() => void poll(), 3000);
    return () => { active = false; stop(); };
  }, [jobId, pollCycle]);

  const progress = useMemo(() => {
    if (ready) return 100;
    if (reportedProgress !== null) return Math.max(0, Math.min(99, reportedProgress));
    const complete = PROCESSING_STAGES.slice(0, activeIndex).reduce((sum, stage) => sum + stage.weight, 0);
    return Math.min(96, complete + PROCESSING_STAGES[activeIndex].weight * 0.55);
  }, [activeIndex, ready, reportedProgress]);

  const retry = async () => {
    setActionPending(true);
    setPollIssue(null);
    try {
      const status = await api.retryJob(jobId);
      setTerminal(null);
      setReady(false);
      setCancelRequested(false);
      setStatusMessage(status.message);
      setReportedProgress(status.approximateProgress);
      setPollCycle((cycle) => cycle + 1);
    } catch (reason) {
      setPollIssue(reason instanceof Error ? reason.message : "The retry could not be started.");
    } finally { setActionPending(false); }
  };

  const cancel = async () => {
    setActionPending(true);
    setPollIssue(null);
    try {
      const status = await api.cancelJob(jobId);
      setCancelRequested(true);
      setStatusMessage(status.stage === "CANCELLED" ? "Processing was cancelled." : "Cancellation requested. The current safe step will finish first.");
      if (status.stage === "CANCELLED") setTerminal("CANCELLED");
    } catch (reason) {
      setPollIssue(reason instanceof Error ? reason.message : "The cancellation request could not be sent.");
    } finally { setActionPending(false); }
  };

  return (
    <main className="processing-page" id="main-content">
      <div className="processing-viz" aria-hidden="true">
        <div className="processing-ring" style={{ "--progress": `${progress}%` } as React.CSSProperties} />
        <div className="processing-number"><strong>{Math.round(progress)}</strong><span>Approximate progress</span></div>
      </div>
      <div className="processing-content">
        <p className="eyebrow">{jobId === "demo-job" ? "Neon Room Groove" : "Drum transcription"}</p>
        <h1>{ready ? "Your chart is ready." : terminal === "FAILED" ? "We couldn’t finish this chart." : terminal === "CANCELLED" ? "Processing cancelled." : PROCESSING_STAGES[activeIndex].label}</h1>
        <p>{ready ? "We found a few sections that may need review. Your original timing is preserved, and every generated hit remains editable." : terminal ? statusMessage ?? (terminal === "FAILED" ? "No project data was made public. You can retry the processing job safely." : "Your uploaded project remains private and can be restarted.") : cancelRequested ? statusMessage : "You can safely close this page. Processing continues in the background and the project will be waiting in your library."}</p>
        {pollIssue && <p className="form-error" role="alert">{pollIssue}</p>}
        <div className="stage-list" aria-label="Processing stages">
          {PROCESSING_STAGES.map((stage, index) => (
            <div className={`stage-row${ready || index < activeIndex ? " is-complete" : index === activeIndex ? " is-active" : ""}`} key={stage.key}>
              <span className="stage-dot">{ready || index < activeIndex ? <Check size={10} /> : null}</span>
              <span>{stage.label}</span>
              <span>{ready || index < activeIndex ? "Done" : terminal && index === activeIndex ? "Stopped" : index === activeIndex ? cancelRequested ? "Stopping" : "Working" : "Waiting"}</span>
            </div>
          ))}
        </div>
        <div style={{ display: "flex", gap: 10, marginTop: 28 }}>
          {ready ? <Link className="button button-primary" href={`/projects/${projectId}`} data-testid="open-chart">Open chart <ExternalLink size={16} /></Link> : terminal ? <><button className="button button-primary" type="button" disabled={actionPending} onClick={() => void retry()}><RotateCcw size={15} /> {actionPending ? "Restarting…" : "Retry processing"}</button><Link className="button button-small" href="/projects">Go to projects</Link></> : <><Link className="button button-small" href="/projects">Go to projects</Link>{jobId !== "demo-job" && <button className="button button-small" type="button" disabled={actionPending || cancelRequested} onClick={() => void cancel()}><X size={15} /> {cancelRequested ? "Stopping…" : "Cancel"}</button>}</>}
        </div>
      </div>
    </main>
  );
}
