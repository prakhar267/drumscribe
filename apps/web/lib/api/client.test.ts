import { afterEach, describe, expect, it, vi } from "vitest";
import { api } from "@/lib/api/client";
import { createDemoEvents } from "@/lib/demo-data";

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });

afterEach(() => vi.unstubAllGlobals());

describe("versioned API client", () => {
  it("unwraps paginated project responses and includes session credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json({ items: [{ id: "4d509a14-cd42-4ef2-96a5-1ddeca87b2f0", title: "Real project", artist: null, durationSeconds: 42, status: "READY", editVersion: 1, createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-02T00:00:00Z" }], total: 1, limit: 24, offset: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    const projects = await api.listProjects();
    expect(projects).toHaveLength(1);
    expect(projects[0]).toMatchObject({ title: "Real project", durationSeconds: 42 });
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ credentials: "include" });
  });

  it("creates an anonymous session, uploads directly, completes and starts an idempotent job", async () => {
    const projectId = "0baf1d4a-1dd1-4a24-a731-ced816712e11";
    const assetId = "e72714f3-43b4-49dc-b8e6-ae82494cd7f6";
    const jobId = "100e1146-9f72-4f97-b77a-a4f7a93e6204";
    const project = { id: projectId, title: "groove", artist: null, durationSeconds: null, status: "DRAFT", editVersion: 1, createdAt: "2026-08-01T00:00:00Z", updatedAt: "2026-08-01T00:00:00Z" };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(json({ detail: "Authentication required" }, 401))
      .mockResolvedValueOnce(json({ user: {}, expiresAt: "later", featureFlags: {} }, 201))
      .mockResolvedValueOnce(json(project, 201))
      .mockResolvedValueOnce(json({ assetId, uploadUrl: "https://storage.invalid/signed", method: "PUT", requiredHeaders: { "Content-Type": "audio/wav" } }, 201))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(json({ id: assetId, status: "VERIFIED" }))
      .mockResolvedValueOnce(json({ id: jobId, projectId, stage: "RECEIVED", friendlyStage: "Preparing audio", approximateProgress: 0, updatedAt: "2026-08-01T00:00:00Z" }, 202));
    vi.stubGlobal("fetch", fetchMock);
    const file = new File([new Uint8Array([82, 73, 70, 70])], "groove.wav", { type: "audio/wav" });
    const result = await api.createAndProcessUpload({ file, rightsConfirmed: true });
    expect(result).toEqual({ projectId, jobId });
    expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
      "/api/v1/projects",
      "/api/v1/auth/anonymous-session",
      "/api/v1/projects",
      `/api/v1/projects/${projectId}/uploads/presign`,
      "https://storage.invalid/signed",
      `/api/v1/uploads/${assetId}/complete`,
      `/api/v1/projects/${projectId}/process`,
    ]);
    expect(fetchMock.mock.calls[6][1]).toMatchObject({ headers: expect.objectContaining({ "Idempotency-Key": expect.stringContaining(projectId) }) });
  });

  it("sends only explicit dirty event operations", async () => {
    const projectId = "6fe5343a-dba5-42a1-b2b4-8a10964e5514";
    const edited = { ...createDemoEvents()[0], id: "bc64b796-b8d5-4cf8-a854-253343fcddaa", projectId, velocity: 63 };
    const deletedId = "7b6861c6-a1e2-4765-b354-4742992315c4";
    const fetchMock = vi.fn().mockResolvedValue(json({ version: 5, upserted: [], deletedIds: [deletedId], revisionId: "7a5e227b-793f-4806-b236-927c7fa20768" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.bulkUpdateEvents(projectId, { upserts: [edited], deleteIds: [deletedId], snapshot: [edited] }, 4);
    const body = JSON.parse(String(fetchMock.mock.calls[0][1]?.body)) as { upserts: unknown[]; deleteIds: string[]; expectedVersion: number };
    expect(body).toMatchObject({ deleteIds: [deletedId], expectedVersion: 4 });
    expect(body.upserts).toHaveLength(1);
  });
});
