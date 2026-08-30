# DrumScribe Design System

## Product character

DrumScribe is a professional creative tool: musical, precise, calm, fast and technical without becoming intimidating. The interface uses a deep graphite workspace, a warm score surface and one restrained chartreuse accent. The product UI should never resemble a generic AI dashboard.

The selected editor direction is the score-first workspace captured in `docs/design/editor-direction-3.png`. It is the visual source of truth for editor hierarchy and density.

## Foundations

The canonical tokens live in `apps/web/app/globals.css` under `:root`. New product UI must use the semantic tokens rather than component-local color literals.

### Color

| Role | Token | Purpose |
| --- | --- | --- |
| Canvas | `--background-canvas` | App chrome and deepest workspace layer |
| Panel | `--background-panel` | Timeline, grid labels and compact controls |
| Elevated | `--background-elevated` | Transport, popovers and contextual inspector |
| Score | `--background-score` | Verovio notation page |
| Primary text | `--text-primary` | Main labels and controls on dark surfaces |
| Secondary text | `--text-secondary` | Supporting labels |
| Muted text | `--text-muted` | Metadata and passive state |
| Accent | `--accent-primary` | Primary actions, selection and active modes |
| Waveform | `--accent-waveform` | Audio and event timing data |
| States | `--state-success`, `--state-warning`, `--state-error` | Status only, never decoration |

The notation page uses dedicated score text, border and selection tokens so warm-surface contrast remains independent from dark UI colors.

### Typography

- UI: Inter Variable when available, followed by the platform system sans stack.
- Technical values: SF Mono/Consolas fallback with tabular numerals.
- Notation: Verovio engraving only.
- Score pagination: restrained serif to reinforce the page metaphor.
- Sentence case is the default. Uppercase is reserved for compact metadata labels.

### Spacing and shape

- Spacing scale: 4, 8, 12, 16, 24, 32 and 48 pixels through `--space-*` tokens.
- Compact control radius: `--radius-control`.
- Panel/popover radius: `--radius-panel`.
- Buttons are not universally pill-shaped. Editor controls use compact rounded rectangles; pills are reserved for statuses and segmented choices.
- Borders establish hierarchy before shadows. Shadows are reserved for floating or modal layers.

### Motion

- Fast interaction feedback: `--motion-fast` (140 ms).
- Standard surface transitions: `--motion-standard` (200 ms).
- Animate opacity and transform only where possible.
- The playhead and timing-critical visuals never use decorative easing.
- `prefers-reduced-motion` disables non-essential movement globally.

## Editor architecture

The desktop editor is ordered by musical importance:

1. Project chrome and mode switcher.
2. Waveform ribbon with range, loop and measure navigation.
3. Large paginated warm notation page.
4. Collapsible instrument lanes.
5. Dedicated bottom transport deck.

Edit, Timing, Review and Practice are distinct workflows. Controls must not leak between modes unless they are globally necessary for playback or project safety.

### Notation

- Eight measures are rendered per page with a system break after four measures.
- The active playback page follows the authoritative transport clock.
- The active measure is subtle; selected hits use the score-specific accent.
- Long scores are paginated instead of compressed into one horizontal strip.

### Waveform and grid

- Waveform, notation and drum grid share the transport time; no local playback clock is permitted.
- Bar boundaries are stronger than beat subdivisions.
- Waveform cyan represents audio energy; chartreuse represents active selection/loop state.
- Instrument lanes may be collapsed. Hidden lanes must not discard editor state.

### Contextual note editing

- No permanent empty inspector is allowed.
- Selecting a hit opens a compact floating palette with musical value, instrument and position. Its explicit detail control expands velocity, confidence/source and delete actions without reserving permanent editor space.
- Review mode may show a compact review dock even before a note is selected.
- Escape/close clears selection without mutating the note.

### Transport

- Previous/play/next and authoritative time remain at the left.
- Loop, speed, count-in and metronome form the center practice cluster.
- Original/drums toggles and the detailed mixer live at the right.
- Space remains the immediate play/pause shortcut; count-in applies to the visible Play action.

## Responsive behavior

- Desktop and large tablet: full notation, waveform and grid editing.
- Narrow tablet: compact labels and icon-first transport controls.
- Mobile: notation, waveform, playback and contextual review remain; the dense drum grid is intentionally hidden and the app explains that full editing is optimized for desktop/tablet.
- Contextual inspector becomes a bottom sheet on narrow screens.
- Interactive targets aim for at least 44 pixels on touch-first layouts.

## Accessibility and interaction states

- Every icon-only control requires an accessible name.
- Focus uses the primary accent with visible offset.
- Buttons and inputs implement hover, active, focus, disabled and error states.
- Status is never communicated by color alone.
- Successful autosave is quiet. Error status remains actionable.
- Verovio notes are keyboard-focusable buttons with descriptive instrument, beat and measure labels.

## Asset policy

- Product notation, waveform and hit data are rendered from the real project model; screenshots are never substituted for working editor content.
- Existing DrumScribe brand assets are preserved.
- Lucide is the product icon family because its restrained line weight matches the selected design and is already shipped in the app.
- New illustrations or raster imagery require a real source asset or ImageGen output sized for its consuming slot. Do not create decorative div/SVG stand-ins.

## QA gate

For visual changes, capture the reference and the live app at the same viewport and interaction state. Record findings in `design-qa.md`, fix P0–P2 issues and repeat until the report says `final result: passed`. Build/test success alone is not visual verification.
