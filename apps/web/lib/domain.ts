export const INSTRUMENTS = [
  "CRASH",
  "RIDE",
  "RIDE_BELL",
  "OPEN_HIHAT",
  "CLOSED_HIHAT",
  "PEDAL_HIHAT",
  "HIGH_TOM",
  "MID_TOM",
  "LOW_TOM",
  "FLOOR_TOM",
  "CROSS_STICK",
  "SNARE",
  "KICK",
] as const;

export type Instrument = (typeof INSTRUMENTS)[number];

export const EDITOR_ROWS: Instrument[] = [
  "CRASH",
  "RIDE",
  "RIDE_BELL",
  "OPEN_HIHAT",
  "CLOSED_HIHAT",
  "PEDAL_HIHAT",
  "HIGH_TOM",
  "MID_TOM",
  "LOW_TOM",
  "FLOOR_TOM",
  "CROSS_STICK",
  "SNARE",
  "KICK",
];

export const INSTRUMENT_LABELS: Record<Instrument, string> = {
  KICK: "Kick",
  SNARE: "Snare",
  CROSS_STICK: "Cross-stick",
  CLOSED_HIHAT: "Closed hi-hat",
  OPEN_HIHAT: "Open hi-hat",
  PEDAL_HIHAT: "Pedal hi-hat",
  RIDE: "Ride",
  RIDE_BELL: "Ride bell",
  CRASH: "Crash",
  HIGH_TOM: "High tom",
  MID_TOM: "Mid tom",
  LOW_TOM: "Low tom",
  FLOOR_TOM: "Floor tom",
};

export const GM_PERCUSSION_MAP: Record<Instrument, number> = {
  KICK: 36,
  SNARE: 38,
  CROSS_STICK: 37,
  CLOSED_HIHAT: 42,
  OPEN_HIHAT: 46,
  PEDAL_HIHAT: 44,
  RIDE: 51,
  RIDE_BELL: 53,
  CRASH: 49,
  HIGH_TOM: 50,
  MID_TOM: 47,
  LOW_TOM: 45,
  FLOOR_TOM: 43,
};

export type EventSource = "MODEL" | "MANUAL" | "IMPORTED";
export type NotationSubdivision = "1/4" | "1/8" | "1/16" | "1/32" | "1/8T" | "1/16T";

export interface DrumEvent {
  id: string;
  projectId: string;
  instrument: Instrument;
  onsetSeconds: number;
  durationSeconds: number;
  velocity: number;
  confidence: number;
  source: EventSource;
  beatPosition: number;
  measureIndex: number;
  subdivision: NotationSubdivision;
  quantizedOnset: number;
  manuallyEdited: boolean;
  createdAt: string;
  updatedAt: string;
}

export type ProjectStatus = "PROCESSING" | "READY" | "FAILED" | "CANCELLED";

export interface DrumProject {
  id: string;
  title: string;
  artist?: string;
  durationSeconds: number;
  bpm: number;
  beatsPerMeasure: number;
  status: ProjectStatus;
  createdAt: string;
  updatedAt: string;
  reviewCount: number;
}

export type SnapValue = "off" | "quarter" | "eighth" | "sixteenth" | "thirty-second" | "triplet";

export interface MixerState {
  original: number;
  drums: number;
  metronome: number;
}

export interface LoopRange {
  enabled: boolean;
  start: number;
  end: number;
}

export interface TempoPoint {
  timeSeconds: number;
  bpm: number;
  beatsPerMeasure: number;
}

export const PROCESSING_STAGES = [
  { key: "VALIDATING", label: "Preparing audio", weight: 8 },
  { key: "NORMALIZING", label: "Balancing the recording", weight: 9 },
  { key: "SEPARATING_DRUMS", label: "Isolating drums", weight: 28 },
  { key: "TRANSCRIBING", label: "Listening for drum hits", weight: 25 },
  { key: "DETECTING_BEATS", label: "Finding the pulse", weight: 9 },
  { key: "QUANTIZING", label: "Building the rhythm", weight: 8 },
  { key: "GENERATING_SCORE", label: "Creating your chart", weight: 8 },
  { key: "FINALIZING", label: "Almost ready", weight: 5 },
] as const;

export type ProcessingStage = (typeof PROCESSING_STAGES)[number]["key"] | "RECEIVED" | "READY" | "FAILED" | "CANCELLED";

export interface JobStatus {
  id: string;
  projectId: string;
  stage: ProcessingStage;
  approximateProgress: number;
  message: string;
  updatedAt: string;
  errorCode?: string;
}
