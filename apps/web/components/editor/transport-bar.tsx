"use client";

import { ChevronLeft, ChevronRight, Gauge, Headphones, ListMusic, Pause, Play, Repeat2, Volume2 } from "lucide-react";
import { useState } from "react";
import { useTransport } from "@/components/transport-provider";
import { formatTime } from "@/lib/file-validation";

const SPEEDS = [0.25, 0.5, 0.75, 0.9, 1, 1.1, 1.25, 1.5];

export function TransportBar() {
  const transport = useTransport();
  const [mixerOpen, setMixerOpen] = useState(false);
  return (
    <footer className="editor-transport" aria-label="Playback controls">
      <div className="transport-section transport-left">
        <button className="icon-button" type="button" aria-label="Previous measure" onClick={() => transport.skipMeasure(-1)}><ChevronLeft /></button>
        <button className="transport-main-play" type="button" onClick={transport.togglePlayback} aria-label={transport.playing ? "Pause" : "Play"} data-testid="transport-play">{transport.playing ? <Pause /> : <Play />}</button>
        <button className="icon-button" type="button" aria-label="Next measure" onClick={() => transport.skipMeasure(1)}><ChevronRight /></button>
        <span className="transport-time"><strong>{formatTime(transport.currentTime)}</strong><i>/</i>{formatTime(transport.duration)}</span>
      </div>
      <div className="transport-section transport-center">
        <label className="transport-select"><Gauge /><span className="sr-only">Playback speed</span><select value={transport.playbackRate} onChange={(event) => transport.setPlaybackRate(Number(event.target.value))} data-testid="playback-rate">{SPEEDS.map((speed) => <option value={speed} key={speed}>{speed.toFixed(speed % 1 ? 2 : 1).replace(".00", ".0")}×</option>)}</select></label>
        <button className={`transport-chip${transport.loop.enabled ? " is-active" : ""}`} type="button" onClick={() => transport.setLoop({ ...transport.loop, enabled: !transport.loop.enabled })} aria-pressed={transport.loop.enabled} data-testid="loop-toggle"><Repeat2 /> Loop</button>
        <button className={`transport-chip${transport.mixer.metronome > 0 ? " is-active" : ""}`} type="button" onClick={() => transport.setMixer({ ...transport.mixer, metronome: transport.mixer.metronome > 0 ? 0 : 0.7 })} aria-pressed={transport.mixer.metronome > 0}><ListMusic /> Click</button>
      </div>
      <div className="transport-section transport-right">
        <div style={{ position: "relative" }}>
          <button className={`transport-chip${mixerOpen ? " is-active" : ""}`} type="button" onClick={() => setMixerOpen((value) => !value)} aria-expanded={mixerOpen}><Headphones /> Mixer</button>
          {mixerOpen && (
            <div className="mixer-popover">
              {(["original", "drums", "metronome"] as const).map((channel) => (
                <label className="mixer-channel" key={channel}><span><Volume2 /> {channel === "metronome" ? "Click" : channel[0].toUpperCase() + channel.slice(1)}</span><input type="range" min="0" max="1" step="0.01" value={transport.mixer[channel]} onChange={(event) => transport.setMixer({ ...transport.mixer, [channel]: Number(event.target.value) })} /><output>{Math.round(transport.mixer[channel] * 100)}</output></label>
              ))}
            </div>
          )}
        </div>
      </div>
    </footer>
  );
}
