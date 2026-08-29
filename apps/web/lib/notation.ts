import { musicXmlIdForEvent } from "@/lib/music";

export interface NotationEventDescriptor {
  id: string;
  label: string;
}

const BLOCKED_SVG_ELEMENTS = "script, foreignObject, iframe, object, embed, audio, video";
const UNSAFE_CSS = /(?:expression\s*\(|url\s*\(\s*['\"]?\s*(?:javascript|data):|@import)/i;

function parsedSvg(svg: string) {
  const document_ = new DOMParser().parseFromString(svg, "image/svg+xml");
  const parserError = document_.querySelector("parsererror");
  if (parserError || document_.documentElement.localName !== "svg") {
    throw new Error("Verovio returned invalid SVG.");
  }
  return document_;
}

/**
 * Verovio renders our own generated MusicXML, but its SVG still crosses an HTML
 * trust boundary. Strip executable/remote content before it reaches the DOM and
 * decorate preserved MusicXML note IDs for editor interaction.
 */
export function sanitizeVerovioSvg(svg: string, events: readonly NotationEventDescriptor[]) {
  const document_ = parsedSvg(svg);
  const root = document_.documentElement;
  root.querySelectorAll(BLOCKED_SVG_ELEMENTS).forEach((element) => element.remove());
  [root, ...root.querySelectorAll("*")].forEach((element) => {
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on")) element.removeAttribute(attribute.name);
      if ((name === "href" || name === "xlink:href") && !value.startsWith("#")) {
        element.removeAttribute(attribute.name);
      }
      if (name === "style" && UNSAFE_CSS.test(value)) element.removeAttribute(attribute.name);
    }
    if (element.localName === "style" && UNSAFE_CSS.test(element.textContent ?? "")) element.remove();
  });

  root.setAttribute("role", "img");
  root.setAttribute("aria-label", "Engraved drum notation");
  root.querySelectorAll(".measure").forEach((measure, index) => {
    measure.setAttribute("data-measure-index", String(index));
  });
  events.forEach((event) => {
    const note = document_.getElementById(musicXmlIdForEvent(event.id));
    if (!note) return;
    note.classList.add("drumscribe-event");
    note.setAttribute("data-drumscribe-event-id", event.id);
    note.setAttribute("role", "button");
    note.setAttribute("tabindex", "0");
    note.setAttribute("aria-label", event.label);
  });
  return new XMLSerializer().serializeToString(root);
}

export function mountSanitizedSvg(container: HTMLElement, svg: string) {
  const root = parsedSvg(svg).documentElement;
  container.replaceChildren(document.importNode(root, true));
}

let verovioModulePromise: ReturnType<typeof import("verovio/wasm")["default"]> | undefined;

function loadVerovioModule() {
  verovioModulePromise ??= import("verovio/wasm").then(({ default: createVerovioModule }) => createVerovioModule());
  return verovioModulePromise;
}

export async function engraveMusicXml(musicXml: string, measureCount: number) {
  const [VerovioModule, { VerovioToolkit }] = await Promise.all([
    loadVerovioModule(),
    import("verovio/esm"),
  ]);
  const toolkit = new VerovioToolkit(VerovioModule);
  try {
    toolkit.setOptions({
      adjustPageHeight: true,
      breaks: "none",
      footer: "none",
      header: "none",
      pageHeight: 1200,
      pageMarginBottom: 50,
      pageMarginLeft: 90,
      pageMarginRight: 60,
      pageMarginTop: 80,
      pageWidth: Math.min(120_000, Math.max(2_400, measureCount * 440)),
      scale: 42,
      svgViewBox: true,
    });
    if (!toolkit.loadData(musicXml)) throw new Error("The score could not be loaded.");
    if (toolkit.getPageCount() < 1) throw new Error("The score has no renderable pages.");
    return toolkit.renderToSVG(1, false);
  } finally {
    toolkit.destroy();
  }
}
