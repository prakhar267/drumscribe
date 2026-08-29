import { createDemoEvents, demoProject, demoProjects } from "@/lib/demo-data";
import type { DrumEvent, DrumProject, Instrument, JobStatus, ProcessingStage, RequantizeMode, TimingBeat, TimingMap, TimingSegment } from "@/lib/domain";

const API_BASE = (process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1").replace(/\/$/, "");
const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE !== "false";
const STORAGE_KEY = "drumscribe:demo-events:v2";
const DEMO_PROJECT_STORAGE_KEY = "drumscribe:demo-projects:v1";

interface EventChanges {
  upserts: DrumEvent[];
  deleteIds: string[];
  /** The complete post-edit chart, used only by the deterministic local demo. */
  snapshot: DrumEvent[];
}

export interface ProjectRevision {
  id: string;
  sequence: number;
  kind: string;
  label: string;
  eventCount: number;
  createdAt: string;
}

export interface AdminJobDiagnostics {
  job: WireJob & {
    retryCount: number;
    startedAt: string | null;
    finishedAt: string | null;
  };
  providerVersions: Record<string, unknown>;
  providerMetadata: Record<string, unknown>;
  totalProviderCost: number | null;
  providerCostCurrency: string | null;
  stageTimings: Record<string, unknown>;
  technicalErrorDetail: string | null;
  assets: Array<{
    id: string;
    kind: string;
    status: string;
    contentType: string | null;
    sizeBytes: number | null;
    durationSeconds: number | null;
    codec: string | null;
    sampleRate: number | null;
    channels: number | null;
  }>;
  modelRuns: Array<Record<string, unknown>>;
  eventCount: number;
  lowConfidenceEventCount: number;
}

class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

interface WireProject {
  id: string;
  title: string;
  artist: string | null;
  durationSeconds: number | null;
  status: "DRAFT" | "UPLOADING" | "UPLOADED" | "PROCESSING" | "READY" | "FAILED" | "CANCELLED";
  editVersion: number;
  createdAt: string;
  updatedAt: string;
}

interface WireEvent {
  id: string;
  instrument: Instrument;
  onsetSeconds: number;
  durationSeconds: number;
  velocity: number;
  confidence: number | null;
  source: "AI" | "USER" | "IMPORT";
  beatPosition: number;
  measureIndex: number;
  subdivision: "1/4" | "1/8" | "1/16" | "1/32" | "1/8T" | "1/16T";
  quantizedOnset: number;
  manuallyEdited: boolean;
  createdAt: string;
  updatedAt: string;
}

interface WireEvents {
  transcriptionId: string;
  version: number;
  tempoBpm: number;
  timeSignatureNumerator: number;
  timeSignatureDenominator: number;
  items: WireEvent[];
}

interface WireJob {
  id: string;
  projectId: string;
  stage: ProcessingStage;
  friendlyStage: string;
  approximateProgress: number;
  updatedAt: string;
  errorCode?: string | null;
  errorMessage?: string | null;
}

interface WireAccount {
  id: string;
  email: string | null;
  kind: "ANONYMOUS" | "REGISTERED";
  role: "USER" | "ADMIN";
  entitlement: string;
  allowModelImprovement: boolean;
  createdAt: string;
}

async function parseError(response: Response) {
  const problem = await response.json().catch(() => null) as { detail?: string; message?: string; title?: string } | null;
  return problem?.detail ?? problem?.message ?? problem?.title ?? `Request failed (${response.status})`;
}

async function bootstrapAnonymousSession() {
  const response = await fetch(`${API_BASE}/auth/anonymous-session`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
  });
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
}

async function request<T>(path: string, init?: RequestInit, retryAuth = true): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (response.status === 401 && retryAuth && path !== "/auth/anonymous-session") {
    await bootstrapAnonymousSession();
    return request<T>(path, init, false);
  }
  if (!response.ok) throw new ApiError(await parseError(response), response.status);
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function isDemoUnavailable(error: unknown) {
  return error instanceof TypeError;
}

function demoTiming(project: DrumProject): TimingMap {
  const beatDuration = 60 / project.bpm;
  const beats: TimingBeat[] = [];
  for (let time = 0, index = 0; time <= project.durationSeconds + beatDuration; time += beatDuration, index += 1) {
    const beatInMeasure = index % project.beatsPerMeasure + 1;
    beats.push({
      timeSeconds: Number(time.toFixed(6)),
      beatInMeasure,
      measureIndex: Math.floor(index / project.beatsPerMeasure),
      isDownbeat: beatInMeasure === 1,
      confidence: null,
    });
  }
  return {
    timingVersion: 1,
    transcriptionVersion: 1,
    barOneSeconds: 0,
    segments: [{
      startSeconds: 0,
      bpm: project.bpm,
      timeSignatureNumerator: project.beatsPerMeasure,
      timeSignatureDenominator: 4,
      startMeasure: 0,
    }],
    beats,
    source: "AI",
    requantizedEventCount: 0,
    revisionId: null,
  };
}

function readDemoEvents() {
  if (typeof window === "undefined") return createDemoEvents();
  const value = window.localStorage.getItem(STORAGE_KEY);
  if (!value) return createDemoEvents();
  try {
    return JSON.parse(value) as DrumEvent[];
  } catch {
    return createDemoEvents();
  }
}

function readDemoProject(projectId: string) {
  const fallback = demoProjects.find((project) => project.id === projectId) ?? demoProject;
  if (typeof window === "undefined") return { ...fallback, id: projectId };
  try {
    const stored = JSON.parse(window.localStorage.getItem(DEMO_PROJECT_STORAGE_KEY) ?? "{}") as Record<string, Partial<DrumProject>>;
    return { ...fallback, ...stored[projectId], id: projectId };
  } catch {
    return { ...fallback, id: projectId };
  }
}

function writeDemoProject(project: DrumProject) {
  if (typeof window === "undefined") return;
  let stored: Record<string, Partial<DrumProject>> = {};
  try { stored = JSON.parse(window.localStorage.getItem(DEMO_PROJECT_STORAGE_KEY) ?? "{}") as Record<string, Partial<DrumProject>>; } catch { /* Replace malformed demo state. */ }
  stored[project.id] = project;
  window.localStorage.setItem(DEMO_PROJECT_STORAGE_KEY, JSON.stringify(stored));
}

function projectStatus(status: WireProject["status"]): DrumProject["status"] {
  if (status === "READY" || status === "FAILED" || status === "CANCELLED") return status;
  return "PROCESSING";
}

function toProject(project: WireProject, tempoBpm = 120, beatsPerMeasure = 4, reviewCount = 0): DrumProject {
  return {
    id: project.id,
    title: project.title,
    artist: project.artist ?? undefined,
    durationSeconds: project.durationSeconds ?? 0,
    bpm: tempoBpm,
    beatsPerMeasure,
    status: projectStatus(project.status),
    createdAt: project.createdAt,
    updatedAt: project.updatedAt,
    reviewCount,
  };
}

function toEvent(event: WireEvent, projectId: string): DrumEvent {
  return {
    ...event,
    projectId,
    confidence: event.confidence ?? 1,
    source: event.source === "AI" ? "MODEL" : event.source === "USER" ? "MANUAL" : "IMPORTED",
    subdivision: event.subdivision,
  };
}

function toEventWrite(event: DrumEvent) {
  return {
    id: event.id,
    instrument: event.instrument,
    onsetSeconds: event.onsetSeconds,
    durationSeconds: event.durationSeconds,
    velocity: event.velocity,
    confidence: event.confidence,
    source: event.source === "MODEL" ? "AI" : event.source === "MANUAL" ? "USER" : "IMPORT",
    beatPosition: event.beatPosition,
    measureIndex: event.measureIndex,
    subdivision: event.subdivision,
    quantizedOnset: event.quantizedOnset,
  };
}

function toJobStatus(job: WireJob): JobStatus {
  return {
    id: job.id,
    projectId: job.projectId,
    stage: job.stage,
    approximateProgress: job.approximateProgress,
    message: job.errorMessage ?? job.friendlyStage,
    updatedAt: job.updatedAt,
    errorCode: job.errorCode ?? undefined,
  };
}

export const api = {
  async requestMagicLink(email: string) {
    try {
      return await request<{ accepted: true; devToken?: string }>("/auth/magic-link/request", { method: "POST", body: JSON.stringify({ email }) });
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
      return { accepted: true as const };
    }
  },

  async consumeMagicLink(token: string) {
    try {
      return await request<{ user: { id: string; email: string | null }; expiresAt: string }>("/auth/magic-link/consume", { method: "POST", body: JSON.stringify({ token }) });
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
      return { user: { id: "demo-user", email: "demo@drumscribe.local" }, expiresAt: new Date(Date.now() + 86_400_000).toISOString() };
    }
  },

  async listProjects(): Promise<DrumProject[]> {
    try {
      const response = await request<{ items: WireProject[]; total: number }>("/projects");
      return response.items.map((project) => toProject(project));
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
      return demoProjects.map((project) => readDemoProject(project.id));
    }
  },

  async getProject(projectId: string): Promise<{ project: DrumProject; events: DrumEvent[]; revision: number }> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) {
      return { project: readDemoProject(projectId), events: readDemoEvents(), revision: 1 };
    }
    try {
      const [wireProject, wireEvents] = await Promise.all([
        request<WireProject>(`/projects/${encodeURIComponent(projectId)}`),
        request<WireEvents>(`/projects/${encodeURIComponent(projectId)}/events`),
      ]);
      const events = wireEvents.items.map((event) => toEvent(event, projectId));
      return {
        project: toProject(wireProject, wireEvents.tempoBpm, wireEvents.timeSignatureNumerator, events.filter((event) => event.confidence < 0.7).length),
        events,
        revision: wireEvents.version,
      };
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
      return { project: readDemoProject(projectId), events: readDemoEvents(), revision: 1 };
    }
  },

  async bulkUpdateEvents(projectId: string, changes: EventChanges, revision: number) {
    if (typeof window !== "undefined" && DEMO_MODE && demoProjects.some((project) => project.id === projectId)) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(changes.snapshot));
      return { revision: revision + 1, savedAt: new Date().toISOString() };
    }
    const response = await request<{ version: number; deletedIds: string[] }>(`/projects/${encodeURIComponent(projectId)}/events/bulk`, {
      method: "PATCH",
      body: JSON.stringify({
        upserts: changes.upserts.map(toEventWrite),
        deleteIds: changes.deleteIds,
        expectedVersion: revision,
        revisionLabel: "Editor autosave",
      }),
    });
    return { revision: response.version, savedAt: new Date().toISOString() };
  },

  async getTiming(projectId: string): Promise<TimingMap> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) {
      return demoTiming(readDemoProject(projectId));
    }
    return request<TimingMap>(`/projects/${encodeURIComponent(projectId)}/timing`);
  },

  async updateTiming(projectId: string, input: {
    expectedVersion: number;
    barOneSeconds: number;
    segments: TimingSegment[];
    beats: TimingBeat[];
    requantize: RequantizeMode;
    measureStart?: number;
    measureEnd?: number;
    preserveManualEdits: boolean;
  }): Promise<TimingMap> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) {
      return {
        timingVersion: input.expectedVersion + 1,
        transcriptionVersion: input.expectedVersion + 1,
        barOneSeconds: input.barOneSeconds,
        segments: input.segments,
        beats: input.beats,
        source: "MANUAL",
        requantizedEventCount: 0,
        revisionId: null,
      };
    }
    return request<TimingMap>(`/projects/${encodeURIComponent(projectId)}/timing`, {
      method: "PATCH",
      body: JSON.stringify(input),
    });
  },

  async resetTiming(projectId: string, input: {
    expectedVersion: number;
    requantize: RequantizeMode;
    measureStart?: number;
    measureEnd?: number;
    preserveManualEdits: boolean;
  }): Promise<TimingMap> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) {
      return demoTiming(readDemoProject(projectId));
    }
    return request<TimingMap>(`/projects/${encodeURIComponent(projectId)}/timing/reset`, {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  async createAndProcessUpload(input: { file: File; title?: string; rightsConfirmed: true }) {
    let projectCreated = false;
    try {
      const title = (input.title ?? input.file.name.replace(/\.[^.]+$/, "")).trim() || "Untitled transcription";
      const project = await request<WireProject>("/projects", { method: "POST", body: JSON.stringify({ title }) });
      projectCreated = true;
      const signed = await request<{ assetId: string; uploadUrl: string; method: "PUT"; requiredHeaders: Record<string, string> }>(`/projects/${project.id}/uploads/presign`, {
        method: "POST",
        body: JSON.stringify({
          filename: input.file.name,
          contentType: input.file.type,
          sizeBytes: input.file.size,
          rightToUploadConfirmed: input.rightsConfirmed,
        }),
      });
      const upload = await fetch(signed.uploadUrl, { method: signed.method, headers: signed.requiredHeaders, body: input.file });
      if (!upload.ok) throw new ApiError(await parseError(upload), upload.status);
      await request(`/uploads/${signed.assetId}/complete`, { method: "POST", body: JSON.stringify({ etag: upload.headers.get("etag") }) });
      const idempotencyKey = `process-${project.id}-${signed.assetId}`.slice(0, 128);
      const job = await request<WireJob>(`/projects/${project.id}/process`, {
        method: "POST",
        headers: { "Idempotency-Key": idempotencyKey },
        body: JSON.stringify({}),
      });
      return { projectId: project.id, jobId: job.id };
    } catch (error) {
      if (!projectCreated && DEMO_MODE && isDemoUnavailable(error)) return { projectId: demoProject.id, jobId: "demo-job" };
      throw error;
    }
  },

  async getJob(jobId: string): Promise<JobStatus> {
    if (DEMO_MODE && jobId === "demo-job") return { id: jobId, projectId: demoProject.id, stage: "READY", approximateProgress: 100, message: "Your chart is ready", updatedAt: new Date().toISOString() };
    try {
      const job = await request<WireJob>(`/jobs/${encodeURIComponent(jobId)}`);
      return toJobStatus(job);
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
      return { id: jobId, projectId: demoProject.id, stage: "READY", approximateProgress: 100, message: "Your chart is ready", updatedAt: new Date().toISOString() };
    }
  },

  async retryJob(jobId: string) {
    return toJobStatus(await request<WireJob>(`/jobs/${encodeURIComponent(jobId)}/retry`, { method: "POST", body: JSON.stringify({}) }));
  },

  async cancelJob(jobId: string) {
    return toJobStatus(await request<WireJob>(`/jobs/${encodeURIComponent(jobId)}/cancel`, { method: "POST", body: JSON.stringify({}) }));
  },

  async getAudioSources(projectId: string): Promise<{ originalUrl: string; drumsUrl?: string; expiresAt: string } | null> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return null;
    try {
      const original = await request<{ url: string; expiresAt: string }>(`/projects/${encodeURIComponent(projectId)}/audio/original/url`);
      let drumsUrl: string | undefined;
      let drumsExpiresAt: string | undefined;
      try {
        const drums = await request<{ url: string; expiresAt: string }>(`/projects/${encodeURIComponent(projectId)}/audio/drums/url`);
        drumsUrl = drums.url;
        drumsExpiresAt = drums.expiresAt;
      } catch (error) {
        if (!(error instanceof ApiError && error.status === 404)) throw error;
      }
      const expiresAt = drumsExpiresAt && Date.parse(drumsExpiresAt) < Date.parse(original.expiresAt) ? drumsExpiresAt : original.expiresAt;
      return { originalUrl: original.url, drumsUrl, expiresAt };
    } catch (error) {
      if (DEMO_MODE && isDemoUnavailable(error)) return null;
      throw error;
    }
  },

  async getWaveformPeaks(projectId: string): Promise<number[] | null> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return null;
    try {
      const signed = await request<{ url: string }>(`/projects/${encodeURIComponent(projectId)}/waveform/url`);
      const response = await fetch(signed.url);
      if (!response.ok) throw new ApiError(await parseError(response), response.status);
      const envelope = await response.json() as { peaks?: [number, number][] };
      if (!envelope.peaks?.length) return null;
      const bucketSize = Math.max(1, Math.ceil(envelope.peaks.length / 320));
      const heights: number[] = [];
      for (let index = 0; index < envelope.peaks.length; index += bucketSize) {
        heights.push(Math.max(...envelope.peaks.slice(index, index + bucketSize).flatMap(([low, high]) => [Math.abs(low), Math.abs(high)])));
      }
      return heights;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      if (DEMO_MODE && isDemoUnavailable(error)) return null;
      throw error;
    }
  },

  async generateExport(projectId: string, format: "MIDI" | "MUSICXML" | "PDF"): Promise<string | null> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return null;
    const idempotencyKey = `export-${projectId}-${format}-${Date.now()}`.slice(0, 128);
    const created = await request<{ id: string; status: "QUEUED" | "GENERATING" | "READY" | "FAILED" | "CANCELLED" }>(`/projects/${encodeURIComponent(projectId)}/exports`, {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ format }),
    });
    let status = created.status;
    for (let attempt = 0; attempt < 90 && !["READY", "FAILED", "CANCELLED"].includes(status); attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      status = (await request<{ status: typeof status }>(`/exports/${created.id}`)).status;
    }
    if (status !== "READY") throw new Error(status === "FAILED" ? "The export could not be generated." : "The export is not ready yet.");
    return (await request<{ url: string }>(`/exports/${created.id}/download`)).url;
  },

  async updateProject(projectId: string, changes: { title?: string; artist?: string | null }) {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) {
      const next = { ...readDemoProject(projectId), ...changes, artist: changes.artist === null ? undefined : changes.artist, updatedAt: new Date().toISOString() };
      writeDemoProject(next);
      return next;
    }
    return toProject(await request<WireProject>(`/projects/${encodeURIComponent(projectId)}`, { method: "PATCH", body: JSON.stringify(changes) }));
  },

  async duplicateProject(projectId: string, title?: string) {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return null;
    return toProject(await request<WireProject>(`/projects/${encodeURIComponent(projectId)}/duplicate`, { method: "POST", body: JSON.stringify({ title }) }));
  },

  async deleteProject(projectId: string) {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return;
    await request(`/projects/${encodeURIComponent(projectId)}`, { method: "DELETE" });
  },

  async restoreProject(projectId: string) {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return;
    await request(`/projects/${encodeURIComponent(projectId)}/restore`, { method: "POST", body: JSON.stringify({}) });
  },

  async listRevisions(projectId: string): Promise<ProjectRevision[]> {
    if (DEMO_MODE && demoProjects.some((project) => project.id === projectId)) return [];
    return (await request<{ items: ProjectRevision[] }>(`/projects/${encodeURIComponent(projectId)}/revisions`)).items;
  },

  async restoreRevision(projectId: string, revisionId: string) {
    return request<{ version: number; eventCount: number }>(`/projects/${encodeURIComponent(projectId)}/revisions/${encodeURIComponent(revisionId)}/restore`, { method: "POST", body: JSON.stringify({}) });
  },

  async getAdminJobDiagnostics(jobId: string): Promise<AdminJobDiagnostics> {
    return request<AdminJobDiagnostics>(`/admin/jobs/${encodeURIComponent(jobId)}`);
  },

  async setModelImprovementConsent(allowModelImprovement: boolean) {
    try {
      await request("/account/me", { method: "PATCH", body: JSON.stringify({ allowModelImprovement }) });
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
    }
  },

  async getAccount(): Promise<WireAccount> {
    try {
      return await request<WireAccount>("/account/me");
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
      return { id: "demo-user", email: null, kind: "ANONYMOUS", role: "USER", entitlement: "FREE_BETA", allowModelImprovement: false, createdAt: new Date().toISOString() };
    }
  },

  async logout() {
    try {
      await request("/auth/logout", { method: "POST" });
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
    }
  },

  async deleteAccount() {
    try {
      await request("/account", { method: "DELETE", body: JSON.stringify({ confirmation: "DELETE MY ACCOUNT" }) });
    } catch (error) {
      if (!DEMO_MODE || !isDemoUnavailable(error)) throw error;
    }
  },

  clearDemoEdits() {
    if (typeof window !== "undefined") {
      window.localStorage.removeItem(STORAGE_KEY);
      window.localStorage.removeItem(DEMO_PROJECT_STORAGE_KEY);
    }
  },
};
