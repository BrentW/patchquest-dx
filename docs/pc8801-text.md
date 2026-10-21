# PC-8801 text and BASIC storage research

The shared platform provides explicit, read-only storage primitives, not a
complete PC-8801 filesystem, BASIC interpreter, translator or emulator adapter.
See [D88 containers](disk-images.md) and [runtime evidence](runtime-evidence.md).

## Keep container, file and program addresses separate

D88 sector headers are not file bytes. Track slots, CHRN sector identities,
physical ordinal order and filesystem allocation order are distinct. Extra,
duplicate, mixed-size or protection-related sectors must remain in the original
container; their presence does not authorize including them in every file stream
or deleting them. Never infer a file by concatenating all container payloads.

`patchquest.storage.basic_records.gather(source, ranges)` assembles explicitly
selected `(offset, length)` ranges in caller order. It rejects overlap and
out-of-bounds ranges, captures immutable bytes and returns a source map.
`source_ranges(offset, length)` maps a logical span back to one or more original
byte ranges. Thus a string crossing a sector boundary retains exact provenance.
The private adapter must establish allocation/ordering and source SHA-256 first.
Gathering is not proof that selected sectors belong to one file.

## Linked program records

`parse_lines(data, base_address=...)` validates a narrow linked-record profile:
little-endian 16-bit next address, 16-bit line number, opaque body and a trailing
NUL immediately before the next record. A zero link ends the program. Addresses
are interpreted relative to the caller-supplied address of the first byte; no
load address, dialect or source header is guessed. Forward bounds, increasing
line numbers and terminal links are checked. The returned program retains every
supplied byte, including unused tail bytes, for exact reconstruction.

Do not split tokenized program bodies at every NUL: packed numeric operands can
contain zero bytes. Do not decode all high bytes as kana: the same byte can be a
keyword token outside a string and a character inside one. Quoted strings,
comments, DATA fields, extended tokens and binary operands need lexical context.
The shared record reader deliberately leaves bodies opaque; it is not a
detokenizer or editable program serializer. It does not relocate links.

References consulted for format interpretation:
[N88 binary-file converter author's implementation](https://github.com/mumriks/b2an88b)
and [N88 command reference](https://github.com/barbeque/n88-basic-reference).
These are research references, not imported dependencies. Implementation and
tests here are independently authored; no third-party implementation, token
table, game program or firmware is incorporated. The code/docs/tests use the
platform's Apache-2.0 scope. Tests use invented opaque records and addresses.

## Validation before translation insertion

Establish the directory/allocation chain and actual program consumer privately.
Bind each string to its source hash, logical program offset, line and original
sector spans. Keep observations separate from inferred statement semantics.
A parsed PRINT statement is static evidence, not proof of its rendered frame,
color, pixel width, keyboard behavior or runtime branch coverage.

Reconstruct unchanged program and container bytes before editing. Length changes
may affect later line links, allocation and branches independently of visible
layout. Preserve error handlers, waits, disk operations and parser vocabulary.
Use fresh OutputPolicy destinations and immutable revision snapshots for later
builds. No checksum repair from a cartridge platform applies to a disk image.

Private findings and recipes remain private. Promote general format rules and
independently tested tools here so multiple PC-8801 projects can reuse them;
never put game offsets, strings, sector chains or proprietary evidence in these
public instructions. There is no automatic claim that another title shares a
filesystem, encoding or renderer.

## Explicit FAT8 allocation inspection

`patchquest.storage.fat8` adds read-only chain checks. `agree(copies)` requires
the supplied table copies to match exactly; disagreement fails rather than
selecting a majority or repairing media. `walk(table, start, cluster_count=...,
sectors_per_cluster=..., terminal_first=...)` returns cluster order and occupied
sector counts, rejecting cycles, invalid links and reserved/unused markers.
The terminal range represents the number of occupied sectors in the last
cluster. `crosslinks(named_chains)` reports shared clusters without deciding
which file owns them. Profile parameters and source geometry remain explicit.

The N88 directory profile described by
[L3DiskEx's author](https://github.com/bml3mk5/L3DiskEx/blob/master/src/basicfmt/basiccommon.h)
uses 16-byte entries: six name bytes, three extension bytes, attribute byte,
starting-cluster byte and five reserved bytes. Its
[FAT8 implementation](https://github.com/bml3mk5/L3DiskEx/blob/master/src/basicfmt/basicdiritem_fat8.cpp)
also documents terminal markers encoding the last cluster's sector count.
These format facts are references only; no upstream implementation is copied,
linked or imported. The new helper and synthetic tables are independently authored
under Apache-2.0. It is not a filesystem allocator or complete directory parser.

Do not assume the usual directory track or cluster geometry for all disks.
Check all selected copies, map cluster sectors through explicit CHRN identities,
retain their physical ordinals and offsets, and compare file-type headers and
program boundaries with the allocation result. A rounded occupied-sector count
is not an exact logical file length. Files may have meaningful trailing bytes.
Directory labels, deleted entries and terminators require separate handling.

A crosslink or inconsistent program boundary is evidence to investigate, not
authorization to fix a directory or reuse apparently free storage. Custom
loaders can read outside ordinary directory chains or alter metadata in memory.
Keep conflicting observations and avoid resizing until actual ownership is known.

## Container failures and bounded loader observations

A structurally valid D88 may still be rejected by an emulator's flux-layout
conversion. Retain the exact failure and original input. If investigating with
a deliberately modified container, record every omitted/rearranged sector,
verify all retained payloads, and label results as modified-media experiments.
A diagnostic copy that mounts does not establish protection fidelity or a valid
original boot. Do not silently substitute it for the project's original.

Use independently bounded samples of each CPU domain and passive I/O taps to
localize a stall. Limit trace volume, preserve device tags, times and active
memory mapping; observe callbacks must not return replacement values. The
[MAME memory API](https://docs.mamedev.org/luascript/ref-mem.html) documents
address-space reads and pass-through handlers. Byte-for-byte comparison between
a static reconstruction and captured memory can validate a loader step without
claiming later game execution. Capture actual frames separately, and test that
the intended stage was reached: a zero process exit alone is not boot success.

### Following a disk handshake across CPUs

Distinguish host-to-disk commands from disk-controller commands: the same numeric
value need not mean the same operation at the two interfaces. Capture both
directions, identify command/result boundaries, and retain CPU domain and phase.
For example, the controller's READ ID result reports status followed by CHRN;
it is not sector payload. Consult the pinned emulator's
[controller implementation](https://github.com/mamedev/mame/blob/mame0289/src/devices/machine/upd765.cpp)
when interpreting controller traffic. Do not mistake successful ID reads for a
successful data read or host transfer.

A late sampled PC may be a consequence of an earlier failure. Inspect the return
stack and compare captured RAM with the code originally loaded there. Capture
earlier stages when code is decoded, relocated or overwritten. Keep transforms
and source-to-RAM comparisons reproducible privately; linear disassembly of
encoded bytes, tables or data does not establish executable control flow.

Extra sector IDs can be inputs to loader checks even when ordinary filesystem
files do not reference them. A modified-media experiment must identify which
original properties it preserves and which it omits. Reaching a title or credits
screen on that experiment establishes that bounded result only; it does not
validate the original container, later disk accesses, saves or a translation.

### Resolving an allocation conflict

Map a shared cluster into each candidate file's logical byte ranges. Check
whether it starts at a record boundary, inside a record, or after a logical
terminator. Preserve the complete allocation, including its trailing bytes.
A directory entry pointing inside another program does not establish an alias,
free space or a repair. Inspect the consumer before assigning ownership.

Compare source directory bytes with host-received bytes separately from program
payloads. A custom loader can transfer an extent directly while directory entries
remain unchanged. Matching a captured payload proves the observed transfer, not
that the ordinary FAT chain explains it. Retain framing, capture limits and the
explicit source map; a byte match without those qualifications is only a lead.

## Reusable tools available to another project

| Component | Supported use | Limit |
| --- | --- | --- |
| `storage.d88` | Inspect containers and retain sector identity/offsets | Parsing does not prove emulator compatibility |
| `basic_records.gather` / `source_ranges` | Assemble explicit extents and map logical bytes back to source | Caller proves allocation and ordering |
| `basic_records.parse_lines` | Validate linked records and preserve all supplied bytes | No dialect inference, detokenization or relocation |
| `fat8.agree` / `walk` | Check copies, links and terminal sector counts under an explicit profile | No automatic profile or repair |
| `fat8.crosslinks` | Report clusters shared by candidate chains | Does not decide ownership or reusable capacity |
| `delimited_records.parse_records` | Read a caller-bounded, explicitly counted message pool | No encoding, ownership, relocation or writer inference |

These tools can be imported by private project runners without depending on
another game's workspace. Emulator scenarios, actual loader decoders and file
adapters remain private until a general API has independent synthetic coverage.

## Startup consumers and the first interactive scene

Keep a directory filename, a BASIC label, a variable containing a filename and a
boot command distinct. Matching names are not evidence that they share a consumer.
Observe the startup command buffer and trace the executed entry point: a loader
may transfer a program directly and start it without opening its apparent startup
directory entry. Retain the command's source sector and the observed CPU/time.
An ending-program reference in parsed BASIC is static evidence until the branch
is exercised; do not promote it into an ending-playthrough claim.

Advance one observed input stage at a time. Credits can contain several separate
key waits before a title menu requests a specific choice. Record key-down and
key-up times, release every injected key, and capture the transition. Use the
emulator's discovered keyboard fields or documented text-input API; do not infer
acceptance from an empty input queue. A visible command prompt establishes that
screen, not command acceptance or parser coverage. Keep later test inputs out of
an earlier prompt screenshot used as a baseline.

Text resources can be selected numerically through raw-sector reads even when
graphics or executable files use directory chains. Compare an entire captured
resource buffer with explicitly mapped source sectors and inspect the selecting
consumer. Keep resource headers, control bytes, prose and parser vocabulary
separate. A byte-exact buffer match does not identify every field's semantics;
visible text still needs its own frame and boundary evidence. Do not assume a
filename variable used by an error handler proves a filesystem file was opened.

## Bounded delimiter records and command vocabulary

`storage.delimited_records.parse_records(data, delimiter=..., count=...)` reads
an explicit number of terminated, opaque records from a caller-bounded extent.
It retains empty records, body offsets and every trailing byte. Missing delimiters
fail within that extent rather than scanning into adjacent binary structures.
Combine its offsets with `basic_records.gather` source maps for cross-sector
provenance. Record count, delimiter, extent and encoding need consumer evidence;
the helper does not infer any of them or supply an insertion/relocation API.

Message selection may use an ordinal rather than an address. Trace how the
consumer scans delimiters and how command/action records select messages before
repacking text. Preserve empty messages and numbering. Apparent trailing padding
does not by itself establish writable capacity. Keep headers and command/action
records outside the text decoder, and validate byte-exact reconstruction first.

Command entry can include a game-owned conversion layer between keyboard events
and parser tokens. Test letter case, word order and argument boundaries explicitly.
Inspect separate language dictionaries before assuming translated commands need
a new parser. A successful verb-only submission may invoke a generic response;
test a specific verb/noun pair and correlate its selected message with a frame.
Matching response text is useful evidence, but does not prove every synonym,
abbreviation, input-editing key or action is supported.

## Full-sector compatibility experiments

Separate a container reader's synthesized track layout from the sector contents.
A bit-budget failure can precede game execution: changing firmware or patching
the game's loader will not establish a fix for that failure. The pinned
[MAME D88 reader](https://github.com/mamedev/mame/blob/mame0289/src/lib/formats/d88_dsk.cpp)
and [track builder](https://github.com/mamedev/mame/blob/mame0289/src/lib/formats/flopimg.cpp)
provide reference implementations for investigating these boundaries. Consult
the exact installed revision; do not assume a later implementation behaves alike.

A track-image experiment can retain sector content while reconstructing gaps
that a sector container does not specify. Preserve the ordered CHRN identities,
declared and actual sizes, payloads, density, deleted marks and error semantics.
Reject unsupported flags rather than clearing them. Retain original container
metadata separately. Never describe reconstructed gaps as original flux timing.
In particular, ID-to-data spacing is a controller constraint: a stream that
passes a custom decoder can still fail the actual controller's read path.

Verify the final serialized image independently of the writer's intermediate
buffers: reread its directory, head interleaving and bit order, find address
marks, check ID/data CRCs, and compare every ordered sector with the pinned
source. For [HFE v1](https://github.com/mamedev/mame/blob/mame0289/src/lib/formats/hxchfe_dsk.cpp),
account for padding before the last partial second-head block when recording
track lengths. A self-roundtrip is only a static check. Cold-boot the converted
untranslated image and capture the intended prompt and accepted command before
using the same representation for an English comparison. Preserve failed trials.
Keep direct original-container boot, full-sector converted boot, reconstructed
timing, and physical-media fidelity as separate claims.

When several conversion parameters changed between a failed and successful
trial, isolate them with fresh copies rather than attributing success to one
change. Hold payloads, ordering and unrelated tracks constant; compare the first
expected sector transfer as well as the eventual screen. A short boot probe
establishes only the stages it captures. A standalone converter failing at the
same track-builder boundary helps separate container support from machine BIOS
and input configuration, but converters sharing an implementation are not
independent format validators.

Separate the minimum track footprint from adjustable inter-sector spacing.
Account for the index region, synchronized ID and data fields, checksums,
ID-to-data spacing and actual payload lengths before adding gaps between sectors.
If that minimum already exceeds the revolution budget, reducing only the
inter-sector gap cannot make the layout fit. Compare a calculated first failure
with the actual reader error across pinned variants; matching failures do not
identify which variant is historically correct. The installed implementation's
[default field parameters](https://github.com/mamedev/mame/blob/mame0289/src/lib/formats/flopimg.h)
and media-type branch determine which assumptions apply. A drive or CPU option
does not override a budget selected entirely from the container header. Do not
change header geometry merely to bypass this check: that creates another
representation requiring its own controller and content validation.

Extend an untranslated conversion control beyond its first prompt before using
it to isolate later translation failures. Travel through ordinary commands,
write one new save into a disposable copy, decode the resulting sectors and
compare the exact expected save payload while checking every other sector.
Start a fresh emulator process with that saved copy, select the slot through the
native interface, compare restored progress and issue another command. Keep the
original-content control separate from the translated run and direct-container
mount attempt. A successful converted save round trip does not establish direct
container support or recover the original physical timing.

Compare dump variants at several levels before changing the selected source.
Map byte differences to ordered sector identities, known save slots, parsed
message boundaries and validated command tables. Include record delimiters and
the rule-table terminator; check table structure before classifying later bytes
as trailing data. A scene identifier alone does not prove that every part of its
allocation uses the usual command-table format. Retain unclassified regions.
Check the declared load extent as well as the allocation boundary: a final
sector of repeated bytes can overlap the loaded payload. Apparent padding
therefore still needs ownership and consumer evidence.
Repeated fill bytes are a description, not proof of free space or authenticity.

Equal parsed messages can coexist with different complete resource buffers.
A runtime validator must use the tested variant's own pinned bytes, even when
its visible text matches another dump. Convert each variant independently with
all sectors preserved, retain its conversion/readback report and isolate its
existing save data from new-game controls. A successful common opening can
localize an earlier container failure, but it does not establish equivalence of
all later paths or justify replacing one source with another.

## Fixed-cell English layout experiments

An editorial newline in saved wording is not necessarily a literal newline byte
in the resource. If the observed renderer advances at a fixed cell boundary,
an adapter may implement the planned break with verified space padding. Bind
that recipe to the caller's starting column, row width, indent and line step;
do not generalize it to another window. This does not establish scrolling or
pagination. Preserve saved wording and record the encoded layout separately.

Use the shared [layout planner](dialogue-layout.md) with measured or conservative
native pixel metrics. Check actual glyph bounds on emulator frames, including
lowercase, punctuation, the longest line and the following input prompt. Compare
the graphics area and unchanged text against the same untranslated baseline.
After submitting a specific command, check both its response and the next input
state; initial prose fitting alone does not validate interaction.

Test line editing through actual key events: capture the mistyped input, corrected
input, parsed result and next prompt. Do not infer Delete/Insert behavior from
the host key name. To verify scrolling, submit enough bounded commands to fill
the window and compare retained rows at their new positions. Check that graphics
outside the text window stay fixed and another command remains usable after
scrolling. Keep this caller-specific evidence separate from arbitrary-length
message support, pagination, input-capacity limits and other window geometries.

For ordinal message pools, a private writer must preserve record count, empty
records, unselected bodies and all adjacent binary regions. Establish the bounded
pool's ownership from consumers before using trailing space. Require expected
source bytes, immutable state snapshots, unchanged roundtrips, repeatable outputs
and patch reconstruction. Record storage capacity separately from display space;
neither permits silently shortening the saved translation.

## Global responses and transition ownership

A renderer can select either a scene pool or a global pool, and can print the
first body directly instead of using its ordinary ordinal scan. A message index
alone is therefore not a stable identity: retain pool, source identity, caller,
selection state and actual read span. Inspect global fallback paths separately
from matched scene rules. The same typed verb with a missing or unknown noun
can take a different path from a successful verb/noun pair.
A per-delimiter search limit that resets on each iteration is not a bound on
the whole resource; validate the caller's complete selected span independently.

Widening a memory tap to cover another text pool can also include the renderer's
instructions. Filter by data address as well as CPU/PC and phase; an observation
callback may report instruction fetches alongside operand reads. Compare the
resulting ordered address/value sequence with the expected body and delimiter,
not merely a string found somewhere in the log. Retain raw traces for review.

Prove source mapping across filesystem/file headers and sector boundaries with
an explicit gathered stream. A unique match of a bounded region plus consumer
evidence supports that region; it does not prove the entire loaded program is
unchanged. Unrelated global records may contain controls, substitution slots or
opaque zero bytes. Do not decode or repack them under a scene-specific profile.
An equal-length expected-byte edit of one verified slot can preserve subsequent
addresses and delimiters without claiming ownership of the rest of the pool.

During an action transition, outgoing text can still belong to the old scene
while an identifier or loading state already names the destination. Capture the
outgoing message, intermediate frames, completed resource buffer and next input
prompt. Identify the newly loaded resource through its full source mapping;
do not assign text ownership from a single scene-ID byte or portrait. Bind each
translation to the resource that supplied it, and retain untranslated destination
text when that scene has not yet been reviewed.

Test a shared response again after a scene transition. Keep reuse evidence scoped
to the exercised callers: storage identity does not establish equal window
geometry, narrative perspective or control behavior everywhere. Before expanding
the batch, use the [narrative guide](narrative-context.md) to separate observation,
interpretation and unknowns, then freeze record revisions and the guide used for
the build. A verified command route is not evidence of a complete walkthrough or
of how an ordinary player would discover its solution.

## Conditional room introductions and interactions

A room introduction can contain an unconditional message followed by a second
message selected by header metadata and a persistent state comparison. Trace
each call separately and retain the compared state value. Do not assume the
second line requires a player command, or that translating the first message
covers the entire introduction. Validate the combined visible height, including
text retained from the outgoing room and the following command prompt.

Command tables can repeat the same verb/noun pair with different state
predicates. Record the matched row, predicate result, selected message and any
state writes. Table order and token equality alone do not establish which rule
executes. A question asking which item the player wants is a clarification;
it is not evidence that an item was awarded. Keep post-selection dialogue and
inventory changes unverified until a separate successful selection is observed.

Re-establish each destination pool's record count and source spans. A common
loader size does not imply a common message count, and a resource can cross a
physical track boundary. When repacking a verified ordinal pool, preserve
unselected bodies and the adjacent header/rules byte-for-byte. Compare repeated
builds and patch application, then test the same command sequence with native
destination text and localized destination text. Keep prior translated regions
identical between those controls to isolate the new changes.

Budget encoded whitespace as well as letters. An editorial break implemented
by fixed-cell padding consumes storage even though it adds no visible wording.
Report remaining pool space independently of pixel bounds, and fail before
insertion when either budget is exceeded. A dialogue containing several quoted
turns may preserve its original grouping without forcing a new row for every
speaker, provided attribution remains readable and the actual frame is checked.

## Coverage census and reversible text coding

Derive a complete resource census from the loader's accepted identifiers and
address calculation. Compare its mapped buffers with independently captured
loads, distinguish populated resources from unused slots, and retain blank
records as structural entries. Track repeated bodies separately by owner and
index; unique wording counts do not measure branch or runtime coverage. Keep
other text classes explicit: global responses, inventory labels, BASIC output,
image lettering, credits and system prompts can have different consumers.

An ASCII/kana subset does not establish a multibyte encoding for every other
byte. Display unresolved bytes individually in research views, retain their
positions, and compare actual glyphs before assigning Unicode identities.
Decoding a pair under an unrelated codec can produce a plausible but incorrect
character. Likewise, a zero byte inside a printed body is not automatically a
terminator or disposable padding. Preserve unresolved controls until their
consumer behavior is known.

When native line feeds appear in verified source messages, test them as a
separate layout recipe against existing space-padded wording. Compare complete
frames, retained history and later commands. A successful comparison can reclaim
storage without changing saved wording, but it applies only to those caller and
window behaviors; it does not establish pagination.

If English still exceeds the allocation, a reversible pair dictionary can be
investigated independently of editorial wording. Keep dictionary parameters,
mode markers and renderer adaptations private. Prove literal/token separation,
bounded indices, exact decompression, delimiter preservation and mode reset
before mixing encoded and native messages. A private machine-code shim also
needs expected-byte ownership, preserved caller registers, instruction-level
tests and actual emulator validation. Apparent zero-filled space alone is not
evidence of safe ownership.

Use a control with the new consumer but unchanged text to isolate the renderer
change. Separately compare encoded text against its unencoded presentation, then
exercise later native messages and state-changing commands. Bind insertion and
runtime evidence to the specific records actually checked. A complete census,
successful decompression or a large inserted batch is not a fully translated or
fully tested game.

## Repeated text and command-dependent clues

Reuse a translation only after comparing the exact source body and its local
context. Keep a separate record, revision and evidence history for each owner.
Do not propagate unresolved glyphs, provisional puzzle wording or competing
targets merely because a display-normalized string looks identical. Identical
wording does not transfer insertion or gameplay verification between branches.

For riddles and unfamiliar speech, inspect accepted command forms alongside the
displayed text before settling the English. Dictionary positions need not equal
parser token values: follow the lookup loop, its counter direction and its
termination bounds. Distinguish bare-word commands from verb/noun forms and
trace both to their response records. A statically matched answer can constrain
translation while leaving imagery, wordplay and actual gameplay unverified.
Keep phonetic drafts explicitly provisional when a language or cipher has not
been established, and include illustrated inscriptions in the text census.

Run a snapshot-bound capacity forecast as the draft corpus grows. A dictionary
chosen for a small batch can give different savings when shared across more
resources. Report per-pool deficits, individual message heights and combined
introduction heights separately, keeping unresolved bodies intact. Such a
forecast selects the next storage or presentation investigation; it neither
authorizes shortening saved wording nor counts as a successful insertion.

A nested pair dictionary can be forecast without changing media: each new token
may reference only literals or earlier tokens, making expansion acyclic. Check
exact round trips, delimiter exclusion and maximum expansion depth across the
captured corpus. Count the dictionary itself and decoder memory separately from
per-resource savings. A storage forecast does not prove safe placement, bounded
machine-stack use, register preservation or acceptable runtime timing.

When instrumenting candidate memory, distinguish emulated CPU accesses from the
debugger's own reads. A bulk RAM capture may invoke installed read taps while
reporting the paused CPU's current program counter. Guard capture operations or
classify them with explicit capture boundaries; do not infer execution from such
events. Retain the original trace and explain exclusions. Compare unchanged and
modified runs with the same instrumentation before drawing ownership conclusions.

For a split dictionary, verify each segment's source ownership and arithmetic at
segment boundaries. Repacking an ordinal pool may recover a tail only after all
consumers' valid indices, delimiters and retained blank records are accounted for.
Keep controls with the prior consumer, compare unchanged rendered wording, then
exercise new text and state-changing commands. Bounded route evidence does not
establish that an apparently unused region is safe for every game state.

Banked-memory probes must record the mapping context, not just CPU addresses.
Graphics writes can share addresses with resident code. Correlate access traces
with bank controls and verify the resident bytes after transitions; an incomplete
bank trace must remain qualified. Static bounds on adjacent consumers and sampled
byte preservation complement one another, but neither proves every route safe.

Test pagination first in a clearly labeled diagnostic using unchanged wording.
Exercise a full content page plus the continuation cue, held input, release,
a fresh press for the next page, and subsequent normal commands. Verify that the
input queue is cleared without changing gameplay state. Keep fitting production
layouts unchanged, and establish each caller's blocking/timing behavior before
enabling pagination there. Pin the narrative guide as an explicit build input so
later guide revisions do not silently change a reproduction report.

Include interface literals in the census separately from narrative pools. For
tokenized BASIC, classify quoted strings by their statement consumers: filenames,
disk signatures, and empty input sentinels are not display text. Identical wording
in separate programs may have different input-clearing behavior and needs its own
source binding. Reuse mapped spans rather than assuming a literal is contiguous
in the disk container. For fixed-span edits, verify every line link, number, end
offset, final terminator, and uninterpreted tail, as well as unchanged container
structure. Preserved byte length proves storage stability, not visual quality or
correct behavior of a disk-error or save branch; test those paths separately.

An unknown source byte can be a visible glyph, a cursor operation, or an
invisible operation with side effects. Use a labeled specimen through the actual
printer and compare it with a single-variable control run. Bind the frame and
printer-entry events to the pinned firmware and display mode. Pixel equality
does not prove timing or bookkeeping equality: an invisible byte may still take
execution time or update last-character state. Preserve control count/order until
the translated recipe has explicit placement and behavior evidence. When a glyph
shares byte values with compression tokens, leave compression mode before sending
it to the native printer and verify re-entry, rather than treating it as a token.

Save newly verified interpretations as explicit source revisions, retaining the
raw source binding and original history. Coordinated writers can use the
`source_revision: true` mode of `work-publish`; ordinary target publications
remain separate. Decoding a control does not establish where it belongs in the
translation. Keep placement concerns explicit and reassess evidence against the
new revisions before including those records in a build.

For combined introductions, trace the caller's actual sequence and sentinel rules.
A field meaning "no optional message" must not be counted as a message index;
conversely, repeated indices may represent repeated prints and must not be silently
deduplicated. Bound the worst reachable combination, including conditional text.
If one component has unresolved controls or geometry, keep the combination out of
automatic insertion until its layout is established. A broad partial build should
report every retained source record and its reason, verify both translated and
untouched bodies, and distinguish model coverage from the few routes actually
played in an emulator.

Bind control-placement recipes to both the source-byte hash and the saved target
hash. Boundary controls can sometimes retain their exact prefix/suffix order and
adjacent spaces without moving anything inside translated words; verify the
printer's actual output, not just encoded storage. A wording correction must
invalidate or explicitly rebind its recipe and receive evidence at the new record
revision. Trace the selecting noun or action before resolving number and pronouns.
An existing compression dictionary may be reused with newer records if every new
input is checked for capacity and exact decoded output. Retain its training
snapshot separately; never relabel an old forecast as belonging to new inputs.

For controls embedded in prose, preserve their sequence using reviewed semantic
anchors rather than copying source byte offsets into translated text. Require
unique anchors in the saved wording and resolve them again after line wrapping;
whitespace inserted by wrapping must not silently break placement. Verify exact
control runs, reject reordered or ambiguous anchors, and keep visible glyphs
separate from nonprinting operations. A recipe that passes the printer model
still needs evidence from its actual scene and caller before gameplay verification.

When an inserted page wait is followed by an original continue prompt, test both
waits independently. Holding and releasing the page-turn key must not also consume
the original prompt. Capture the page before, during and after the hold, then
verify that a separate input advances the scene. Choose breaks from paragraph and
sentence structure where possible; a fitting maximum-size page can still leave an
awkward one-line continuation. If native scrolling retains old continuation cues,
verify an explicit page-cleanup plan within the established text window and check
that graphics, cursor state and later input remain correct.

Trailing line feeds are part of layout capacity even when they draw no glyphs.
Bind their count and terminal placement to the source and saved target, then
account for visible rows, blank rows and the caller's own newline/prompt together.
Do not let generic paragraph wrapping silently discard them. Validate exact
printer bytes and the final screen: preserving the bytes alone can scroll the
first translated line out of view if the English uses more rows than the source.


For inventories assembled into temporary buffers, locate expansion before native
copying and length accounting. A printer-only decoder can leave the game counting
compressed bytes or copying token values into a buffer with different terminator
rules. Preserve the source pointer and loop ordinal while allowing the destination
pointer to advance for each expanded byte. Check hidden items, separators, status
suffixes, delimiter handling and the largest reachable combined label; include
terminators and prefixes in buffer-capacity calculations. Test the emitted code's
register and stack behavior separately from actual inventory screens.

A shared dictionary must satisfy all of its consumers together. Evaluate candidate
dictionaries against every resource pool, including relocated labels and decoder
code, rather than optimizing aggregate compression alone. Enlarging a table can
reduce available text storage, so recalculate all segment boundaries and token
thresholds together. Reuse only allocations with established ownership; split code
or data across owned spans with explicit branches and pointer checks if needed.
A successful model and deterministic build do not establish correct inventory
selection, wrapping or gameplay state in the emulator.


Include graphic text in the consumer census. Trace graphic calls and their resource
pointers separately from character-printer calls; a string search cannot establish
that image lettering is translated. Keep decoded previews distinct from emulator
captures. Corroborate a reconstructed graphic decoder against a source-bound,
positioned crop from an actual frame before using it to classify additional images,
and retain separate uncertainty for animation/compositing paths not yet compared.
Existing English graphic prompts may be retained after visual and input review.

For save/load validation, choose progress that differs from the preexisting slot.
A success message or changed disk-container hash does not prove changed game state
was saved: track encoding can change while all sector payloads remain identical.
Compare decoded sector identities, payloads and integrity fields, then cold-boot a
fresh copy of the written media and load the selected slot. Check scene and item
state against the pre-save state, while preserving original media and earlier saves.


For multi-disk graphic inventories, identify extracted blocks by disk identity,
resource entry and block index. Repeated filenames on different media must not
overwrite one another's previews or merge their evidence. Retain opaque bytes
between images and after the last decoded block; a convenient partition does not
establish padding ownership. Compare previews with captures selected using the
actual loaded resource identifier and position, including overlays with different
origins. Keep initial mismatches and corrected associations in the private record.

Review image lettering in narrative context. Already-localized credits/signs,
decorative marks, puzzle inscriptions and readable dialogue are distinct cases.
Preserve deliberate unreadability when it is part of a puzzle; do not silently
replace it with the solution. Import newly discovered dialogue into the same
revisioned translation state and narrative guide before image insertion, and
report it as pending even when all previously catalogued strings were inserted.


When replacing image lettering, define the editable pixel regions independently
of the compressed byte allocation. Check that all changed pixels stay inside the
reviewed text/geometry masks, preserve the palette and surrounding art, and measure
ink bounds rather than just character advances. Tiny source balloons may need a
small explicit geometry adjustment; document constrained padding and review the
result at native size. Preserve licensed font artwork and carry its notices with
font-containing private artifacts.

Validate an inverse graphic encoder against the decoded source corpus before
inserting edited pixels. Require exact pixel round trips, expected source bytes,
allocation bounds and unchanged unrelated resources. If a shorter replacement
ends naturally before the old stream's end, retain unused original bytes when
safe rather than claiming them as free space. An isolated diagnostic save can
exercise the real loader and renderer, but evidence must state that it does not
verify the normal route or its prerequisites. Pair diagnostic source/translated
runs when checking changes outside the intended image regions.

For command-rule tables, trace the consumer's stop condition before enumerating
fixed-size entries. Bytes after a terminating entry may be padding or another
structure even when they look like plausible rules. Preserve rule order and test
conditions in their observed order: an inventory-state test may reject a rule
before a secondary-object question is reached. A recognized verb and noun alone
therefore do not prove that the question is unreachable or broken. Reach the
required state through normal actions, capture the question before answering it,
and verify both the resulting text and the item-state transition. Keep speculative
route plans separate from observed command acceptance and saved progress.

Exact text-consumer traces must include blank records selected by the caller.
A scene may print its main description and then a space-only companion through
the same reader. Such records need no translated wording but still consume their
body and delimiter, and can affect layout. Derive the expected call sequence from
the header and state predicates; retain blank reads in byte comparisons while
excluding them from translated-record counts. Do not discard unmatched reads just
because the final screen looks correct.

Cold-loading a save can rerun scene initialization and print its description,
including any translated page waits. Validate restored scene and inventory bytes
separately from the visible entry sequence. Schedule page presses and releases
before subsequent commands, and verify that a held key cannot skip the next page.
A faithful save payload alone does not prove that a command issued after loading
was accepted; the game may still be waiting for the description to finish.

For a route tested across several cold boots, retain an explicit chain from each
run's saved media to the next run's pinned input. Check changed save sectors and
restored state at each handoff. Keep this evidence distinct from a continuous
playthrough, an ending reached with injected state, and coverage of optional
branches. Reusing an ending screenshot from a diagnostic run cannot validate the
normal route's prerequisites or final transition.

Do not assume that inspection or conversation commands leave story state unchanged.
Trace the action effects as well as the displayed response: an apparently
observational command may select a later branch without moving the player.
Capture the relevant flags before and after the command, then preserve a separate
save and verify the later condition through ordinary play. Keep mutually exclusive
routes and their dialogue context distinct; a shared location or similar screen
does not establish that two saves have equivalent future behavior.

Keep planned observation windows separate from the actual command schedule. Disk
loads and graphic drawing may delay text until after a fixed validation window.
Retain the failed expectation, inspect the complete trace, and bound a corrected
window before the next command. A justified timing correction must still require
the exact expected consumer bytes and printed text; it must not discard unmatched
reads or turn an unfinished screenshot into evidence of a completed message.

Trace accepted commands through their dictionary and parser tokens; do not infer
a verb from the prose of its response. A parser that compares fixed prefixes may
map a longer English word to an existing but different command. Keep verb and
noun tables distinct even when their numeric token ranges overlap. Preserve a
failed command attempt, verify its selected rejection record, then test the
correct dictionary-backed command from equivalent game state. Do not silently
add aliases or reinterpret a failure as the intended interaction.

Inventory state may encode carrying, placement, use or recovery rather than a
Boolean ownership flag. Derive visibility and action eligibility separately from
their consumers. Test a placed item across saving and cold loading, verify that
it is omitted from the carried-item list, then retrieve it through normal play
and check its exact label and order. Compare persisted game state around inventory
displays and include the status suffixes, separators, wrapping and command prompt
in visible-row checks. A nonzero flag alone cannot establish that an item is held.

Several terminal branches can converge on one ending animation. Reuse a verified
source-art comparison only after checking each branch's own prerequisites, final
text and continuation input. Keep branch-specific dialogue evidence separate from
the shared artwork result; identical ending pixels do not verify another route.

Audit optional-response coverage by record identity and current revision. Repeated
wording in different locations remains separate evidence when different resources
or rules own it. Keep source reachability, insertion, decoder execution and visible
layout distinct. A registry count identifies missing checks; it does not establish
that every catalogued record is reachable or that an older build's evidence applies
to changed code. Bind new checks to the actual build and its immutable inputs.

Global response selection needs the same scrutiny as location dialogue. Compare
the selected body's complete encoded bytes and delimiter, its decoded controls,
and the actual printer output within the command's observation window. Verify the
native verb/object tokens and required item states against the ordered source
rules. An earlier rule can shadow a later identical selector; another command may
still reach that later response. Preserve that distinction instead of adding an
alias or changing rule order to make a coverage count increase.

For rejected input, verify the recovery contract as well as the message. A save
menu may interpret a nonnumeric character as cancellation; trace that behavior
before assuming an invalid-input loop. On disposable media, compare the complete
disk and persisted state before and after cancellation, then issue another normal
command. A missing prerequisite can also return the player to another location.
Check the destination and item state, perform the legitimate recovery action, and
confirm that normal navigation still works. Fatal responses need their own
continuation and reload checks; a readable death message alone does not establish
that saved progress remains usable.

Capture memory-mapping controls and the CPU position alongside every memory dump.
During graphics drawing, addresses normally used for scene or inventory data can
expose a graphics plane instead. Apparent state changes in that CPU-visible view
must not be treated as damaged RAM without checking the mapping. Retain the raw
transitional capture and repeat the observation passively; compare the complete
resource and relevant state again after the native mapping returns. Do not switch
banks or repair bytes merely to satisfy a capture assertion. Record source reads,
loaded resources and completed screen output separately: a resource can be loaded
before its picture and text finish drawing, so an early frame cannot approve the
finished layout.

Trace disk-request ownership through the program's error handlers and requested
resource, not the wording alone. Main gameplay and an ending program may print
similar prompts from different records. With disposable copies, use the emulator's
documented [media load/unload interface](https://docs.mamedev.org/luascript/ref-devices.html#image-device-interface)
to exercise wrong or missing media, reject unexpected reset-on-load behavior, and
record each media event before the following input. Bound the run and compare
complete media afterward. Check the full emitted request and continuation sequence,
including trailing newlines; an older continuation prompt can remain in scrolling
history without being the active wait.

Disk reinsertion is not necessarily a retry of the original operation. An error
handler may cancel a failed save, resume a failed resource load, or use a separate
ending-specific recovery path. Verify each observed contract: unchanged saved
state and media for cancellation, a subsequent accepted command for gameplay,
and source-bound final output for an ending. Keep the failed-media interval and
the successful recovery as separate observations.

When rule priority hides a catalogued reply, retain the ordinary-play result.
If a controlled diagnostic is needed to check the hidden renderer path, label it
separately, assert the original state and mapping before changing a flag, limit
the alteration, and restore it afterward. Compare persisted state and media;
never create a gameplay checkpoint from the altered state. A successful diagnostic
can establish decoding and appearance without establishing natural reachability.

Test missing prerequisites in combination, using ordinary acquisition and omission
where possible. A missing key may take priority over a placed or missing quest
item, so a checklist with one case per item can miss the actual rule order. Bind
each case to the selected source rule, item states, complete response and resulting
location. Compare state around a rejection and issue a subsequent normal command;
failure text alone does not establish whether the player moved or lost an item.
Distinguish carrying equipment from equipping it even when both use one state byte.

Fatal routes can have an intermediate warning with its own continuation before
the final death screen. Trace each wait separately, then use the native old-game
flow to verify restored scene and item state. When a route writes several save
slots, compare the complete set of changed sectors against each independently
captured payload; a single-slot validator cannot silently exempt the other writes.
Keep cold loading and an in-process reload distinct. Coverage of distinct fatal
replies does not establish coverage of every command alias or every route to them.

An unchanged memory mapping does not imply an idle text renderer. A capture can
fall between the last visible sentence and completion of padding or the command
prompt, while a decoder's mutable mode byte remains active. Retain the failed
settled-state expectation and printer timing; repeat with a later passive capture
before the next action. Compare the complete resource and decoder again, rather
than masking a changed byte or treating an active print as a permanent code change.

A menu dispatcher may temporarily reuse a location-header byte as an operation
code while preserving the actual location elsewhere. Establish that behavior from
the original writer and restoration path before interpreting a changed header as
a new location or corrupted resource. Compare the menu-state resource against
that exact expected change, retain separate settled-state checks before and after
the menu, and verify the saved payload's real location independently.

A static fatal-branch inventory is a planning aid, not an exhaustive death count.
Follow the established rule-table terminator and distinguish direct destinations
from header-driven transitions, deferred warnings and native-code outcomes. Group
aliases by source record identity while retaining every selector and predicate.
Query evidence at the current record revision, then inspect its build and whether
it came from ordinary play or a diagnostic. Identical visible wording and a passing
check on another revision must not silently fill a coverage gap. Keep untested
candidates and completed scenarios in separate, reproducible private reports.

A persistent flag can carry unrelated choices in different chapters. Before naming
it after one observed response, enumerate its source writers and identify the last
applicable writer on each played route. Compare earlier legitimate saves as well
as later ones: an old checkpoint may already preserve the alternate conversation
state needed for a branch. Replay from that state and verify the selected rule,
subsequent one-time event, repeated attempt and normal exit. Keep companion-state
conditions separate from conversation-choice conditions, even when both affect
the same reply. Equal scene identities do not imply equal narrative histories.

When an object changes enemy behavior, test its full ordinary lifecycle: inactive,
activated while carried, and deployed where the game expects it. An intermediate
state may be more dangerous than either endpoint. Compare source predicates and
actual movement from each approach; matching threat text does not merge separate
location-owned replies. A warning in dialogue is not itself a fatal outcome:
verify the destination, preserved state and a subsequent accepted command. Pair
an unsafe attempt with the successful prerequisite sequence from the same pinned
save, while keeping each run and its evidence distinct.

For held-page checks, compare the full text viewport and continuation cue while
checking the pager state separately. Map markers or other graphics may animate
while text correctly waits. Preserve the original full frames and report changes
outside the comparison region; do not describe a cropped match as whole-screen
stability. If an overly broad assertion fails, retain it and its original plan,
then bind a corrected, explicitly scoped check to the same captured evidence.


For terminal transitions, review the originating reply before reviewing the shared
end screen. The end screen may scroll away part of an otherwise complete reply.
Capture the response after its printer finishes and before later text replaces it,
then capture the final outcome separately. Bind both observations to the same
accepted action and exact consumer sequence. An early visual witness does not
establish stable memory mapping or a completed resource load; keep those checks
on independently verified settled frames. If a final screenshot is incomplete,
retain it and replay the ordinary route with earlier passive captures.

Do not assign several replies to one screenshot from their saved line counts
alone. Scene entry can leave blank rows and place the command prompt at the
bottom; entering the next command may scroll away the location description
even when both strings would fit in a newly cleared viewport. Inspect the actual
retained pixels and cursor progression. Keep a separate entry capture when
needed, remove incomplete record associations from the later frame, and preserve
the original review assumption and its correction. Exact printer output proves
emission, but does not prove that a later screenshot still shows the whole text.

A secondary-object answer belongs to the pending primary action. Preserve the
question, original verb/object tokens, selected tool predicate and resulting
consumer sequence as one interaction; do not treat the answer as a newly parsed
primary command. A scripted route that omits the answer can feed its next command
into the question and invalidate every later expectation while the game keeps
running normally. Retain that failed run, repair the input schedule, and repeat
from the same immutable checkpoint instead of relabeling unintended responses.

A rule may update persistent scene presentation independently of its inventory
or story-effect list. Before asserting that an action leaves state unchanged,
inspect every rule field consumed after the response, including picture variants
and redraw flags. Derive whether a field replaces, combines or clears bits from
the native writer, then compare the complete persisted state with only those
justified changes applied. A visible picture change is useful corroboration but
does not identify the storage operation by itself. Preserve a failed invariant
when a newly traced state channel explains it; do not exempt the whole state block.

After scene and shared rule tables both fail to match, inspect the final response
dispatcher. It may choose a different text pool according to the parsed verb or
another mode, even when the fallback index is identical. Prove the failed
predicates in each table, the dispatcher selection and the actual consumer span;
do not assign every unsuccessful action to a location-owned default. If the
input sequence succeeded but a validation expectation chose the wrong owner,
retain the failed assertion and original plan. A corrected expectation can use
the same captured run only when its inputs and traces remain pinned and the new
selection is independently justified by the source path.

For refillable or consumable items, exercise the complete state cycle and repeat
the action at its endpoints. Check the empty and full descriptions, rejected
repetition, pending tool question, successful use and subsequent inventory state.
The question may leave inventory unchanged until the secondary answer is accepted.
A short acknowledgement alone cannot establish that a refill or consumption
occurred: compare the source effect and persisted state, then issue an ordinary
inspection command. Keep identical acknowledgements in different location-owned
records separate, with their own source selectors and runtime evidence.

For accelerated emulator checks, inspect the installed binary's supported options
and retain its hash and effective arguments. Remove real-time throttling without
changing the emulated CPU clock; schedule inputs, waits and captures against
emulated time. A requested speed is not a measured result. Record bounded successful
completion, observed emulated timestamps, wall duration and the emulator's reported
average over its stated interval. Distinguish a requested-duration/wall ratio from
that measured interval and account for startup, tracing and concurrent workers.
Keep the same consumer, state and image assertions at higher throughput. Headless
or muted measurements do not establish visible interactive or audio performance,
nor physical hardware timing; preserve that scope in the private report.

Distinguish an absent item from a carried item with empty contents. A description
of nearby equipment does not establish possession, and a generic failed lookup
does not identify which prerequisite is missing. Compare the actual inventory
slots and selected predicates before and after examination, pickup and reuse.
Bundle recovery can restore several slots together while access to the recovery
location depends on just one representative slot. Trace the complete effect list
and preserve all other persisted state; do not infer independent item recovery
from separate item names. Pair a route that omits pickup with an ordinary recovery
route, and verify the later trade or interaction as well as the immediate reply.

Track recognition separately for each parsed field. An unrecognized verb can
coexist with a successfully matched blank object; it need not stop the rest of
parsing. Distinguish initialization, failed-search sentinel writes and successful
match writes by their source paths and observed program counters. Validate the
final token pair and fallback selection rather than assuming invalid input emits
no parser writes. Preserve a failed instrumentation expectation when source code
explains it, and bind corrected assertions to the same immutable input and trace.

Treat travel rules as directed edges labelled by accepted commands and conditions.
Do not infer a return command by reversing a compass direction: viewpoint changes,
relative movement or authored routes can make that assumption wrong. Verify the
return edge from its own rule, then compare the loaded location identifier and
complete resource after traversal. Similar artwork, shared descriptions and a
rotating compass do not establish location identity. Where the source predicts
no lasting effects, compare all persisted state before departure and after return;
retain any intervening commands and their independent effect checks. Scope the
result to the exercised edges, rather than claiming the whole map or all aliases.

A temporary use of equipment can leave a lasting change in the surrounding world.
Do not name a flag from the command verb alone or assume the equipment stays
active after its action. Trace possession, tool state, world state and conditional
descriptions separately. Compare the complete persisted state before the action,
after it, after any pickup, and on an ordinary return to the location. Verify both
the changed description and the absence of any now-inapplicable companion text.
Re-entry checks distinguish persistent outcomes from temporary display changes;
they also keep a nearby object's availability separate from actual possession.

When several action rows share a primary verb and object, include secondary-tool
matching before deciding that an earlier row shadows a later one. A pending
question can defer final selection until the answer identifies the tool. Trace
the retained primary tokens, the secondary token, possession conditions and
ordered scan together. A rejected candidate can restore the primary pair and
parse the same answer again for a later row; preserve those repeated writes as
evidence rather than assuming each answer is parsed exactly once. Exercise a
later tool-specific row both with and without
an earlier row's tool carried, using legitimately reached states. Confirm that a
failed use preserves the complete world and inventory state, and that successful
use produces only the source-defined effects. Verify return paths separately
when those effects change which version of a location subsequent travel loads.

Repeated acknowledgements can represent different stages of one construction
process. Derive the ordered stage conditions, consumed inventory and cumulative
picture changes from the source, then compare complete state after each stage.
Exercise repetition after completion and compare alternate accepted command
forms from equivalent legitimate starting states. Matching words or pictures
alone do not establish equivalent outcomes; compare the resulting resource and
persisted state as well. Keep refill acknowledgements separate from construction
even when the same local text record is used for both.

Resolve omitted grammatical subjects from the accepted action, surrounding source
and observed outcome. First-person narration does not make every unstated subject
the player. A failed action can lose an object while play continues; inspect the
native destination, inventory changes and later accepted commands before calling
it a death response. When that evidence changes a translation, retain the earlier
revision and its issue history, rebind unchanged controls to the new wording, build
from pinned originals, and replay the corrected line. Old screenshots and consumer
reports remain evidence of the earlier wording, not proof of the correction.

Inspect local action handling before treating a resource-use command as a universal
inventory operation. A local rule can decline use without consuming anything,
while another location consumes the resource and changes travel eligibility.
Derive both paths from their ordered conditions and effects, then compare the
complete persisted state and subsequent movement. An internal item value can
encode a contextual progression state as well as possession or contents; do not
assign its meaning from the inventory label alone. Check failed movement after
successful use separately from the use acknowledgement.

Printed media advice does not by itself establish that execution is blocked on a
disk handshake. Bind the visible instruction to the script or loader path, the
actually mounted media and subsequent accepted commands. A scene already loaded
into memory can remain interactive while advising a later disk change. Verify
local actions and the next resource-crossing transition separately, retaining any
real loader request or failure rather than classifying every disk-related line
as the same kind of prompt.

When a sector reader's fixed track overhead exceeds its budget, an isolated reader
experiment can distinguish reconstruction assumptions from damaged sector data.
Pin the installed executable and matching source revision, identify the exact
layout call, and assert the original bytes and complete extent of any change.
Keep the original executable and media untouched. Adjust only the justified
reconstruction parameters; preserve controller-critical spacing and every sector.
Require an untranslated direct-container boot and accepted commands, independent
ordered-sector readback, then the localized progression test. A successful reader
experiment does not add a format writer or establish physical timing. Retain its
separate executable identity and keep writable-save testing on a verified format.

A converter can emit more nominal cylinders than the source actually contains.
Inspect the output directory and decode every emitted track rather than assuming
that excess tracks are empty. A reused conversion buffer can reproduce the last
populated track where the source has no track. Compare the populated source range
separately, classify all additional output and retain the failed whole-image
expectation. Do not use an export with unexplained or manufactured tracks as a
playable compatibility baseline. The versioned
[HFE exporter](https://github.com/mamedev/mame/blob/mame0289/src/lib/formats/hxchfe_dsk.cpp)
is one implementation where nominal geometry, buffer lifetime and unformatted-track
handling must be considered together; sector readback and geometry are distinct checks.

Before joining checkpoint-tested routes into a fresh playthrough, compare all
persisted world and inventory state at each proposed boundary. That equality
supports a plan; only a new uninterrupted process establishes the playthrough.
Remove save/load inputs and account for initialization that occurs only on a cold
load. In particular, a loaded narrative page can require an advance that an
already completed continuous entry does not. Bind the fresh input media, ordinary
commands, page events, media changes, actual frames and terminal transition to one
execution. Keep optional-branch coverage and ending-from-save evidence separate.

For sustained accelerated traces, narrow passive observers to the established
consumer ranges and call sites instead of instrumenting unrelated instruction
fetches. Preserve bank context, ordered bytes and delimiters, printer output,
complete resource/state comparisons and actual frames. Check trace ceilings and
input budgets explicitly so an exhausted log cannot appear to be a quiet success.
Measure completed runs with their exact observation profile; reduced callback
work does not justify relaxing assertions or changing the emulated CPU clock.
