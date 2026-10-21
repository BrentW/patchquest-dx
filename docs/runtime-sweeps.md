# Bounded scene and message capture

`patchquest.runtime_sweep` implements phase A of the runtime renderer workflow.
It schedules an explicit private inventory, prepares scenes through
`runtime_scenes`, captures observations in spawn workers and registers PNG bytes
through `RuntimeArtifacts`. It does not implement detectors, translate text,
approve checkpoints, discover games or launch a configured emulator implicitly.

**Capture completion is not a text pass.** Completed observations retain
`assertion: not_assessed`. Detectors consume the immutable observations and
produce their own contract-v1 `DetectorFinding` records. Synthetic adapters always
produce `method: synthetic`, including when their frames match expectations.

## Explicit inventory and setup

Create an inventory with
`case_inventory(cases, scope=..., source=..., completeness="unknown")` from
independently enumerated private `CaseSpec` records. Use stable IDs for distinct
message/page/window/context/dynamic-value variants. The source label and
completeness declaration describe that inventory; neither establishes whole-game
coverage. Up to 1,000 distinct cases in one named scope are accepted. Empty scope
is rejected rather than presented as complete.

Supply a `SceneLibrary` containing every selected scene and its regeneration
dependencies. Exercise definitions cover **every** inventoried case exactly:

```python
exercises = {
    case_id: {
        "scene_id": selected_scene_id,
        "steps": [{"frames": 30, "buttons": [], "capture": True}],
    },
}
```

The default `mode: "exercise"` has 1–500 explicit steps of 1–3,600 frames, at most
20,000 exercise frames, valid existing controller buttons and an explicit boolean capture flag.
The final step must capture. Scene preparation consumes the same per-case
observed-frame budget. Words, control codes, substitutions, widest legal names,
minimum/maximum numbers and representative windows belong in the explicit case
inventory and private setup, not a rewritten translation or guessed range.

To capture arrival without advancing after scene preparation, explicitly select
`mode: "arrival_only"` and supply `steps: []`:

```python
exercises = {
    case_id: {"scene_id": selected_scene_id, "mode": "arrival_only", "steps": []},
}
```

An empty list without this mode is invalid; arrival-only definitions reject
nonempty steps. The scene still requires its normal arrival assertions and
supported route/capabilities. Preparation still observes a fresh neutral arrival
frame after its setup, including after checkpoint restore. Those setup/arrival
frames and all retries consume the existing scene and sweep frame budgets.
Each produced preparation-attempt frame is retained under the existing capture
and storage limits, including failed-attempt diagnostics. A successful scene with
one attempt has exactly one arrival capture, with no extra step or duplicate final
capture. Failed preparation retains its failure/timeout classification and cannot
reach `observe`; unsupported preparation before stepping produces no capture.
Retries may retain multiple diagnostic captures before a ready arrival. An image
alone never establishes arrival success or overall capture completion. Identity
checks, cancellation, clean shutdown requirements and telemetry rules still apply.

The normalized definition always contains the mode: omitted and explicit
`"exercise"` are equivalent, while `"arrival_only"` is a distinct hashed plan.

When `enumerate_messages` is declared, the worker calls the adapter's
`enumerate_cases(scope)` in the loaded isolated session, validates its complete
bounded list of CaseSpecs and resets again before the actual case. Empty results
are explicit gaps. Unplanned cases and missing/changed declared definitions are
retained in manifest `inventories`/`gaps`; the runner never silently expands scope.
A requested case missing or different in that enumeration is unsupported. Each
new recovery worker repeats enumeration. Without that capability, the supplied
inventory is usable but no independent extraction-completeness claim is made.
Each enumeration and its derived gaps carry their original `run_id` and `worker`.
Those two fields identify one enumeration; worker names alone repeat across runs.
The worker's `enumeration_observed` records whether the parent accepted that event.

Optional `selection_plan` is an explicit contract-v1 `ChangeImpactPlan` matching
the complete inventory and exact target binding. Deferred cases remain
`execution: excluded` with reasons, in the planned denominator. No deferred case
inherits verification. Without a plan, every declared case is scheduled.

## Composition and adapter interface

```python
from patchquest.runtime_sweep import case_inventory, run_sweep, storage_preflight

manifest = run_sweep(
    inventory, scene_library, exercises, pinned_binding, capabilities,
    artifacts, build_references, configuration, private_adapter_factory,
    fresh_private_destination,
    limits={"worker_cases": 20, "case_seconds": 30},
)
```

### Explicit approved storage policy

An optional `storage_allowance` supplies positive integer `retained_bytes` and
`workspace_bytes` ceilings. Optional `shared_bytes` explicitly caps their sum;
omitting it or setting it to `None` keeps the categories independent. The runner
does not infer that one approved number applies separately to both categories.
For example, this invented test allocation partitions a shared 3 MiB allowance:

```python
limits = {"workspace_bytes": 2 * 1024 * 1024}
allowance = {
    "retained_bytes": 1 * 1024 * 1024,
    "workspace_bytes": 2 * 1024 * 1024,
    "shared_bytes": 3 * 1024 * 1024,
}
# artifacts must already be configured with budget_bytes <= 1 MiB.
effective = storage_preflight(artifacts, limits=limits, allowance=allowance)
# Supply these same limits and storage_allowance=allowance to run_sweep.
```

`storage_preflight` reads the configured `artifacts.budget_bytes` and normalizes
runner limits without resolving bytes, consulting the graph, creating files or
starting a worker. It rejects invalid policies and ceilings exceeding approval;
it never silently clamps or changes service settings. `run_sweep` repeats the
check before any input/resume capture resolution or worker output creation. Its
definition records detached `storage_policy` with effective retained/workspace
ceilings, their sum and the explicit allowance. Configured ceiling or policy
changes invalidate exact resume. With no policy, configured ceilings are still
recorded, but no approval is inferred. The caller owns stable service settings
throughout the call; this check is not a lock against concurrent reconfiguration.

These are separate conservative counters, even when a shared ceiling is used:
the artifact service counts all existing retained blobs plus new unique retained
bytes, while the runner counts worker journals and PNGs (including copies also
retained by the service). The sum therefore reserves both copies. Neither counter
includes native scratch, logs, final metadata or the composition root's other
files; budget those separately. This policy does not create an OS disk quota,
check free disk space or grant permission to delete/evict evidence. Constructing
the artifact service itself may create its directory; this pure helper does not.

`build_references` maps every binding artifact role to a retained `EvidenceRef`.
The parent resolves and verifies all role digests through `retained_build` before
starting a worker. Checkpoint bytes resolve through the same artifact service;
scene compatibility and arrival checks remain owned by `runtime_scenes`. Missing
or incompatible checkpoints fail the selected route; no fallback is chosen.

`configuration` is explicit JSON whose canonical sorted-key UTF-8 digest must
equal `binding.configuration_sha256`. Supply the complete immutable snapshot,
record revisions, adapter version, emulator binary/configuration and expectation
identity in the existing `RunBinding`. No placeholder identity is generated.

`private_adapter_factory(configuration)` is a trusted, spawn-picklable top-level
callable, never a shell command, executable path or import string. The factory
constructs one backend per worker. The adapter implements:

| Interface | Responsibility |
| --- | --- |
| `reset(inputs, configuration, sandbox)` | Reload all immutable role-to-bytes inputs with fresh isolated save RAM/state, using only this fresh worker sandbox |
| `describe()` | Existing runtime description with exact `kind`, emulator `sha256` and `version` |
| `capabilities()` | Explicit contract-v1 `AdapterCapabilities` |
| `configuration()` | Actual active canonical JSON configuration |
| `loaded_artifacts()` | Actual loaded role-to-SHA-256 identities |
| `step(buttons)` | Existing runtime `Frame` from one observed frame |
| `restore(bytes)`, `load_save_ram(bytes)` | Existing scene interfaces when selected and supported |
| `observe(case, frame_number)` | Optional `{glyphs, resources, controls}`; omit unavailable observations |
| `enumerate_cases(scope)` | Required only with declared `enumerate_messages` |
| `debug_setup(adapter)` | Optional explicit volatile hook only for a debug scene |
| `close()` | Release backend resources before worker completion |

The `debug_setup` callable follows the scene hook signature: it receives the
tracked adapter explicitly. Ordinary routes never receive this hook. Debug routes
keep `reach_method: debug_injection`; state routes retain `emulator_state`. Both
remain separate from normal-route evidence. The runner creates isolated test
sandboxes; hooks must remain volatile-only, preserve build inputs and never carry
modifications into release outputs. Arbitrary trusted Python is not sandboxed.

The worker resets before **every** case, including the first. A backend may
amortize initialization across cases, but cannot preserve mutated save RAM or
renderer state between them. Identities, capabilities, loaded artifacts and
configuration are checked after reset and after exercise. Existing private
runtime adapters may use a small wrapper around their load/close/describe methods;
the public runner neither imports that wrapper nor changes a backend globally.

`observe` uses contract-v1 glyph/resource/control fields. Glyph frame numbers are
absolute within this case, including scene setup. Empty observed collections
differ from `null` instrumentation. Page completion/line advancement requires
`page_advance`, scrolling requires `native_scroll`, and input-wait observation
requires `input`. Accepted input/newlines do not establish any of those facts.
Invalid or unadvertised telemetry fails the case, retains raw private diagnostics
and valid captures, and cannot become a completed observation.

Native script invocation, text-copy interception and original-address lookup are
private adapter techniques requiring project-specific evidence. Label shortcuts
according to their actual reach method. Validate buffers/resources, original
consumers, compression round trips and control semantics privately; no portable
console hook or script encoding is inferred by this runner.

## Worker and resource bounds

The parent uses a spawned process and polls completed journal events without a
blocking receive. Factory startup, per-case execution and shutdown have independent
deadlines. Timeout or cancellation terminates the worker, joins it, escalates to
kill if necessary and verifies it stopped before starting another. A worker may
not launch unmanaged child processes. A native exit or malformed protocol retains
a failed current case, then subsequent cases use a fresh worker. Failed cases are
not silently retried within that run; explicit resume can retry them later.

Defaults, overridable within the validated hard bounds:

| Limit | Default |
| --- | --- |
| Factory startup / per case | 30 seconds each |
| Shutdown grace | 2 seconds per join/kill phase |
| New-work total elapsed time | 600 seconds |
| Observed frames per case / per run | 20,000 / 100,000 |
| Captures per case | 100, including retained scene-arrival frames |
| PNG bytes per capture | 16 MiB |
| Cases per worker | 20, maximum 100 |
| Managed worker journal/capture bytes across this run | 64 MiB, maximum 100,000,000 bytes |

Elapsed allowances may be positive finite fractions up to 3,600 seconds. Cleanup
join/kill grace can extend the capture deadline. Captured frames are acknowledged
only after parent registration, providing backpressure. Managed byte accounting
covers event/staging JSON and PNG files; zero-byte acknowledgements do not consume
the allowance. `RuntimeArtifacts` separately enforces retained blob admission.
No existing blob, journal, checkpoint or save is evicted or overwritten.

The managed allowance is not an OS disk/memory quota: adapter scratch files,
native allocations, private logs and final metadata must be budgeted by the
composition root. Parent filesystem/storage/graph callbacks remain trusted and
must return within their own bounds; worker deadlines cannot interrupt a blocked
parent I/O call. Trusted adapters must not emit uncontrolled logs or spawn other
processes. A parent process crash requires inspection/stopping of any surviving
child before recovery; no automatic recovery from stale artifact locks occurs.

### Keep adapter cleanup bounded

An adapter's `close()` runs before the worker publishes `worker_done`, within
the shutdown allowance. Keep recursive workspace scans, final inventories and
report generation outside this critical path. Reserve and account for bounded
diagnostic space before execution; moving accounting later must not remove its
storage ceiling. Avoid unbounded logging during cleanup.

Record separate phase markers for accounting completion, native cleanup entry
and native cleanup return when diagnosing shutdown. A file written before a
cleanup call proves only that the writer reached that point. Neither it nor a
completed case observation establishes a clean worker exit. Retain missing return
markers, cleanup exceptions and forced termination as failures, without masking
an earlier error or attempting native cleanup twice. The parent still requires
`worker_done` and an observed clean process exit before accepting completion.

Use an invented adapter to test a completed case followed by a blocked cleanup:
the case's captures may survive while overall completion remains false. Keep
that synthetic result separate from native diagnosis. Preserve the failed native
run, and review any repair or timeout change before a new bounded attempt.

`cancelled` is an optional parent callback. Cancellation before startup records
every planned case as not run; cancellation during work retains the current
interrupted observation and leaves unscheduled cases visible. Frame counts on a
crash/interruption are acknowledged observed counts, a conservative lower bound
on what the child may have executed. Journals may contain later unacknowledged
diagnostics; they are never silently promoted into assessed evidence.

### Journal I/O diagnostics and bounded contention

Runner version `5` retains version `3`'s journal policy: each published journal is
read in sequence with a 2 MiB size bound. On Windows it uses `CreateFileW`/`ReadFile`
directly to preserve the numeric
Windows error at the failing operation; CRT-backed Python reads can lose that
code. The opened handle must identify a regular disk file, without a directory
or final reparse-point attribute, within the size bound; bytes must still match
the observed size. Other hosts use a bounded Python read. This changes no permissions, ACLs,
security settings or file contents. Host filesystem calls remain synchronous and
must return; this is not an interruptible I/O guarantee.

Only a reported Windows sharing/lock violation (`32`/`33`) is eligible for a
parent journal-read/stat retry. Each retry polls the same event sequence, waits
10 ms, and returns through the existing cancellation and startup/case/shutdown
and whole-run deadline checks. A sequence gets at most 100 retries. No retry
extends a deadline, acknowledges an unread capture, skips an event, or reruns a
failed case. After synchronous I/O returns, the parent checks cancellation and
deadlines again before accepting any event, including the final completion event.
A final published event may be read after the producer exits, within
those same bounds. Windows access denied (`5`), EACCES without a Windows code,
other I/O errors, malformed JSON, changed bytes and invalid event files fail
closed. A missing unpublished name is normal; disappearance of an event already
pending after a sharing error is a failure.

Each worker's `journal_io` records the retry limit/count, recovered events,
pending sequence/retries, retry exhaustion, and first/last/fatal numeric error
details. Error details contain the phase, sequence, exception class, `errno`,
`winerror`, Windows operation when available, and eligibility for a sharing/lock
retry. A secondary close failure is preserved alongside the primary error and
prevents retry. Null codes remain
unknown. Parent I/O failures also retain `io_error`, including non-journal phases
such as capture reading or artifact registration. Summary reasons never copy
exception messages or private filenames. A timeout/cancellation retains pending
diagnostics without relabeling it as access denial or successful recovery.

Worker staging write/publication failures remain fail closed: no child-side retry
or replacement publication is attempted. Their numeric `journal_stage_write` or
`journal_publish` diagnostics and raw traceback remain in the private worker log.
The parent cannot infer a producer's error code from its exit alone. Historical
errors recorded only as `PermissionError` remain unclassified; successful invented
sharing tests cannot diagnose a prior native failure.

## Immutable results, artifacts and resume

The destination must be new, unredirected and disjoint from retained blob storage.
The runner writes `definition.json`, unique observation JSON files, private
worker journals/PNGs/logs/sandboxes and a final `manifest.json` without reusing an
existing run directory. Event files become visible only after complete writes;
partial staging files survive failures. Raw exception traces stay in worker logs;
summaries contain exception classes, not copied private exception messages.

Each `CaseObservation` is checked against its exact CaseSpec, binding and declared
capabilities. PNG `EvidenceRef` associations retain run/case/frame identity even
when the artifact service deduplicates identical bytes. No capture alone receives
`assertion: passed`; this module does not run detector algorithms. Failed arrival,
missing capabilities, crashes, cancellation and budget refusal remain distinct
from completed unassessed capture.

The manifest retains the complete definition/digest, planned inventory, ordered
observations, worker outcomes, enumeration gaps, counts by execution, frame/time/
managed-storage metrics and prior history. `capture_complete` requires completed
capture for the whole inventory and clean worker completion. It is false with
deferred, unsupported, failed or interrupted cases. It is never a coverage or
release-readiness percentage.

Each worker records parent-monotonic startup timestamps (start request, return,
ready observed or incomplete-startup decision) and measured startup duration.
Shutdown starts when the parent observes the final case result, or when process
control is requested if no final result arrived. Its timestamps/duration include
waiting for adapter close and process exit; separate control timestamps/duration
identify the join/escalation portion. These are parent observations, not child
CPU time or a guarantee of when a buffered event was generated.

`worker_done_observed` records a protocol message only. After it, the parent
allows the remaining `shutdown_seconds` grace for normal process exit before
escalation. Clean exit additionally requires observed stopped state, exit code
zero, no terminate/kill requests and no process-control errors. The shutdown
record retains the exit code (or null), request flags, errors and final
`stopped`/`unknown` state. Crashed or hung exits cannot produce `capture_complete`
even when all case captures completed. Prior completed observations in a worker
with an unclean lifecycle are recaptured on resume; their old evidence remains.

Cancellation and timeouts skip the voluntary grace and request termination.
Termination and final kill each have a bounded join of `shutdown_seconds`;
normally completed work has at most one additional voluntary grace, shared with
adapter-close waiting. Exceptional process-control failure gets one final
bounded kill attempt. A worker whose stopped state cannot be established blocks
all subsequent workers; remaining cases are not run and the manifest retains
the unknown state for owner intervention. Parent process-control and filesystem
calls remain trusted host operations, not interruptible OS sandbox guarantees.

Pass an explicit prior `manifest.json` as `resume`. Schema, runner version, whole
definition digest, exact build/snapshot/revisions/configuration, scene and case
definitions, limits, capability declarations and selection plan must all match.
Completed current observations are reused only after every capture is resolved
and reverified. Partial/failed/unsupported/not-run cases receive fresh workers and
new observation IDs. Old failures, observations and prior manifest digest remain
in the new history. Reused observations retain their original run IDs and evidence
associations; missing/corrupt artifacts cannot inherit completion. Completed
cases in a worker with shutdown failure are recaptured so resume cannot hide the
failed lifecycle. The supplied inventory remains the planned denominator, and
`observed_frames` counts only new work in this run; reused observations keep their
original frame counts. A fresh output
destination is still mandatory. Change factory behavior with a new adapter
version; unversioned trusted-code changes cannot be detected by metadata alone.

Resume copies all prior `inventories` and `gaps` unchanged, including unplanned,
missing and changed cases. A fully reused run performs no fresh enumeration and
still exposes all known discoveries. A partial resume appends new enumeration
rows under its new run ID, even when both runs use `worker-1`. Repeated resumes
retain each original enumeration once; fresh enumeration is additional evidence,
not a replacement for earlier gaps. `capture_complete` may be true while known
unplanned cases remain: it describes capture of the declared inventory, not
extraction completeness or a clean discovery ledger.

`enumeration_history` pins each inherited enumeration's source `run_id`, exact
source manifest `manifest_sha256`, and original enumerating `worker_ids`. Entries
are added only when the supplied prior run itself enumerated; a reuse-only run
does not create a new source or relabel inherited evidence. The immediate prior
manifest digest remains in `prior` separately. These are provenance references
to immutable source manifests, not a claim that every ancestral file was reopened.

Before artifact resolution, output creation or spawn, resume validates ledger
lists, unique source/run/worker identities, worker event declarations, original
scope and normalized CaseSpecs. Every declared enumeration must have exactly one
inventory, and the entire gap list must equal the gaps derived from those
definitions. Missing, duplicate, inconsistent or unknown-origin ledger data is
refused rather than silently discarded or repaired. Retain malformed prior files
for investigation; do not edit them to fabricate provenance or successful work.

Resume additionally requires every prior worker's shutdown record to explicitly
confirm `final_state: stopped`, before any artifact resolution, output creation
or spawn. Unknown or missing stopped state blocks resume as well as subsequent
workers in the original call. Retain that immutable manifest and investigate the
host/process state with its owner; do not rewrite the manifest to claim a stop.
No external resolution/override API is provided here. Confirmed stopped workers
with nonzero exit or termination remain retryable, with their completed captures
recaptured under the existing unclean-lifecycle rule.

This implementation writes runner version `5` with the existing manifest schema
and contract-v1 observations. Positional arguments remain compatible; the storage
policy is an optional keyword. Versions `1` through `4` are refused for resume before
artifact resolution, output creation or worker startup. Version `1` lacks required
process-exit evidence; version `2` uses the previous journal policy. Version `3`
does not carry original enumeration provenance and may already have lost prior
discoveries during resume. Version `4` predates normalized exercise modes, so its
manifests cannot resume as arrival-only or version `5` plans. Missing source
evidence cannot safely be reconstructed
from that supplied manifest. There is no automatic migration. Retain those
runs and frozen foundations with their original versions as historical evidence.
This resume boundary does not invalidate their original observations or require
rerunning previously accepted bounded evidence for downstream analysis.
Use a fresh destination for new capture; never rewrite an old manifest to version
`5`. Private lifecycle checks and wrappers must derive the actual runner version
rather than hardcoding a historical version.

## Authoritative state and downstream gates

Construct the artifact service with `ArtifactState(store, dedicated_directory)`
and `graph_guard=connector.guard` from `runtime_artifact_state`. After the run,
publish `manifest["observations"]` through
`connector.record_run(build_id, observations, expected=current_build_revision)`.
This existing Store/build CAS path preserves distinct run/failure associations
and build history without a new reference database. Do not hold the graph guard
while calling artifact registration. If publication conflicts, retain the run,
reread current state and reconcile; never bypass CAS or rewrite completed files.
No private project is selected or written automatically by this composition.

The public tests connect actual Store/ArtifactState APIs on invented temporary
projects and verify retained failures plus unchanged human records/build bytes.
Other tests use a complete empty graph **only** for their isolated invented store;
that fixture is not a production graph fallback.

Phase A `runner-v1-ready` supplies this observation seam to detectors while the
pilot issue stays open. Synthetic subprocess tests prove orchestration and failure
handling, not actual emulator pixels. Actual scene arrival, detector positive/
negative controls and deliberate faults, a bounded renderer pilot and separate
normal-gameplay/cold-boot/save-persistence checks require explicit private project
and resource claims. No private pilot, detector-controls gate, gameplay/hardware
compatibility or checkpoint approval follows from this implementation.

Run invented checks with Python 3.10+:

```text
python -B -m unittest discover -s tests -p test_runtime_sweep.py -v
```
