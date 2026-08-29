import { describe, expect, it } from "vitest";
import { createDemoEvents } from "@/lib/demo-data";
import { EDITOR_ROWS, GM_PERCUSSION_MAP } from "@/lib/domain";
import { MUSIC_XML_DIVISIONS, createEvent, diffDrumEvents, eventsToMidi, eventsToMusicXml, gridStepSeconds, lowConfidenceEvents, moveEvent, musicXmlIdForEvent, positionFromSeconds, snapSeconds } from "@/lib/music";

function parseMusicXml(xml: string) {
  const document_ = new DOMParser().parseFromString(xml, "application/xml");
  expect(document_.querySelector("parsererror")).toBeNull();
  return document_;
}

function measureDuration(measure: Element) {
  return [...measure.querySelectorAll(":scope > note")].reduce((duration, note) => (
    note.querySelector(":scope > chord")
      ? duration
      : duration + Number(note.querySelector(":scope > duration")?.textContent ?? 0)
  ), 0);
}

describe("musical timing", () => {
  it("snaps to straight and triplet subdivisions", () => {
    expect(snapSeconds(0.27, 120, "eighth")).toBe(0.25);
    expect(snapSeconds(0.18, 120, "triplet")).toBeCloseTo(1 / 6);
    expect(snapSeconds(0.27, 120, "off")).toBe(0.27);
    expect(gridStepSeconds(120, "sixteenth")).toBe(0.125);
  });

  it("converts seconds into measure and beat positions", () => {
    expect(positionFromSeconds(2.5, 120, 4)).toMatchObject({ measureIndex: 1, beatPosition: 1 });
  });

  it("preserves raw timing while moving quantized notes", () => {
    const event = createEvent({ id: "one", projectId: "p", instrument: "SNARE", time: 1, bpm: 120 });
    const moved = moveEvent(event, { quantizedOnset: 1.25, instrument: "HIGH_TOM" }, 120);
    expect(moved.onsetSeconds).toBe(1);
    expect(moved.quantizedOnset).toBe(1.25);
    expect(moved.manuallyEdited).toBe(true);
  });

  it("builds a minimal dirty batch and leaves untouched model hits alone", () => {
    const original = createDemoEvents().slice(0, 3);
    const changed = moveEvent(original[1], { velocity: 64 }, 112);
    const added = createEvent({ id: "23114658-d158-4ae1-9107-4f26876d35a1", projectId: original[0].projectId, instrument: "KICK", time: 2, bpm: 112 });
    const delta = diffDrumEvents(original, [original[0], changed, added]);
    expect(delta.upserts.map((event) => event.id)).toEqual([changed.id, added.id]);
    expect(delta.deleteIds).toEqual([original[2].id]);
  });
});

describe("canonical conversions", () => {
  const events = createDemoEvents().slice(0, 14);

  it("uses the General MIDI percussion mapping", () => {
    expect(GM_PERCUSSION_MAP.KICK).toBe(36);
    expect(GM_PERCUSSION_MAP.SNARE).toBe(38);
    expect(GM_PERCUSSION_MAP.CLOSED_HIHAT).toBe(42);
  });

  it("generates duration-complete MusicXML with stable IDs, tempo, rests and percussion metadata", () => {
    const xml = eventsToMusicXml(events, { title: "A & B", bpm: 112, durationSeconds: 8.6 });
    const document_ = parseMusicXml(xml);
    const measures = [...document_.querySelectorAll("part > measure")];
    expect(document_.querySelector("work-title")?.textContent).toBe("A & B");
    expect(document_.querySelector("attributes > divisions")?.textContent).toBe(String(MUSIC_XML_DIVISIONS));
    expect(document_.querySelector("direction sound")?.getAttribute("tempo")).toBe("112");
    expect(document_.querySelector("clef > sign")?.textContent).toBe("percussion");
    expect(document_.querySelectorAll("score-instrument")).toHaveLength(13);
    expect(document_.querySelector("midi-instrument midi-channel")?.textContent).toBe("10");
    expect(document_.getElementById(musicXmlIdForEvent(events[0].id))).not.toBeNull();
    expect(document_.querySelector("note > rest")).not.toBeNull();
    expect(measures).toHaveLength(5);
    expect(measures.map(measureDuration)).toEqual(Array(5).fill(4 * MUSIC_XML_DIVISIONS));
  });

  it("groups simultaneous percussion as chords and emits beams for adjacent subdivisions", () => {
    const first = createEvent({ id: "kick", projectId: "p", instrument: "KICK", time: 0, bpm: 120, snap: "eighth" });
    const chord = createEvent({ id: "snare", projectId: "p", instrument: "SNARE", time: 0, bpm: 120, snap: "eighth" });
    const next = createEvent({ id: "hat", projectId: "p", instrument: "CLOSED_HIHAT", time: .25, bpm: 120, snap: "eighth" });
    const document_ = parseMusicXml(eventsToMusicXml([first, chord, next], { title: "Chord", bpm: 120 }));
    expect(document_.querySelectorAll("note > chord")).toHaveLength(1);
    expect(document_.querySelector(`note[id="${musicXmlIdForEvent(next.id)}"] notehead`)?.textContent).toBe("x");
    expect(document_.querySelectorAll("beam").length).toBeGreaterThanOrEqual(2);
  });

  it("preserves non-4/4 measure semantics and XML-safe imported IDs", () => {
    const event = createEvent({ id: "42 / imported & hit", projectId: "p", instrument: "RIDE_BELL", time: 0, bpm: 90 });
    const document_ = parseMusicXml(eventsToMusicXml([event], { title: "3/4", bpm: 90, beatsPerMeasure: 3, durationSeconds: 4 }));
    const measures = [...document_.querySelectorAll("part > measure")];
    expect(document_.querySelector("time > beats")?.textContent).toBe("3");
    expect(document_.querySelector("time > beat-type")?.textContent).toBe("4");
    expect(document_.getElementById(musicXmlIdForEvent(event.id))).not.toBeNull();
    expect(measures.map(measureDuration)).toEqual([3, 3].map((beats) => beats * MUSIC_XML_DIVISIONS));
    expect(musicXmlIdForEvent(" ")).not.toBe(musicXmlIdForEvent("_u20_"));
  });

  it("exposes every canonical instrument as an editable grid row", () => {
    expect(EDITOR_ROWS).toEqual(expect.arrayContaining(["RIDE_BELL", "PEDAL_HIHAT", "LOW_TOM", "CROSS_STICK"]));
    expect(new Set(EDITOR_ROWS).size).toBe(13);
  });

  it("generates a standard MIDI header and percussion track", () => {
    const midi = eventsToMidi(events, 112);
    expect(String.fromCharCode(...midi.slice(0, 4))).toBe("MThd");
    expect(String.fromCharCode(...midi.slice(14, 18))).toBe("MTrk");
    expect([...midi]).toContain(0x99);
  });

  it("orders uncertain events chronologically", () => {
    const uncertain = lowConfidenceEvents(createDemoEvents());
    expect(uncertain.length).toBeGreaterThan(2);
    expect(uncertain.every((event, index) => index === 0 || event.quantizedOnset >= uncertain[index - 1].quantizedOnset)).toBe(true);
  });
});
