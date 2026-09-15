import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TransportProvider, useTransport } from "@/components/transport-provider";

const createDemoAudio = vi.hoisted(() => vi.fn(() => "blob:synthetic-demo"));

vi.mock("@/lib/audio", () => ({ createSyntheticDemoAudioUrl: createDemoAudio }));

class FakeAudio extends EventTarget {
  static instances: FakeAudio[] = [];
  currentTime = 0;
  duration = Number.NaN;
  paused = true;
  playbackRate = 1;
  preload = "";
  preservesPitch = true;
  src = "";
  volume = 1;
  onloadedmetadata: ((event: Event) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;

  constructor(source?: string) {
    super();
    this.src = source ?? "";
    FakeAudio.instances.push(this);
  }

  load() {
    if (!this.src) return;
    this.duration = 25.714;
    queueMicrotask(() => this.onloadedmetadata?.(new Event("loadedmetadata")));
  }

  pause() {
    this.paused = true;
  }

  async play() {
    this.paused = false;
  }

  removeAttribute(name: string) {
    if (name === "src") this.src = "";
  }
}

function Probe() {
  const transport = useTransport();
  return (
    <>
      <output data-testid="ready">{transport.audioReady ? "ready" : "blocked"}</output>
      <output data-testid="playing">{transport.playing ? "playing" : "stopped"}</output>
      <button type="button" onClick={() => transport.loadDemoAudio()}>Load demo</button>
      <button type="button" onClick={transport.togglePlayback}>Toggle playback</button>
      <button type="button" onClick={transport.clearAudioSources}>Clear</button>
    </>
  );
}

beforeEach(() => {
  FakeAudio.instances = [];
  createDemoAudio.mockClear();
  vi.stubGlobal("Audio", FakeAudio);
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("transport audio isolation", () => {
  it("does not preload demo audio outside an explicit demo surface", () => {
    render(<TransportProvider><Probe /></TransportProvider>);

    expect(createDemoAudio).not.toHaveBeenCalled();
    expect(FakeAudio.instances[0]?.src).toBe("");
    expect(screen.getByTestId("ready")).toHaveTextContent("blocked");
  });

  it("enables playback only after the requested source is ready and blocks it again when cleared", async () => {
    render(<TransportProvider><Probe /></TransportProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Load demo" }));
    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("ready"));
    expect(FakeAudio.instances[0]?.src).toBe("blob:synthetic-demo");

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByTestId("ready")).toHaveTextContent("blocked");
    expect(FakeAudio.instances[0]?.src).toBe("");
  });

  it("keeps the synthetic demo available when the media element fails", async () => {
    render(<TransportProvider><Probe /></TransportProvider>);

    fireEvent.click(screen.getByRole("button", { name: "Load demo" }));
    await waitFor(() => expect(screen.getByTestId("ready")).toHaveTextContent("ready"));
    fireEvent.click(screen.getByRole("button", { name: "Toggle playback" }));
    await waitFor(() => expect(screen.getByTestId("playing")).toHaveTextContent("playing"));

    FakeAudio.instances[0]?.onerror?.(new Event("error"));

    await waitFor(() => expect(screen.getByTestId("playing")).toHaveTextContent("stopped"));
    expect(screen.getByTestId("ready")).toHaveTextContent("ready");
  });
});
