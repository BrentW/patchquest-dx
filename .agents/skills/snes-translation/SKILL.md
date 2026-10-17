---
name: snes-translation
description: Inspect Japanese SNES ROMs and develop reproducible English translations in private project workspaces using Patch Quest DX's shared tools, typography, BPS patches and emulator validation.
---

# SNES translation

Read root AGENTS.md, [local setup](../../../docs/local-setup.md), [the project contract](../../../docs/project-architecture.md) and the explicitly selected private project's instructions. Consult relevant ignored local notes/configuration if present. Missing private files do not block public tests or synthetic examples. Do not download utilities without approval.

## Privacy, promotion and permanent maintenance

The public platform never imports private project modules. Private runners consume public APIs. Keep game identities, hashes, encodings, addresses, translations, hooks, allocations, recipes, progress and debugging evidence in the private project. External project folders are preferred; .local/projects/ is an ignored alternative.

Use [the information-classification table](../../../docs/local-workspace.md#information-classification-table). Classify durable discoveries as platform improvement, private-project knowledge, or both. Promote only independently generalized techniques with synthetic, newly authored or appropriately licensed tests. Removing a title does not anonymize byte signatures, offsets, distinctive code or dialogue. Private notes may reference public techniques; public records must not point to actual private projects.

Update canonical documentation when verified findings affect setup, configuration, debugging or workflows. Preserve machine-specific workarounds privately; keep public settings/examples/tests synchronized with implemented behavior. Avoid duplicated procedures and repeated rediscovery. Distinguish verified, reported, unresolved and superseded knowledge; temporary experiments are not permanent rules. Never put private values into tracked documentation, commits or generated public reports. Audit candidate files, staged blobs, exports and Git refs/objects before authorized publication. Do not automatically publish private material.

## Licensing and asset provenance

Follow [the exact license scope](../../../LICENSE-SCOPE.md) and [licensing conventions](../../../docs/licensing.md): platform Python/tools/tests/examples/docs use Apache-2.0; designated Quest Pixel font data/artwork use CC BY 3.0 Unported with applicable upstream terms. Keep attribution and full terms with redistributed font derivatives; the renderer's license does not relicense its inputs. Preserve approved art and metrics. Do not substitute OFL.

Record each new reference or borrowed asset's creator, source, terms and actual changes before inclusion. Maintain scope, notices, provenance and generated package notices together. Do not equate redrawing, AI assistance, approval or pixel differences with independent authorship or clearance of commercial-game rights. Keep detailed research/comparisons private and report specific unresolved conflicts. Public maintainer credit is BrentW; do not invent ownership or an email. Contact, Git initialization and publication need separate authorization.

## Identify and establish a baseline

Use `python tools/patchquest.py inspect PATH` on an explicitly selected immutable original. Keep reports private. Record file/payload hashes, copier-header inference, candidate headers, mapping clues, checksum/complement, reset vector, SRAM, region and cartridge fields. Validate code/vector behavior and mapping independently; neither a filename, a matching checksum nor one header score proves a dump or mapper. Distinguish file offsets, headerless offsets and CPU addresses.

Read sources through hash-pinned APIs. Preserve originals without renaming, stripping headers, repairing or overwriting them. Build fresh derivatives through an explicit output policy. Before migration/refactoring, archive the legacy recipe environment and reproduce checkpoints byte-for-byte. Stop and ask if a checkpoint cannot be reproduced; retain all subsequent research and rejected builds.

## Discover text and graphics

Start statically. Examine likely font tiles across plausible bit depths, glyph arrangements and palettes; use the shared SNES tile codec for explicit ranges. Inspect kana/kanji/Latin coverage and distinguish font glyphs from pre-rendered UI tilemaps. Do not assume Shift-JIS, ASCII, fixed-width codes or linear glyph indexes.

Trace consumers and identify data structures using multiple consistent examples. Record evidence and uncertainty for character tables, pointer widths/endian order, bank constraints, control parameters, terminators, dictionaries and compression. Unknown bytes must remain lossless and visible. Shared extraction supports explicit one-byte tables only; private adapters implement multibyte/control/compression formats.

Identify direct, compressed and generated text paths separately. A compression hypothesis needs exact decompression/recompression or otherwise verified round trips and consumer bounds. Disassembly is exploratory: the shared linear helper is not full control-flow analysis, and M/X widths must be validated at entry/branch boundaries.

Prove one visible phrase/menu and its reference chain first. Match source bytes, glyph identities and rendered text. If static evidence is insufficient, specify an exact emulator/debugger procedure: trigger, CPU/memory domain, read/write/execute breakpoint, registers/banks to capture and observation that would resolve the hypothesis. Recommend or use installed tools within authorization; never invent a debugger trace.

## Extract and localize

For migrated projects, use the [shared state workflow](../../../docs/translation-studio.md): read current revisions/context and relevant memory/glossary, then write through the API with compare-and-swap revisions. Human corrections take precedence; record alternatives as proposals and never silently replace them. Preserve opaque controls and private source evidence. Agent text needs technical validation but no mandatory language-approval queue. Freeze a snapshot before building and bind insertion/test evidence to its revisions. Preserve historical language files for exact checkpoint reproduction.

Offer the optional local Studio when browsing/correction would help; agent work and private builds must also function without it. Publish meaningful timestamped activity and independent progress stages through the same APIs, regardless of provider. Never infer decoded text from a partial transcription or gameplay verification from a build approval. Follow the public/private classification for state, issues, screenshots and discoveries. See [agent compatibility](../../../docs/agent-compatibility.md); maintain this canonical workflow and regenerate thin discovery adapters when it changes.

Extract editable records with stable IDs, source offsets/pointers, original bytes, lossless controls, context and translation fields. Keep originals, text and tables private. An unchanged extraction/insertion cycle must reproduce source bytes before bulk translation.

Read [LOCALIZATION.md](../../../LOCALIZATION.md) and the shared contextual glossary, then private project terminology/voice notes. Translate natural English faithfully, preserving Japanese cultural specificity, tone and intentional ambiguity. Unknown meanings remain provisional. Do not distort meaning, truncate or invent context to fit storage/layout. Keep translation decisions separate from insertion code.

Default to contextual Title Case for menu choices, sentence case for dialogue/exposition/prompts, and context-appropriate headings. Preserve proper nouns, acronyms, terminology, source voice and emphasis. ALL CAPS requires a deliberate stylistic reason. Review spelling editorially rather than applying blanket case conversion, and preserve it through layout and encoding. Document renderer limitations instead of silently uppercasing.

## Typography, alignment and layout quality

Read [TYPOGRAPHY.md](../../../TYPOGRAPHY.md) and the permanent UI standard in AGENTS.md. Preserve approved Quest Pixel artwork, its visual-reference credit and Japanese glyph functionality until all relevant consumers are safe. Keep public Unicode metrics separate from private ROM mappings.

Measure actual ink bounds, advance, baseline and line step. Aim for comfortable, consistent 4–8 native-pixel interior padding where feasible, treating it as a guideline. Left-align normal menu lists, center appropriate headings/prompts and align numeric columns for scanning. Balance whitespace and row spacing; text must not collide with borders or interaction areas.

For mixed-case rows, retain ascenders, descenders and punctuation placement without changing approved master glyphs. Use a common font-box baseline where related rows need alignment, and measure complete multiline blocks. Compare previous and proposed text at native resolution with borders/highlights; label generated previews separately from emulator captures. Preserve historical recipes while adding new versioned private adapters.

Use compact 8–12 pixel profiles, variable advances and whole-block layout where appropriate. Smaller artwork in a wide cell alone does not fix spacing. Investigate positioning, natural concise wording, compact spacing/layout, safe box changes and deeper rendering changes according to evidence. Do not sacrifice meaning or clip text.

Shared host-side layout supports wrapping, alignment, resolved substitutions and retained opaque controls; it does not implement game bytecode or runtime rendering. Keep page/wait/animation semantics in private adapters. Precomposed proportional tiles are a useful bounded strategy, but are not true runtime VWF.

For intelligent dialogue flow, follow [the layout-planning contract](../../../docs/dialogue-layout.md).
Use pixel thresholds and per-caller policies; preserve fitting layouts and saved
wording. Verify native scrolling independently of newline acceptance and prefer
it over resizing/pagination when available. Otherwise use verified line capacity
or wait/clear pagination. Do not add waits to timed/nonblocking text without a
validated policy. Restrict menu/HUD behavior, block unresolved overflow before
ROM output, and bind Studio summaries to frozen revisions. Plans are not edits
to human corrections or claims of emulator verification.

Before renderer/allocation changes, trace all callers and consumers, and budget ROM/banks, WRAM, VRAM, tile indices, DMA/VBlank, CPU/stack, buffer lifetimes and fallback paths. Account for cursors, highlights, scrolling, dynamic values and background restoration.

Review actual screenshots at native/documented integer scale. Test selected/unselected states, longest labels, largest valid values, empty/populated fields, scrolling, transitions and animation. Confirm navigation and selection behavior. Static specimens alone cannot approve a finished interface. Keep design approval, automated traces and runtime evidence distinct.

## Build, patch and validate

Studio's **Build test ROM** requires an explicitly launched private `BuildWorker` callback; the generic platform never imports project code or executes browser-provided commands. Capture saved revisions atomically and report real validation stages, fresh output locations and failures. Full builds are supported; do not claim selective modes until implemented and verified. Preserve interrupted outputs and use a new job for retries. Keep checkpoint approval separate from technical success. For screenshot issues, upload private PNG/JPEG evidence, verify record/issue/scene/resource/build links, retain provisional confidence where uncertain, and use association history to correct mistakes. An associated image alone does not certify a translation or gameplay result. Follow the [Studio workflow](../../../docs/translation-studio.md).

Private recipes must assert source hashes, expected bytes, intended changed ranges, pointer constraints and capacities. Prefer programmatic insertion/repointing over manual hex edits. Build from the original plus approved changes and validated new work, never from a rejected derivative.

Recalculate internal checksum/complement using the verified header/mirroring policy. Repeat builds and compare exact ROM and BPS bytes. The shared BPS encoder/verifier supports SourceRead/TargetRead; require reconstruction and wrong-source/corrupt-patch rejection. Independent approved-tool interoperability is a separate pre-distribution check. Never distribute ROMs or untouched extracted assets as public fixtures.

Cold-boot Snes9x and check edited text, relevant branches, menus/gameplay, names/numbers, transitions, saves and reload after restart. Save states alone do not prove SRAM persistence. Record emulator/version/build and the exact tested scope privately. Check original hardware/FXPAK PRO when available, with region, firmware, timing and save behavior; emulator success is not hardware validation.

Maintain private per-project evidence, progress, known issues, repeatable commands and coverage. Preserve known-good checkpoints and label rejected/unapproved outputs. Never claim a complete translation, full playthrough or hardware compatibility without corresponding tests.

## Shared agent work

For sequential handoffs or concurrent tasks, follow the canonical
[collaboration skill](../translation-collaboration/SKILL.md). Use `agent-context`
to discover the selected private project's rules and build interfaces. Read
memory, glossary and current revisions before claiming/publishing work; protect
human corrections and preserve source controls. Coordinate shared renderer,
font or allocation changes with explicit resource ownership as well as record
scope. Keep findings and handoffs durable in the appropriate public/private
records, never in a separate provider-specific policy copy.
