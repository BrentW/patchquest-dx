# Runtime evidence and visual inspection

Use an explicitly configured emulator and a private scenario to reach the affected
screen, capture real frames and check named expectations. Runtime evidence
supplements static checks; human acceptance remains separate.

Use [verification coverage and readiness](verification-readiness.md) to declare
planned areas, reuse exact registered assertions and distinguish untested, failed,
passed and stale evidence for an explicit build. Its private summary omits raw
project evidence and never infers release approval.

| Level | Establishes | Does not establish |
|---|---|---|
| Static / instruction checks | Bounds, controls, expected bytes and repeat builds within the tested model | Actual frames or gameplay timing |
| Automated runtime | Observed frames and specific assertions in the named emulator/configuration | Every scene, hardware compatibility or literary quality |
| Human acceptance | Only the review scope explicitly reported by the reviewer | Untested records, states or platforms |

## Explicit setup and capabilities

Adapters implement `describe`, `load`, `step`, `restore` and `close`. `step` returns
an RGB `Frame` from emulator output. Adapters identify `actual_emulator` versus
`synthetic`; synthetic tests never establish emulator execution. Native cores are
trusted local software, not sandboxed by this interface. Use approved installations.

The optional `libretro_runtime.Libretro` adapter supports software video,
frame-stepped port-zero joypad input, core-native states and explicit battery-save
transfer. No core is bundled or downloaded; RetroArch is not required. No desktop
input, WRAM patching, debugger or audio analysis is implemented. Hardware framebuffers are
rejected. Core defaults are retained and unsupported extensions return false.
Record binary hash, version and configuration; test exact installed capabilities.
The independent client follows the [libretro ABI](https://github.com/libretro/libretro-common/blob/master/include/libretro.h).

Private instruments can explicitly query `memory_size("system_ram")` or
`memory_size("video_ram")`, then copy a bounded slice with
`read_memory(region, offset, length)`. A zero size means unavailable; reads fail
when the core is unloaded, the pointer is absent or the range is invalid. Regions
are limited to 16 MiB and each nonempty copy to 1 MiB. Only these two named regions
are accepted. Offsets address bytes within the core-provided block, not CPU bus
addresses. The result is immutable bytes; no pointer or memory-writing interface
is returned. Query and read on the owning worker thread between frame steps,
never concurrently with stepping, restoring or unloading the native core.

Memory availability is not glyph or control instrumentation. Keep private field
maps, observed frame numbers, interpretation versions and source evidence bound
to the exact build/core/configuration. Retain raw samples alongside the actual
capture and independently calibrate their meaning before declaring glyph,
completion, wait or scrolling capabilities. Between-frame samples can miss
transient events; unchanged bytes alone do not prove completion or absence of
activity. Existing adapter capability defaults are unchanged. These accessors
perform no implicit reads, discovery, game interpretation or evidence admission.

Use the bounded child-process runner, not a native core in a long-lived Studio
server. The parent watchdog terminates its own hung child and retains failure
evidence. Each worker uses a fresh private directory. Existing saves are never
discovered or imported automatically; only an explicitly pinned scenario file is read.
This is output isolation, not an OS security sandbox. No browser input selects
executables, commands or ROM paths. Desktop screenshot/movie/frame-advance support
does not prove a usable unattended interface; verify before promising automation.

## Emulator testing speed

Default to the highest emulator speed the testing agent can reliably observe and
control. Try the installed emulator's supported fast-forward or unthrottled mode,
increasing speed while checking that inputs, navigation and required captures
remain dependable. Use emulator speed controls rather than changing emulated CPU
clocks, game logic or timing constants. For deterministic frame stepping, execute
as quickly as the host permits while retaining every specified emulated frame,
input duration and capture point.

Slow down, pause or advance individual frames when reading text, inspecting
transitions or issuing precise inputs requires it. Check real-time pacing, audio
and input responsiveness at normal speed with tools that support those checks;
an accelerated run alone does not verify them. Record the effective speed and
any limitations in private evidence. Keep temporary settings local to the owned
test session where possible, and restore changed persistent settings afterward.
If acceleration is unavailable or unreliable, use the fastest reliable supported
mode and record that limitation.

## Transfer completion and latency

When changing graphics loading, distinguish the first matching pixels or memory
bytes from completion of the requested work. A destination can already contain
the expected bytes while redundant writes remain queued. Observe the actual
queue/loader completion condition and return to the caller, and verify restored
registers, scratch state and fallback behavior where the adapter can inspect them.
If completion cannot be observed, report visual readiness only and leave load
completion unverified.
Record observation granularity: a stack low-water mark sampled between frames
does not establish the deepest stack use within an interrupt.

Compare baseline and candidate from equivalent game states reached under each
build's own pinned cold boot or compatible fixture. Record the trigger, queued
work, completion and first usable interface in emulated frames; report host
throughput separately. If loads take different frame counts, compare stable
post-load states using the measured offset, retaining the unshifted timing evidence.
Do not search for an arbitrary matching frame or use an offset to hide a changed
animation, delay or missed input. Approximate seconds require the applicable frame
rate; they do not constitute a normal-speed responsiveness assessment.

Exercise short presses, a held button across the load, release/neutral input and
a deliberately missing input. Check that the intended page/selection is reached
without skipping, then test page waits, advancement, closure and fallback screens.
Exact font reconstruction, transfer counts and static timing estimates complement
actual frames and controls; none replaces whole-handler timing or hardware tests.
A [synthetic counterexample](../tests/test_tile_dictionary_model.py) demonstrates
why byte equality alone is insufficient; it does not exercise emulator input or
timing.

## Scenarios and assertions

Start from [the fictional template](../templates/project/runtime-scenario.example.json).
Replace its hashes, timing and geometry privately. Pin ROM SHA-256 and immutable
translation snapshot; associate only exercised records and their exact revisions.
Empty associations describe screen-level checks, not all translations.

Steps specify bounded frame counts, held joypad buttons, capture names and named
assertions. Neutral steps release buttons. Save unscaled callback PNGs, frame
numbers and input ranges. Limits bound frames, captures and elapsed time. Failed
assertions stop the scenario; partial captures and logs remain diagnostic evidence.

Supported assertions: region hashes, bounded RGB-color pixel counts with optional
tolerance, and pixel differences against an earlier capture. Use these for known
navigation checkpoints, highlight movement, stable borders and transitions.
Expectations must be independently justified, not copied from the same run and
presented as independent proof. Geometry alone does not prove complete wording.
Inspect text, line/page advancement and input behavior with suitable captures.
Choose stable regions and documented tolerances for animation. An assertion label
cannot broaden the scope of what its pixels actually establish.

Calibrate checkpoints from inspected frames before writing a regression scenario.
A visible screen may still be initializing or animating text and may ignore an
early button press. Check a settled screen before advancing; distinguish a
partially rendered animation from permanent clipping. Keep complete-frame or
text-region checks alongside selection probes. Place background-color probes in
verified blank interior pixels, away from glyphs and decorative borders. If an
expectation is wrong, retain the failed run and document the independently
verified correction; do not relax an expectation merely to obtain a pass. Include
a deliberately missing input to demonstrate that navigation assertions can fail.

Cold boot is the default. State scenarios require a private file/hash and matching
ROM/emulator hashes. Cross-build or desktop/core state reuse is rejected until a
separate compatibility strategy is established. State loading does not verify
cold boot or SRAM persistence. Compare before/after runs under compatible
configuration and timing; retain both builds and capture provenance.

For battery persistence, use `initial.kind: "sram"` with the same `path`, `sha256`,
`rom_sha256` and `emulator_sha256` fields as a state fixture. For example, a private
scenario can name `output/runtime/example-save/test-save.srm`; use real verified
hashes privately. The adapter copies only the core's exposed save-RAM buffer,
requires an exact size (at most 16 MiB), and imports before the first frame.
`save_ram()` returns that buffer for an explicit private harness to retain under
a fresh output path. No automatic overwrite or save discovery occurs.

Verify persistence by saving through normal game controls, exporting that newly
created SRAM, ending the worker, then starting a fresh worker with SRAM alone and
loading through the game's menus. Compare saved values, progress and visuals;
include cancel and slot-selection paths. A same-process state roundtrip does not
meet this test. Pin and retain the test save's provenance and preserve user saves.
RTC data and core-specific multi-file save formats are unsupported. Describe only
the actual restart/load behavior observed; file equality alone is insufficient.

## Run and inspect

After a private pipeline registers a validated build:

```text
python tools/runtime_check.py /private/example/project.json --build example-build --scenario /private/example/scenarios/menu.json --core /tools/approved-core.dll --core-sha256 <verified-hash> --destination runtime/menu-check-001
```

Use a fresh destination. The runner validates identities, saves scenario, inputs,
captures and `runtime.json`, then registers through existing screenshot/build APIs.
`state ... runtime-reports` exposes evidence to all agents. Studio's Builds view
shows assertions, provenance and capture sequences; associated revision changes
mark evidence stale. Link captures to issues through existing screenshot metadata.
Associations do not confer per-record verification. New UI assets need a browser
refresh; new APIs need the normal authorized server restart procedure.

The runner never changes translations, human corrections or checkpoint approval.
Registration checks consistency, not cryptographic proof of an adapter's claims.
Public tests exercise invented frames; installed-emulator results remain private
and do not certify every core. No general scene search, OCR, autonomous full
playthrough, audio analysis, debugger integration, automatic issue matching or
browser-triggered native execution is claimed.

## Narrative context and durable findings

Actual expressions, animation, transitions and observed timing supplement source
dialogue and event evidence in the [narrative guide](narrative-context.md). Keep
observations separate from interpretations; do not infer personality or emotional
intent from one frame. This adapter discards audio, so no music/sound analysis is
supported. Keep scenarios, states, real hashes, paths, captures, review status and
game-specific assertions private. Promote generic techniques with independent
synthetic tests. Record capabilities as tested, documented or unverified; retain
failed runs and known-good builds.
