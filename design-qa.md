# Design QA — score-first editor

## Evidence

- Selected source: `docs/design/editor-direction-3.png`
- Final implementation: `docs/design/editor-implementation-1280x720.png`
- Source pixels: 1487 × 1058
- Implementation capture: 1280 × 720 CSS pixels at device pixel ratio 2 (the Codex in-app browser panel caps the visible content height at 720 pixels)
- Comparison state: Edit mode, first score page, one selected crash hit, compact note palette open
- Density normalization: proportional full-view comparison, followed by focused comparison of toolbar, waveform, score/palette, instrument-lane header and transport. The source contains a taller viewport, so the final implementation intentionally shows less grid depth at the same readable score scale.

## Comparison history

### Pass 1

- P1: the notation was compressed and did not hold visual priority.
- P1: the default selected-note inspector obscured too much of the score.
- P2: mobile notation was scaled down instead of remaining readable.

### Corrections

- Paginated the Verovio score at eight measures per page with encoded four-measure system breaks, a larger engraving scale and active-page/current-measure behavior.
- Replaced the full default inspector with a four-value contextual palette and an explicit advanced-properties control.
- Added readable minimum score widths with horizontal scrolling on narrow tablet/mobile layouts; the dense drum grid is hidden on mobile while notation, waveform, playback and correction controls remain.

## Final visual review

- Typography: passed. Compact system UI typography, tabular transport values, restrained serif pagination and real Verovio engraving match the professional music-tool hierarchy.
- Spacing and layout: passed. Project chrome, waveform ribbon, warm score page, collapsible instrument lanes and bottom transport follow the selected source's order and density.
- Color and tokens: passed. Graphite workspace, warm paper, chartreuse selection/action and cyan waveform/grid data are implemented through semantic tokens.
- Assets: passed. The build uses real Verovio notation, live waveform/event data, the existing DrumScribe mark and the shipped Lucide icon set; no placeholder visual assets are present.
- Copy and states: passed. Labels are concise and functional; mode, save, selection, review count, loop, source-channel and responsive states are explicit rather than color-only.

## Interaction and responsive review

- Verified play/pause, score hit selection, compact/advanced note properties, grid collapse/expand, Edit/Timing/Review mode switching, export modal and hit/measure context menus.
- Verified hit context actions for instrument reassignment, duplicate, quantize, mark correct and delete; verified measure actions for loop, requantize, select hits and open in Timing.
- Verified desktop editor at the in-app browser's 1280 × 720 visible viewport, tablet layout at 1024 × 768 and mobile layout at 390 × 844.
- Verified the homepage's synchronized product proof appears in the first fold and the processing screen includes track identity, duration/privacy context and a live waveform preview.
- Re-opened the editor in a fresh browser tab and inspected development logs; no application errors remained.

## Remaining differences

- P3: source content is an art-directed measure 9–16 state, while the implementation capture uses the available development project's real measure 1–8 data and transport time.
- P3: the implementation retains undo, redo and autosave status because they are required product-safety controls.
- P3: exact glyph spacing differs because the implementation is live Verovio engraving rather than a raster mock.

No P0, P1 or P2 visual-fidelity issue remains in the verified scope.

final result: passed
