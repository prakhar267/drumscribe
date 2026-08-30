import {
  EDITOR_ROWS,
  GM_PERCUSSION_MAP,
  INSTRUMENT_LABELS,
  INSTRUMENTS,
  type DrumEvent,
  type Instrument,
  type SnapValue,
} from "@/lib/domain";

const SNAP_DIVISIONS: Record<Exclude<SnapValue, "off">, number> = {
  quarter: 1,
  eighth: 2,
  sixteenth: 4,
  "thirty-second": 8,
  triplet: 3,
};

export function snapSeconds(time: number, bpm: number, snap: SnapValue): number {
  if (snap === "off") return Math.max(0, time);
  const step = 60 / bpm / SNAP_DIVISIONS[snap];
  return Math.max(0, Math.round(time / step) * step);
}

export function gridStepSeconds(bpm: number, snap: SnapValue): number {
  if (snap === "off") return 0.01;
  return 60 / bpm / SNAP_DIVISIONS[snap];
}

export function positionFromSeconds(time: number, bpm: number, beatsPerMeasure = 4) {
  const beatFloat = time / (60 / bpm);
  const measureIndex = Math.floor(beatFloat / beatsPerMeasure);
  const beatInMeasure = beatFloat - measureIndex * beatsPerMeasure;
  return {
    measureIndex,
    beatPosition: beatInMeasure,
  };
}

export function moveEvent(
  event: DrumEvent,
  changes: Partial<Pick<DrumEvent, "instrument" | "onsetSeconds" | "quantizedOnset" | "velocity" | "subdivision">>,
  bpm: number,
): DrumEvent {
  const quantizedOnset = changes.quantizedOnset ?? changes.onsetSeconds ?? event.quantizedOnset;
  return {
    ...event,
    ...changes,
    ...positionFromSeconds(quantizedOnset, bpm),
    manuallyEdited: true,
    updatedAt: new Date().toISOString(),
  };
}

export function createEvent(input: {
  id: string;
  projectId: string;
  instrument: Instrument;
  time: number;
  bpm: number;
  velocity?: number;
  snap?: SnapValue;
}): DrumEvent {
  const now = new Date().toISOString();
  return {
    id: input.id,
    projectId: input.projectId,
    instrument: input.instrument,
    onsetSeconds: input.time,
    quantizedOnset: input.time,
    durationSeconds: 0.08,
    velocity: input.velocity ?? 96,
    confidence: 1,
    source: "MANUAL",
    ...positionFromSeconds(input.time, input.bpm),
    subdivision: ({ off: "1/16", quarter: "1/4", eighth: "1/8", sixteenth: "1/16", "thirty-second": "1/32", triplet: "1/8T" } as const)[input.snap ?? "sixteenth"],
    manuallyEdited: true,
    createdAt: now,
    updatedAt: now,
  };
}

export function lowConfidenceEvents(events: DrumEvent[], threshold = 0.7) {
  return events.filter((event) => event.confidence < threshold).sort((a, b) => a.quantizedOnset - b.quantizedOnset);
}

function eventWriteSignature(event: DrumEvent) {
  return JSON.stringify([
    event.instrument,
    event.onsetSeconds,
    event.durationSeconds,
    event.velocity,
    event.confidence,
    event.source,
    event.beatPosition,
    event.measureIndex,
    event.subdivision,
    event.quantizedOnset,
  ]);
}

/** Compute the smallest API edit batch without rewriting untouched model events. */
export function diffDrumEvents(previous: DrumEvent[], current: DrumEvent[]) {
  const previousById = new Map(previous.map((event) => [event.id, event]));
  const currentIds = new Set(current.map((event) => event.id));
  return {
    upserts: current.filter((event) => {
      const saved = previousById.get(event.id);
      return !saved || eventWriteSignature(saved) !== eventWriteSignature(event);
    }),
    deleteIds: previous.filter((event) => !currentIds.has(event.id)).map((event) => event.id),
  };
}

function escapeXml(value: string) {
  return value.replace(/[<>&'\"]/g, (character) => ({
    "<": "&lt;",
    ">": "&gt;",
    "&": "&amp;",
    "'": "&apos;",
    '\"': "&quot;",
  })[character] ?? character);
}

const DISPLAY_POSITION: Record<Instrument, { step: string; octave: number }> = {
  KICK: { step: "F", octave: 4 },
  SNARE: { step: "C", octave: 5 },
  CROSS_STICK: { step: "C", octave: 5 },
  CLOSED_HIHAT: { step: "G", octave: 5 },
  OPEN_HIHAT: { step: "G", octave: 5 },
  PEDAL_HIHAT: { step: "D", octave: 4 },
  RIDE: { step: "F", octave: 5 },
  RIDE_BELL: { step: "F", octave: 5 },
  CRASH: { step: "A", octave: 5 },
  HIGH_TOM: { step: "E", octave: 5 },
  MID_TOM: { step: "D", octave: 5 },
  LOW_TOM: { step: "A", octave: 4 },
  FLOOR_TOM: { step: "G", octave: 4 },
  TAMBOURINE: { step: "E", octave: 6 },
};

export const MUSIC_XML_DIVISIONS = 480;

/** MusicXML IDs are XML names, so canonical UUIDs and imported IDs need a safe prefix. */
export function musicXmlIdForEvent(eventId: string) {
  const encoded = Array.from(eventId, (character) => character.codePointAt(0)?.toString(16) ?? "0").join("-");
  return `drumscribe-event-${encoded || "empty"}`;
}

interface DurationDescriptor {
  type: "whole" | "half" | "quarter" | "eighth" | "16th" | "32nd" | "64th";
  dots?: number;
  tuplet?: { actual: number; normal: number };
}

const DURATION_DESCRIPTORS: Array<[number, DurationDescriptor]> = [
  [MUSIC_XML_DIVISIONS * 4, { type: "whole" }],
  [MUSIC_XML_DIVISIONS * 3, { type: "half", dots: 1 }],
  [MUSIC_XML_DIVISIONS * 2, { type: "half" }],
  [MUSIC_XML_DIVISIONS * 3 / 2, { type: "quarter", dots: 1 }],
  [MUSIC_XML_DIVISIONS, { type: "quarter" }],
  [MUSIC_XML_DIVISIONS * 3 / 4, { type: "eighth", dots: 1 }],
  [MUSIC_XML_DIVISIONS / 2, { type: "eighth" }],
  [MUSIC_XML_DIVISIONS / 3, { type: "eighth", tuplet: { actual: 3, normal: 2 } }],
  [MUSIC_XML_DIVISIONS / 4, { type: "16th" }],
  [MUSIC_XML_DIVISIONS / 6, { type: "16th", tuplet: { actual: 3, normal: 2 } }],
  [MUSIC_XML_DIVISIONS / 8, { type: "32nd" }],
  [MUSIC_XML_DIVISIONS / 16, { type: "64th" }],
];

const SUBDIVISION_TICKS: Record<DrumEvent["subdivision"], number> = {
  "1/4": MUSIC_XML_DIVISIONS,
  "1/8": MUSIC_XML_DIVISIONS / 2,
  "1/16": MUSIC_XML_DIVISIONS / 4,
  "1/32": MUSIC_XML_DIVISIONS / 8,
  "1/8T": MUSIC_XML_DIVISIONS / 3,
  "1/16T": MUSIC_XML_DIVISIONS / 6,
};

function durationMarkup(ticks: number) {
  const descriptor = DURATION_DESCRIPTORS.find(([candidate]) => candidate === ticks)?.[1];
  if (!descriptor) return "";
  const dots = "<dot/>".repeat(descriptor.dots ?? 0);
  const tuplet = descriptor.tuplet
    ? `<time-modification><actual-notes>${descriptor.tuplet.actual}</actual-notes><normal-notes>${descriptor.tuplet.normal}</normal-notes></time-modification>`
    : "";
  return `<type>${descriptor.type}</type>${dots}${tuplet}`;
}

function restMarkup(ticks: number) {
  const chunks: string[] = [];
  let remaining = ticks;
  while (remaining > 0) {
    const exact = DURATION_DESCRIPTORS.find(([candidate]) => candidate === remaining);
    const candidate = exact ?? DURATION_DESCRIPTORS.find(([duration]) => duration < remaining);
    const duration = candidate?.[0] ?? remaining;
    chunks.push(`<note><rest/><duration>${duration}</duration><voice>1</voice>${durationMarkup(duration)}<staff>1</staff></note>`);
    remaining -= duration;
  }
  return chunks.join("");
}

interface NoteCluster {
  tick: number;
  duration: number;
  events: DrumEvent[];
}

function beamCount(duration: number) {
  if (duration <= MUSIC_XML_DIVISIONS / 8) return 3;
  if (duration <= MUSIC_XML_DIVISIONS / 4) return 2;
  if (duration <= MUSIC_XML_DIVISIONS / 2) return 1;
  return 0;
}

function beamMarkup(clusters: NoteCluster[], index: number) {
  const cluster = clusters[index];
  const previous = clusters[index - 1];
  const next = clusters[index + 1];
  const levels = beamCount(cluster.duration);
  const sameBeat = (left: NoteCluster, right: NoteCluster) => (
    left.tick + left.duration === right.tick
    && Math.floor(left.tick / MUSIC_XML_DIVISIONS) === Math.floor(right.tick / MUSIC_XML_DIVISIONS)
  );
  return Array.from({ length: levels }, (_, beamIndex) => {
    const level = beamIndex + 1;
    const joinsPrevious = Boolean(previous && beamCount(previous.duration) >= level && sameBeat(previous, cluster));
    const joinsNext = Boolean(next && beamCount(next.duration) >= level && sameBeat(cluster, next));
    if (!joinsPrevious && !joinsNext) return "";
    const value = joinsPrevious && joinsNext ? "continue" : joinsNext ? "begin" : "end";
    return `<beam number="${level}">${value}</beam>`;
  }).join("");
}

function noteheadForInstrument(instrument: Instrument) {
  if (instrument === "RIDE_BELL") return "diamond";
  if (["CRASH", "RIDE", "OPEN_HIHAT", "CLOSED_HIHAT", "PEDAL_HIHAT", "CROSS_STICK", "TAMBOURINE"].includes(instrument)) return "x";
  return "normal";
}

function eventNoteMarkup(event: DrumEvent, duration: number, chord: boolean, beams: string) {
  const position = DISPLAY_POSITION[event.instrument];
  const openHiHat = event.instrument === "OPEN_HIHAT"
    ? "<notations><technical><open-string/></technical></notations>"
    : "";
  return `<note id="${musicXmlIdForEvent(event.id)}">${chord ? "<chord/>" : ""}<unpitched><display-step>${position.step}</display-step><display-octave>${position.octave}</display-octave></unpitched><duration>${duration}</duration><instrument id="P1-I${GM_PERCUSSION_MAP[event.instrument]}"/><voice>1</voice>${durationMarkup(duration)}<stem>up</stem><notehead>${noteheadForInstrument(event.instrument)}</notehead><staff>1</staff>${beams}${openHiHat}<play><other-play type="midi-velocity">${Math.max(1, Math.min(127, Math.round(event.velocity)))}</other-play></play></note>`;
}

function measureNotesMarkup(events: DrumEvent[], measureTicks: number) {
  const grouped = new Map<number, DrumEvent[]>();
  for (const event of events) {
    const tick = Math.max(0, Math.min(measureTicks - 1, Math.round(event.beatPosition * MUSIC_XML_DIVISIONS)));
    grouped.set(tick, [...(grouped.get(tick) ?? []), event]);
  }
  const starts = [...grouped.keys()].sort((a, b) => a - b);
  const clusters = starts.map((tick, index): NoteCluster => {
    const clusterEvents = grouped.get(tick) ?? [];
    const nextTick = starts[index + 1] ?? measureTicks;
    const preferredDuration = Math.min(...clusterEvents.map((event) => SUBDIVISION_TICKS[event.subdivision]));
    return {
      tick,
      duration: Math.max(1, Math.min(preferredDuration, nextTick - tick, measureTicks - tick)),
      events: [...clusterEvents].sort((a, b) => EDITOR_ROWS.indexOf(a.instrument) - EDITOR_ROWS.indexOf(b.instrument)),
    };
  });

  const output: string[] = [];
  let cursor = 0;
  clusters.forEach((cluster, index) => {
    if (cluster.tick > cursor) output.push(restMarkup(cluster.tick - cursor));
    const beams = beamMarkup(clusters, index);
    cluster.events.forEach((event, eventIndex) => {
      output.push(eventNoteMarkup(event, cluster.duration, eventIndex > 0, eventIndex === 0 ? beams : ""));
    });
    cursor = cluster.tick + cluster.duration;
  });
  if (cursor < measureTicks) output.push(restMarkup(measureTicks - cursor));
  return output.join("");
}

export function eventsToMusicXml(
  events: DrumEvent[],
  options: {
    title: string;
    bpm: number;
    beatsPerMeasure?: number;
    durationSeconds?: number;
    firstMeasureNumber?: number;
    systemBreakEvery?: number;
  },
) {
  const beatsPerMeasure = Math.max(1, Math.round(options.beatsPerMeasure ?? 4));
  const bpm = Math.max(1, options.bpm);
  const measureTicks = beatsPerMeasure * MUSIC_XML_DIVISIONS;
  const measures = new Map<number, DrumEvent[]>();
  events.forEach((event) => {
    const absoluteTick = Math.max(0, Math.round((event.measureIndex * beatsPerMeasure + event.beatPosition) * MUSIC_XML_DIVISIONS));
    const measureIndex = Math.floor(absoluteTick / measureTicks);
    const beatPosition = (absoluteTick % measureTicks) / MUSIC_XML_DIVISIONS;
    const list = measures.get(measureIndex) ?? [];
    list.push({ ...event, measureIndex, beatPosition });
    measures.set(measureIndex, list);
  });
  const eventMeasureCount = Math.max(1, ...measures.keys().map((measureIndex) => measureIndex + 1));
  const durationMeasureCount = options.durationSeconds
    ? Math.ceil(options.durationSeconds / (beatsPerMeasure * 60 / bpm))
    : 1;
  const count = Math.max(eventMeasureCount, durationMeasureCount);
  const measureXml = Array.from({ length: count }, (_, measureIndex) => {
    const systemBreak = options.systemBreakEvery && measureIndex > 0 && measureIndex % options.systemBreakEvery === 0
      ? '<print new-system="yes"/>'
      : "";
    const attributes = measureIndex === 0
      ? `<attributes><divisions>${MUSIC_XML_DIVISIONS}</divisions><time><beats>${beatsPerMeasure}</beats><beat-type>4</beat-type></time><staves>1</staves><clef><sign>percussion</sign><line>2</line></clef></attributes><direction placement="above"><direction-type><metronome parentheses="no"><beat-unit>quarter</beat-unit><per-minute>${bpm}</per-minute></metronome></direction-type><sound tempo="${bpm}"/></direction>`
      : "";
    return `<measure number="${(options.firstMeasureNumber ?? 1) + measureIndex}">${systemBreak}${attributes}${measureNotesMarkup(measures.get(measureIndex) ?? [], measureTicks)}</measure>`;
  }).join("");
  const scoreInstruments = INSTRUMENTS.map((instrument) => `<score-instrument id="P1-I${GM_PERCUSSION_MAP[instrument]}"><instrument-name>${escapeXml(INSTRUMENT_LABELS[instrument])}</instrument-name></score-instrument>`).join("");
  const midiInstruments = INSTRUMENTS.map((instrument) => `<midi-instrument id="P1-I${GM_PERCUSSION_MAP[instrument]}"><midi-channel>10</midi-channel><midi-unpitched>${GM_PERCUSSION_MAP[instrument]}</midi-unpitched><volume>80</volume><pan>0</pan></midi-instrument>`).join("");
  return `<?xml version="1.0" encoding="UTF-8"?><score-partwise version="4.0"><work><work-title>${escapeXml(options.title)}</work-title></work><identification><encoding><software>DrumScribe</software><supports element="print" type="yes" attribute="new-system" value="yes"/></encoding></identification><part-list><score-part id="P1"><part-name>Drum Set</part-name><part-abbreviation>Perc.</part-abbreviation>${scoreInstruments}${midiInstruments}</score-part></part-list><part id="P1">${measureXml}</part></score-partwise>`;
}

function variableLength(value: number) {
  let buffer = value & 0x7f;
  const bytes: number[] = [];
  while ((value >>= 7)) {
    buffer <<= 8;
    buffer |= (value & 0x7f) | 0x80;
  }
  while (true) {
    bytes.push(buffer & 0xff);
    if (buffer & 0x80) buffer >>= 8;
    else break;
  }
  return bytes;
}

export function eventsToMidi(events: DrumEvent[], bpm: number): Uint8Array {
  const ticksPerBeat = 480;
  const bytes: number[] = [];
  const messages = events.flatMap((event) => {
    const tick = Math.max(0, Math.round(event.quantizedOnset / (60 / bpm) * ticksPerBeat));
    return [
      { tick, data: [0x99, GM_PERCUSSION_MAP[event.instrument], event.velocity] },
      { tick: tick + 48, data: [0x89, GM_PERCUSSION_MAP[event.instrument], 0] },
    ];
  }).sort((a, b) => a.tick - b.tick || b.data[0] - a.data[0]);
  let lastTick = 0;
  messages.forEach((message) => {
    bytes.push(...variableLength(message.tick - lastTick), ...message.data);
    lastTick = message.tick;
  });
  bytes.push(0, 0xff, 0x2f, 0);
  const tempo = Math.round(60_000_000 / bpm);
  const tempoTrack = [0, 0xff, 0x51, 3, (tempo >> 16) & 0xff, (tempo >> 8) & 0xff, tempo & 0xff];
  const track = [...tempoTrack, ...bytes];
  const header = [0x4d, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 0, 0, 1, 1, 0xe0];
  const length = track.length;
  const trackHeader = [0x4d, 0x54, 0x72, 0x6b, (length >>> 24) & 0xff, (length >>> 16) & 0xff, (length >>> 8) & 0xff, length & 0xff];
  return new Uint8Array([...header, ...trackHeader, ...track]);
}
