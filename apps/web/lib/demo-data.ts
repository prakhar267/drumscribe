import type { DrumEvent, DrumProject, Instrument } from "@/lib/domain";
import { positionFromSeconds } from "@/lib/music";

export const DEMO_PROJECT_ID = "demo-groove";
export const DEMO_BPM = 112;
export const DEMO_MEASURES = 12;
export const DEMO_DURATION = DEMO_MEASURES * 4 * (60 / DEMO_BPM);

export const demoProject: DrumProject = {
  id: DEMO_PROJECT_ID,
  title: "Neon Room Groove",
  artist: "DrumScribe Studio",
  durationSeconds: DEMO_DURATION,
  bpm: DEMO_BPM,
  beatsPerMeasure: 4,
  status: "READY",
  createdAt: "2026-08-28T09:20:00.000Z",
  updatedAt: "2026-08-29T04:12:00.000Z",
  reviewCount: 5,
};

function event(id: string, instrument: Instrument, beat: number, velocity: number, confidence = 0.96): DrumEvent {
  const time = beat * (60 / DEMO_BPM);
  return {
    id,
    projectId: DEMO_PROJECT_ID,
    instrument,
    onsetSeconds: time + (id.charCodeAt(id.length - 1) % 3 - 1) * 0.006,
    durationSeconds: 0.08,
    velocity,
    confidence,
    source: "MODEL",
    ...positionFromSeconds(time, DEMO_BPM),
    subdivision: "1/16",
    quantizedOnset: time,
    manuallyEdited: false,
    createdAt: "2026-08-28T09:20:00.000Z",
    updatedAt: "2026-08-28T09:20:00.000Z",
  };
}

export function createDemoEvents() {
  const events: DrumEvent[] = [];
  let id = 0;
  const add = (instrument: Instrument, beat: number, velocity: number, confidence?: number) => {
    events.push(event(`demo-${String(id++).padStart(3, "0")}`, instrument, beat, velocity, confidence));
  };
  for (let measure = 0; measure < DEMO_MEASURES; measure += 1) {
    const base = measure * 4;
    for (let eighth = 0; eighth < 8; eighth += 1) {
      const open = measure % 4 === 3 && eighth === 7;
      add(open ? "OPEN_HIHAT" : "CLOSED_HIHAT", base + eighth / 2, eighth % 2 ? 72 : 86, measure === 7 && eighth === 5 ? 0.51 : 0.93);
    }
    add("KICK", base, 112);
    add("KICK", base + (measure % 3 === 1 ? 1.5 : 2.5), 94, measure === 5 ? 0.62 : 0.9);
    if (measure % 4 === 2) add("KICK", base + 3.5, 84);
    add("SNARE", base + 1, 108);
    add("SNARE", base + 3, 112, measure === 8 ? 0.54 : 0.95);
    if (measure === 3 || measure === 7 || measure === 11) {
      add("HIGH_TOM", base + 3.25, 91, 0.68);
      add("MID_TOM", base + 3.5, 96, 0.73);
      add("FLOOR_TOM", base + 3.75, 102, 0.65);
    }
    if (measure % 4 === 0) add("CRASH", base, 118);
    if (measure >= 8) add("RIDE", base + 0.5, 82);
  }
  return events;
}

export const demoProjects: DrumProject[] = [
  demoProject,
  {
    ...demoProject,
    id: "paper-kites",
    title: "Paper Kites",
    artist: "Studio take",
    durationSeconds: 203,
    bpm: 126,
    reviewCount: 2,
    updatedAt: "2026-08-27T14:30:00.000Z",
  },
  {
    ...demoProject,
    id: "sunday-drive",
    title: "Sunday Drive",
    artist: "Lesson prep",
    durationSeconds: 248,
    bpm: 94,
    reviewCount: 8,
    updatedAt: "2026-08-24T08:15:00.000Z",
  },
  {
    ...demoProject,
    id: "glass-houses",
    title: "Glass Houses",
    artist: "Rough mix",
    durationSeconds: 176,
    bpm: 138,
    reviewCount: 0,
    updatedAt: "2026-08-20T18:05:00.000Z",
  },
];

export const demoWaveform = Array.from({ length: 160 }, (_, index) => {
  const phrase = (Math.sin(index * 0.41) + Math.sin(index * 0.13 + 1.2) + 2) / 4;
  const accent = index % 16 === 0 ? 0.97 : index % 8 === 0 ? 0.78 : 0;
  return Math.min(1, Math.max(0.1, phrase * 0.66 + accent));
});
