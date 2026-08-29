"use client";

import Link from "next/link";
import { Pause, Play } from "lucide-react";
import { useTransport } from "@/components/transport-provider";
import { demoWaveform } from "@/lib/demo-data";
import { formatTime } from "@/lib/file-validation";

const notes = [
  [8, 32, false], [18, 72, true], [30, 51, true], [43, 72, true], [57, 32, false], [68, 72, true], [80, 51, true], [93, 72, true],
] as const;

export function HomeDemo() {
  const transport = useTransport();
  const visibleDuration = 8.6;
  const playhead = (transport.currentTime % visibleDuration) / visibleDuration * 100;

  return (
    <section className="demo-stage" aria-label="Interactive DrumScribe demo">
      <div className="demo-shell">
        <div className="demo-topbar">
          <div className="demo-window-dots" aria-hidden="true"><i /><i /><i /></div>
          <span className="demo-project-name">Neon Room Groove</span>
          <span className="demo-badge">112 BPM · 4/4</span>
        </div>
        <div className="mini-notation">
          <span className="sr-only">Four measures of drum notation synchronized with the waveform</span>
          <div className="staff-measures" aria-hidden="true">
            {[1, 2, 3, 4].map((measure) => (
              <div className="staff-measure" key={measure}>
                <span className="staff-measure-number">{measure}</span>
                {notes.slice((measure - 1) * 2, measure * 2).map(([left, top, cross], index) => (
                  <i className={cross ? "staff-note cross" : "staff-note"} key={index} style={{ left: `${(left % 25) * 4}%`, top }} />
                ))}
              </div>
            ))}
            <div className="demo-playhead" style={{ left: `${playhead}%` }} data-testid="home-playhead" />
          </div>
        </div>
        <div className="demo-waveform" aria-hidden="true">
          {demoWaveform.map((height, index) => <i className="wave-bar" key={index} style={{ height: `${height * 92}%` }} />)}
          <div className="demo-playhead" style={{ left: `${playhead}%` }} />
        </div>
        <div className="demo-transport">
          <div className="demo-legend"><span><i /> Audio + notation, one clock</span></div>
          <button className="transport-play" type="button" onClick={transport.togglePlayback} aria-label={transport.playing ? "Pause demo" : "Play demo"} data-testid="demo-play">
            {transport.playing ? <Pause /> : <Play />}
          </button>
          <span className="demo-time">{formatTime(transport.currentTime)} / {formatTime(visibleDuration)}</span>
        </div>
      </div>
      <div style={{ display: "flex", justifyContent: "center", marginTop: 20 }}>
        <Link className="button button-small" href="/projects/demo-groove">Open the full demo editor</Link>
      </div>
    </section>
  );
}
