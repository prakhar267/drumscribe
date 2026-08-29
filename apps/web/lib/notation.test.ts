import { describe, expect, it } from "vitest";
import { createEvent, eventsToMusicXml, musicXmlIdForEvent } from "@/lib/music";
import { engraveMusicXml, sanitizeVerovioSvg } from "@/lib/notation";

describe("notation rendering boundary", () => {
  it("sanitizes SVG and decorates only preserved canonical event IDs", () => {
    const eventId = "42 / imported & hit";
    const notationId = musicXmlIdForEvent(eventId);
    const unsafe = `<svg xmlns="http://www.w3.org/2000/svg" onload="steal()"><style>@import url(https://evil.test/x.css)</style><script>steal()</script><foreignObject><div>bad</div></foreignObject><g class="measure"><g id="${notationId}" onclick="steal()"><use href="#glyph"/><a href="javascript:steal()">note</a></g></g></svg>`;
    const sanitized = sanitizeVerovioSvg(unsafe, [{ id: eventId, label: "Ride bell, measure 1" }]);
    const document_ = new DOMParser().parseFromString(sanitized, "image/svg+xml");
    const note = document_.getElementById(notationId);

    expect(document_.querySelector("script, foreignObject, style")).toBeNull();
    expect(document_.documentElement.getAttribute("onload")).toBeNull();
    expect(document_.querySelector("a")?.getAttribute("href")).toBeNull();
    expect(note?.getAttribute("onclick")).toBeNull();
    expect(note?.getAttribute("data-drumscribe-event-id")).toBe(eventId);
    expect(note?.getAttribute("tabindex")).toBe("0");
    expect(document_.querySelector(".measure")?.getAttribute("data-measure-index")).toBe("0");
  });

  it("rejects non-SVG renderer output", () => {
    expect(() => sanitizeVerovioSvg("<html/>", [])).toThrow("invalid SVG");
  });

  it("engraves generated MusicXML through the real lazy Verovio module", async () => {
    const kick = createEvent({ id: "kick-1", projectId: "p", instrument: "KICK", time: 0, bpm: 120 });
    const snare = createEvent({ id: "snare-1", projectId: "p", instrument: "SNARE", time: .5, bpm: 120 });
    const musicXml = eventsToMusicXml([kick, snare], { title: "Render test", bpm: 120 });
    const svg = await engraveMusicXml(musicXml, 1);

    expect(svg).toContain("<svg");
    expect(svg).toContain(musicXmlIdForEvent(kick.id));
    expect(svg).toContain(musicXmlIdForEvent(snare.id));
    expect(svg).toContain("class=\"note");
  }, 20_000);
});
