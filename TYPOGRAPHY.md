# Reusable compact English typography

For capability-gated dialogue flow, pixel overflow thresholds, safe scrolling and
pagination, see [Intelligent dialogue layout](docs/dialogue-layout.md). The planner
preserves saved text and produces revision-bound build artifacts. Private adapters
verify geometry, controls, timing and resources before encoding those plans.

Permanent architectural goal, adopted 2026-10-16 for current and future NES/SNES translations: a compact, readable English font with variable character advances and intelligent pixel-based text-block layout. Language fidelity in LOCALIZATION.md and the visual quality standard in AGENTS.md remain mandatory. Avoid repeatedly expanding individual windows merely because the font is unnecessarily wide.

## Artwork and profiles

Mixed-case English is the default under [the localization policy](LOCALIZATION.md#capitalization). Preserve approved lowercase artwork as well as capitals. Measure the final reviewed text, including punctuation and spaces; do not silently uppercase it in layout or encoding adapters. Font height, baseline, descender room and line step are independent from advance widths. Use consistent font-box positioning for related menu rows so a descender does not move one item's baseline; whole-block ink centering remains useful for standalone headings and prompts. Validate both approaches at native resolution and in highlighted states.

Preserve approved Quest Pixel draft 1 and its Dragon Warrior I-inspired aesthetic. Keep original sources and provenance intact. Explore native 8–12 pixel glyphs, clear ascenders/descenders, uppercase/lowercase, digits, punctuation and common dialogue symbols. Do not mechanically double artwork as the default. Prefer readable type at actual game resolution over maximum density. Multiple UI/dialogue profiles are appropriate. The first compact profile reuses native 8-pixel artwork; the 10-pixel dialogue profile adds vertical room, not an invented hand-redrawn alphabet. New profiles still require visual review.

## Portable layout contract

- Track glyph ink bounds, advance, baseline and line step separately. Narrow letters, punctuation and spaces need suitable advances; smaller artwork in a wide fixed cell does not solve spacing.
- Measure pixels; wrap at natural boundaries; preserve explicit breaks and intentional indentation/spacing. Reject unbreakable overflow rather than clipping/truncating. Rebalance avoidable single-word final lines where possible without crossing hard breaks.
- Align the entire block vertically using its bounds and consistent line spacing. Choose left/center/right horizontal alignment by context. Preserve left-aligned menu lists, right-aligned numeric conventions and cursor relationships. Flexible padding normally targets 4–8 native pixels.
- Resolve runtime substitutions before measuring. Retain game controls, pages, waits, names, animation and variable semantics losslessly through a game adapter. Unknown controls must fail closed or use the original renderer; never silently discard them.
- Keep reusable artwork, profiles, metrics, measurement, wrapping, padding, alignment, previews and overflow checks separate from NES/SNES tile encoders, ROM/VRAM/RAM allocation, hooks, banks, game encoding and window adapters.

## Implementation and evidence

Trace affected call paths and resource consumers before modifying rendering. Account for tile capacity, overlapping buffers, allocation lifetime, DMA/VBlank scheduling, CPU cost, cursor/highlight regions, scrolling, transitions and background restoration. Quantify uncertainty. A host-compiled proportional tile block or a limited compact renderer is a valid intermediate approach when safer than a general runtime compositor; label it accurately and document its limits for substitutions, wrapping and animation.

Prototype a heading, long entry, centered prompt and multiline block. Compare legacy fixed, compact fixed and proportional rendering. Distinguish code-generated studies from actual ROM output and emulator captures. Static specimens alone cannot approve a finished interface. Build a bounded ROM test only when ownership and behavior are defensible, validate it reproducibly, then wait for real-game feedback before whole-game migration. Retain known-good builds and rejected experiments as separately labeled evidence.

Each private project pins its approved baseline and records its own rejected experiments. Public code owns portable measurement and composition; private adapters own resource allocation and runtime integration. Future builds start from the pinned original plus reproducible approved changes. Never publish project identities, control bytes, resource addresses or screenshots as typography examples.

The portable APIs are `patchquest.typography.font` and `patchquest.typography.layout`. `Font` loads the shared artwork and profiles; `layout` returns a binary raster and measurable positions. This host-side library does not implement a console runtime renderer. See [the project architecture](docs/project-architecture.md).

`layout(..., vertical_metrics='font')` reserves the profile's full height for each line and uses `line_step` between baselines. This keeps related menu rows aligned despite differing ascenders/descenders. The default `'ink'` retains whole-block ink centering and existing output. Neither option changes artwork, glyph advances, translation spelling or control semantics. Both reject overflow instead of clipping. Explicit padding may justify asymmetric integer margins; inspect the visible result rather than treating a profile as blanket UI approval.

Resource-limited adapters can use `patchquest.core.packing.pack_blobs` to place indivisible byte assets into explicitly verified intervals. It performs deterministic bounded backtracking, never free-space discovery. Ownership, hardware bank limits, aliases, palette behavior and buffer lifetimes remain the private adapter's responsibility. Grouping tile byte patterns can improve compression without changing pixels, but every map reference must be rebuilt and validated after reassignment.

## Shared graphics and encoded text safeguards

Tilemap inventories alone do not establish unused graphics. Numeric lookup tables, runtime map writers, status displays and hard-coded spacer references can consume tiles absent from static maps. Include these consumers in the allocation inventory. A blank-looking tile may be a required spacer; use a verified blank reference when repacking changes its contents. Validate related letters, digits, separators and their shared baseline together.

When extending a private text encoding, audit every consumer of the stream: source expansion, dictionary substitution, progressive glyph rendering, bulk rendering and any separate tilemap parser. An operand equal to a page or end marker is still data. Check raw source and dictionary tokens for collisions, preserve control operands and their order, and test terminator-valued operands explicitly.

Derive line and page limits from actual callers rather than assuming every dialogue box has the same geometry. Host-composed text must budget the largest supported substitutions, expanded bytes, glyph staging and the available live tile allocation. Generate bounded variants or retain the original path for unsupported layouts; report which paths can still display untranslated text. Preserve explicit waits and end behavior while reflowing lines. Added pages and altered reveal cadence require in-game review.

Bounded CPU checks should compare rendered tile bytes, allocation lifetimes and selection restoration, including numeric extremes and different graphics bases. These checks complement screenshots; they cannot certify timing, scrolling, SRAM persistence or hardware behavior.

A partial Unicode transcription is not necessarily reversible. Distinct original glyph codes can share a tentative reading. Bind retained names or other uncertain source text to verified original byte sequences rather than choosing an arbitrary inverse-table entry; keep the reading uncertainty separate from glyph identity.
