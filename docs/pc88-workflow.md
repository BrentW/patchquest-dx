# PC-88 disk translation workflow

This guide covers reusable investigation methods for NEC PC-8801/PC-88 projects.
The platform supplies guarded storage and state primitives, not a universal
filesystem, text decoder, keyboard driver or PC-88 translation pipeline.
Actual games, firmware, executable paths and results belong in private projects.
Use the [canonical skill](../.agents/skills/pc88-translation/SKILL.md) and
[project contract](project-architecture.md).

## Identify the layers

| Layer | Evidence needed |
| --- | --- |
| Archive | CRC integrity, exact member paths and separate hashes |
| Disk container | Header/track/sector bounds and preserved byte identity |
| Logical data | Verified loader or filesystem order; explicit sector mappings |
| CPU memory | CPU domain, load address, bank state and observed consumer |
| Text | Encoding, controls, terminators and lossless source reconstruction |
| Display/input | Actual frames, glyph metrics, keyboard mode and accepted actions |

The [D88 API](disk-images.md) validates a supported container profile. It does
not prove bootability, dump authenticity, missing-disk completeness or language.
Preserve variants separately. A no-change `reconstruct()` returning original
bytes is container preservation, not proof of a decoded resource's round trip.

When making a payload inspection view, retain a segment table mapping every
view interval to its disk, track slot, sector ordinal and container offset.
Do not decode raw container headers as dialogue or assume a resource ends at a
sector boundary. Concatenation by storage order remains provisional until the
loader or filesystem establishes logical ordering. Repeated strings may be
duplicates, unused data or separate consumers; do not merge them automatically.

Reuse the explicit mapped-stream helpers for verified resource spans. The shared
linked BASIC-line reader and FAT8 chain checks are available when evidence
establishes those formats; a machine family alone does not establish either.
A custom loader may require a different logical mapping while still using the
same guarded D88 sector primitives.

An editable message may cross both sector and track boundaries. Split writes at
verified payload boundaries, retain their logical order, and validate the complete
unchanged message before editing. Determine every affected integrity-check domain;
updating only the domain containing the first byte is insufficient. Boot-time
checksum coverage must not be assumed to cover resources loaded later.

## Machine and firmware evidence

PC-88 models have distinct firmware, banking and display configuration. The main
CPU and disk subsystem are different execution domains. A useful memory trace
records which CPU and bank configuration produced each observation. Text,
graphics and kanji-font accesses need separate investigation. See the
[MAME PC-8801 implementation](https://github.com/mamedev/mame/blob/mame0289/src/mame/nec/pc8801.cpp)
as a versioned hardware implementation reference, not a claim about an installed
emulator or any game's behavior. Do not import emulator source into the platform.

Probe a supplied MAME executable with `-help`, then inspect the explicit machine
using `-listxml`, `-listmedia`, `-listbios` and `-listroms`. Device dependencies and
device BIOS alternatives can matter even when the machine reports no BIOS
options. Audit the supplied firmware with `-verifyroms` and an explicit
`-rompath`. Retain the exact executable and firmware hashes privately.
Metadata and a successful firmware audit are not game boot evidence.

Use the installed version's options, guided by the
[MAME command-line reference](https://docs.mamedev.org/commandline/commandline-all.html).
Create fresh disk copies and isolated configuration, NVRAM, state, snapshot,
diff and input directories. Disable implicit configuration, autosave and unwanted
plugins. Bound both emulated duration and wall-clock execution. Preserve failed
runs and compare source/copy hashes afterward. A write-protect flag alone is not
a substitute for source isolation.

## Text and command investigation

Start with source-bound candidate inventories. Readability under a candidate
encoding is evidence to investigate, not a license to decode every resource with
that encoding. Preserve byte positions and unknown controls. Validate consumer
references and resource boundaries before making editable records.

For command-entry games, distinguish prompt prose from parser vocabulary and
input normalization. Trace noun/verb selection, abbreviated matching, keyboard
modes and command feedback. Translating only visible instructions may leave a
game unusable. Save validated language records through the
[state APIs](translation-studio.md), with context and protected corrections.

Use installed-version keyboard bindings and capture the resulting screen.
[MAME's Lua input API](https://docs.mamedev.org/luascript/ref-input.html) exposes
natural-keyboard posting and queue state; delivery attempts alone do not prove
acceptance by a game. A keyboard-aware workflow must verify the observed action.
The platform's joypad-oriented libretro facilities must not be assumed to provide
this without an explicitly implemented and tested adapter.

Capture actual screen pixels with a verified emulator interface; see
[MAME's screen-device API](https://docs.mamedev.org/luascript/ref-devices.html).
Retain visible geometry, scale and configuration with frames. A font specimen or
instruction trace cannot replace displayed text/input evidence. Follow
[runtime evidence](runtime-evidence.md) for provenance and scoped claims.

## First localization experiment

Prove one resource's unchanged extraction/reinsertion, then one phrase and its
input behavior. Validate expected bytes, sector boundaries, pointer/loader
reachability and storage capacity. Use fresh outputs and verify patch
reconstruction. Do not normalize D88 headers or repair original inputs.
Typography decisions follow the actual renderer and the platform's
[typography policy](../TYPOGRAPHY.md), not cartridge assumptions.

For a verified multiline resource, distinguish per-line indentation from saved
wording and control bytes. Budget the entire bounded resource, including line
breaks and padding, before insertion. A shared indentation adjustment can reclaim
capacity, but it needs measured screen margins, preserved control order and
runtime verification of every affected line. Do not assume individually readable
strings imply independently expandable allocations.

Whitespace can be behavioral data. A text engine may inspect leading cells to
recognize paragraphs or decide what to retain while scrolling. Before changing
indentation, inspect both the writer and any readers of the rendered text buffer.
Initial appearance and a responsive prompt are insufficient: exercise later
messages and repeated commands. Keep whitespace-only diagnostic derivatives
separate from saved translations, preserve failures, and check whether blank
rows can trap a consumer in a loop. Do not repair such behavior by silently
changing saved wording to imitate a marker.

When repairing a text-buffer consumer, retain its independently verified entry
points and footprint, review register use at callers, and bound scans of empty
rows. Test the emitted instructions against native paragraphs, localized
paragraphs, command rows, continuation rows and empty panels. Then test a control
with the consumer change but original text: this separates fallback compatibility
from translation effects. Assert retained lines and command history at expected
screen rows in actual captures; matching scene graphics alone cannot verify
scroll preservation. Exact animation phase and successful progression are separate
claims.

Cold boot, disk changes, writable saves, reload and progression are independent
checks. Firmware audit, static decoding, emulator evidence, user approval and
hardware testing remain distinct. Keep unsupported capabilities explicit.

A structurally valid disk edit can still fail a game's own data-integrity checks.
When an original boots and an equal-length text derivative stalls, compare CPU
and disk-loader observations before blaming character encoding. Investigate
resource checksums and stored validation tables as well as control bytes. Prove
the original computation across multiple entries before updating affected
metadata; do not disable checks or guess compensating bytes. Keep actual
algorithms, tables, locations and failure evidence private unless independently
generalized with synthetic tests. Container checks do not replace this work.

## Keyboard and capture probes

MAME offers two distinct input paths. `machine.natkeyboard:dump()` reports the
installed machine's character bindings; `post()` submits literal text and
`post_coded()` accepts named keys. For direct matrix input, inspect
`machine.ioport.ports[tag].fields[name]`, call `set_value(1)` for a bounded hold,
then `clear_value()` to restore regular behavior. Use the observed port tag and
field together: display names need not be unique. Record both press and release
times. These are documented [input interfaces](https://docs.mamedev.org/luascript/ref-input.html),
not proof that a particular game's parser accepts the submitted text.

Releasing a toggle key does not necessarily restore its previous mode. Observe
the resulting mode separately from key release, and exercise the return toggle
before sending commands that depend on it. A correctly translated prompt can
coexist with input in the wrong mode; keep that scenario failure distinct from a
translation or parser defect.

For a bounded private Lua scenario, retain the subscription returned by
`emu.add_machine_frame_notifier`, schedule actions using elapsed emulated time,
and guard each action so it runs once. Capture before typing, after typing and
after submission. An empty natural-keyboard queue can coexist with no visible
response; compare actual frames. Roman letters may be converted by the game into
kana, so inspect the echoed text rather than assuming the host keyboard mode is
the game's command language. Do not carry such behavior between games without
verification.

`screen:pixels()` exposes visible dimensions independently of a requested PNG
snapshot size. Retain the dimensions alongside `screen:snapshot()` output.
Headless runs can capture screens, but a black early frame can be an unfinished
boot. Preserve that observation and try a bounded longer run before diagnosing
corrupt media. Keep an original-disk control with the same input schedule when
testing a localized derivative; compare unaffected regions and later responses.
These checks cover only their exercised route, not general gameplay or saves.

For longer routes, MAME's documented
[save/load methods](https://docs.mamedev.org/luascript/ref-core.html#running-machine)
schedule a state operation asynchronously. Confirm the resulting file and a
successful reload before using it as a checkpoint. Bind it to the exact disk,
emulator, configuration and route; a state from a different build is not an
interchangeable starting point. Preserve a separate cold-boot check. Loading a
state may change emulated time, so schedule subsequent inputs relative to the
confirmed load rather than assuming a monotonically advancing clock.
Check the installed version's filename handling: a relative state name may gain
the configured machine subdirectory and an extension, while an absolute filename
can be used literally. Preserve the actual generated filename instead of stripping
an extension by assumption. A restored clock can also reach an absolute run
deadline immediately. Bind a separate additional-duration budget to the saved
time and retain the wall-clock watchdog; never infer a successful reload merely
because the clock eventually passes the checkpoint's timestamp.

Include an idle control before attributing an event to a command. An initial
submission may advance a scripted event without exercising the requested action.
Test individual verbs or directions before combining them, and distinguish
accepted input, an error response, a location transition and a subsequent command
in the new location. Confirm navigation with changed scene content and follow-up
responses, not echoed text alone.

For conversation changes, branch from the same starting route into repeated
listening and a different follow-up action. Compare each branch with its own
original-disk control; repeated dialogue can expose retention or event-state
differences that a single display misses. If an action requests clarification,
record that parser response separately from successful movement or interaction.
Preserved dialogue history and an unchanged clarification response are useful
checks, but they do not establish that the requested action completed.

When a verb alone requests an object, test explicit noun/verb combinations from
the same pre-action state and retain the echoed input. Verify word order and
punctuation through the installed keyboard path; a noun seen in display text is
only a parser candidate. Establish success with the destination or interior,
its response text, and a subsequent interaction. Keep verb-order equivalence
limited to the commands and state actually exercised.

Retest an interaction with its object present and absent before diagnosing a
parser regression. A valid command may fail after a vehicle departs or another
scene condition changes. Record the intervening actions and test waiting as an
explicit command separately from leaving the emulator idle. Preserve the failed
attempt as evidence of its state, rather than discarding it after finding a route.

When timed screenshot comparisons differ, retain the failed expectation and
repeat the original control to check repeatability. Compare text history, cursor
blink and animated regions separately from scene progression. A later matching
frame can establish convergence without proving equal timing; do not mask a
region merely to turn an unexplained mismatch into a pass.

## Complete text inventories and packing experiments

Regex text runs are discovery aids, not completeness checks. Reconcile them with
the actual loader tables and display consumers. Include default replies before
the first separator, records crossing sector or track boundaries, null-terminated
interface strings, indexed location labels, and nonstandard single-byte glyphs.
Classify parser vocabulary, control records, duplicate data and graphics text
separately. An apparent duplicate is not proven unused merely because a known
loader table omits it.

Audit text embedded in graphics as well as character streams. Decode referenced
backgrounds, animation images and populated inventory rows into private review
artifacts, retaining each source span and consumer. A static reconstruction can
establish lettering and storage coverage, but its palette may differ from the
runtime palette and it is not gameplay evidence. Check empty, populated and
maximum-length interfaces in the emulator. If a diagnostic injects inventory or
scene state, label it separately from naturally reached gameplay.

For host-composed replacement lettering, preserve item artwork and interaction
geometry, measure native ink bounds, retain font attribution, and prove that the
encoded raster round-trips. Deduplicate identical assets only after tracing all
references and rebuilding their pointers. Reuse only the verified allocation;
unconsumed padding is not free space merely because it looks empty. Keep the
actual compression format, image tables and adaptations in the private project.

If compressed text is needed, freeze the wording first and verify exact decoding
of every record. Preserve separator semantics, blank-message thresholds and
opaque allocation tails; short encoded strings can accidentally enter a native
empty-message branch. Check dictionary acyclicity, recursion/stack bounds,
register preservation and all token values in the actual decoder instructions.
Static packing success does not validate a code allocation, its lifetime,
indirect callers, timing or gameplay. Keep those findings and the game's actual
dictionary private. Validate both cold boot and later inputs before treating an
experimental packed build as a usable checkpoint.

## Translating typed commands

Bind translated vocabulary to the original action and object identities. A
translated display noun does not automatically become valid parser input.
Determine whether matching uses full words, fixed prefixes or ordered synonyms;
audit collisions across the complete vocabulary before inserting a table. If an
additional character disambiguates collisions, test both alternatives and short
inputs in the actual resolver instructions. Preserve the native dictionary when
supporting both input modes, and test unknown and missing words independently.

Input conversion and command matching are separate consumers. Before reclaiming
a conversion routine, trace direct callers, fall-through paths, shared character
append helpers, keypad input, editing controls and mode toggles. Test case
normalization and correction of a mistyped command through the actual keyboard
path. Document accepted word order, abbreviations and multiword-object rules;
do not imply natural-language input merely because commands use English.

Treat page advances as explicit events in a playthrough. A submitted command can
be consumed by a pending narrative pause without executing its action. Record
the visible prompt and resulting scene after each submission; insert separate
Return events where the game requests them. Continue from pinned checkpoints
of the same build, and retain failed routes as evidence. Reaching an ending from
a supplied save does not establish a complete cold-boot playthrough.
If a harness detects prompts from visible text, distinguish an active pause from
an older prompt retained in scrolling history. A matching phrase anywhere on
screen is insufficient; inspect subsequent output and verify the next action.

## Writable media and persistent saves

Image loading and image saving are separate emulator capabilities. Check the
installed tool's format help and the selected driver's write support before
diagnosing a translation regression or a write-protection flag. An in-session
save/load round trip can succeed while the host image remains unchanged.

If a supported writable format is needed, convert a pinned derivative into a
fresh working image, retain the original container, and verify the conversion.
For ordinary MFM sector media, independent decoding can compare ordered sector
identifiers, data marks, payloads and CRCs. Sector equivalence does not establish
preservation of physical flux or unusual copy protection. Repeat conversion to
check determinism where reproducibility is required.

Verify persistence by saving a recognizable location and inventory, exiting the
emulator completely, then cold-booting the saved working disk in a fresh process
without a checkpoint. Compare the recovered state and actual frames; test the
original-language control separately. Record which slots and states were tested.
Keep the writable disk between interactive sessions; never recreate it from the
clean seed on every launch. Prevent concurrent writers and retain backups before
opening the working disk. Preserve failed scenarios when scripted events consume
a save/load command before its menu appears.

Exercise every advertised slot, then overwrite one with a legitimately reached,
distinguishable state and reload both the replaced slot and its neighbors. Equal
initial saves alone cannot detect a slot-selection alias. Test cancellation at
each offered menu separately from confirmation-time reselection. A cancel-only
run on a disposable image allows an exact before/after media comparison; compare
the in-memory state as well. Do not use a player's persistent disk for these
destructive slot tests.

For optional responses, trace the native action/object table before treating a
reasonable-sounding phrase as supported input. Related nouns may resolve to
different identities, and prose describing an action need not be triggered by
the verb suggested by its English wording. Confirm the actual response and
subsequent navigation. A one-shot event may consume the next submitted command;
retain that distinction instead of counting the command's intended action as
tested. Keep game-specific vocabulary, conditions and event sequences private.

Build optional-branch coverage from source-bound records and explicit scenario
states. Searching retained visible-text logs can prioritize missing candidates,
but does not prove visual quality or exhaustive coverage: history may contain an
earlier response, repeated text can have multiple owners, and a complete message
can span several frames. Bind reviewed frames to the actual build and record
revision; preserve automated discovery separately from assessed evidence.

Inspect action-table ordering when an optional response is hidden by an automatic
transition. A specific action may be checked before the unconditional departure
or arrival rule. Exercise that action while legitimately in the relevant state,
then verify the transition still works. Do not change timing or inject flags to
make a plausible command reach a branch. Test one-shot responses again and retain
the second result separately; a normal fallback after the first activation need
not be a localization regression.

For story-dependent dialogue, replay the same command sequence from separate
legitimately reached checkpoints on either side of the relevant event. Pin both
states and compare the loaded action data and observed condition values before
attributing a response difference to translation. Other state may differ too;
do not describe two full gameplay checkpoints as a single-variable experiment.
Verify both expected responses and a subsequent normal interaction or exit.

A scenario ending on a narrative pause is a valid checkpoint, not evidence that
the transition completed. Preserve that checkpoint, then explicitly resume and
advance the remaining pages before asserting combat, escape or navigation success.
Keep the initial display assertion separate from the completed transition.

Do not treat non-ASCII bytes in a captured text buffer as untranslated glyphs
without checking the actual frame and display encoding. A machine-specific blank
cell can become a replacement character in a host-side diagnostic decoder.
Retain the raw bytes and frame together; annotate verified display behavior in
the private review rather than rewriting game text to satisfy an ASCII scan.
