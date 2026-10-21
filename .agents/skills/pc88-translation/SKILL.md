---
name: pc88-translation
description: Inspect PC-8801/PC-88 disk images and develop private English translation projects using guarded D88 storage, keyboard-aware runtime evidence and shared translation state. Use for PC-88 game work, not SNES cartridge workflows.
---

# PC-88 translation

Read root AGENTS.md, the selected private project's instructions and
[PC-88 workflow](../../../docs/pc88-workflow.md). Use explicit manifests and
the existing project/state APIs. Keep source identities, text, sector locations,
consumer traces, runtime configurations and actual results private.

## Intake and investigation

Pin archives and extracted members separately. Preserve alternate dumps as
variants until evidence establishes disk roles. Archive filenames, language
suffixes and parser success do not establish release identity or translation.
Use [D88 storage](../../../docs/disk-images.md) for supported containers;
preserve headers, status flags, ordering and opaque bytes. Do not apply cartridge
checksum or SNES mapping tools to disks.

Distinguish container offsets, sector payload offsets, loaded CPU addresses and
banked memory. Keep an explicit mapping when examining concatenated payloads;
sector headers must not appear in decoded strings. Physical track order is an
inspection view, not evidence of file allocation or execution order.

Treat ASCII, single-byte kana, multibyte text, tokenized programs, compressed
resources and rendered graphics as hypotheses until consistent source examples
and consumers support them. A readable byte run is a research candidate, not a
verified translation record. Preserve undecoded bytes and prove byte round trips.
For typed adventures, investigate command matching, abbreviations, noun/verb
tables and keyboard modes alongside display text.

## Runtime and localization

Verify the installed emulator, chosen machine and firmware independently of game
media. Firmware is separate from the emulator; never infer that installing one
provides the other. Use explicit firmware paths and installed-version metadata,
including device dependencies. Do not acquire utilities/firmware implicitly.

Boot disposable disk copies with isolated writes and bounded execution. Retain
actual title/text/input frames before associating storage candidates with visible
strings. Record CPU domain and bank state for traces. A drained input queue is
not proof that a command was accepted. See the shared
[runtime evidence contract](../../../docs/runtime-evidence.md).

Follow LOCALIZATION.md and TYPOGRAPHY.md in the selected platform. Identify the
actual text/graphics/firmware-font path before choosing a font integration.
Measure native glyph bounds, cursor and interaction areas; preserve fallback
glyphs. Establish [narrative context](../../../docs/narrative-context.md) before
substantial translation, using source evidence rather than a catalog synopsis.

Use revisioned state for verified records, human corrections and build snapshots.
Require lossless unchanged extraction/insertion before a localized experiment.
Build fresh derivatives with expected-byte checks and explicit storage ownership;
test displayed wording and typed commands together. Disk writes and save media
are separate from cartridge SRAM. Report static, emulator and human results
separately; do not advertise an unavailable private build worker.

## Shared work

Use the [collaboration skill](../translation-collaboration/SKILL.md) for shared
work. Check exact public resource ownership across the participating projects:
separate project databases do not provide cross-project exclusion. Keep scopes
disjoint or obtain a coordinated handoff. Promote independent techniques and
synthetic examples only; never copy actual game examples into public tests.
