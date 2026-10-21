# Runtime artifact storage

`patchquest.runtime_artifacts` supplies private content-addressed bytes using
contract-v1 EvidenceRef and RunBinding. It never discovers projects, executes
emulators, changes translations, creates checkpoints automatically, maintains a
metadata database or deletes retained artifacts. Code, guide and independently
invented tests fall under the repository Apache-2.0 scope.

## State and job integration

Construct `RuntimeArtifacts(directory, budget_bytes=..., graph_guard=...)` with
an explicit dedicated private blob directory. The existing composition root must
supply a callable returning a context manager which yields a complete snapshot
and excludes reference/lease changes throughout the context. It uses the existing
state/Jobs/Coordination interfaces to evaluate lease expiry and current fences.
Lock order is artifact writer lock, then state/job graph guard. Do not already
hold that guard when calling this service. A cached or guessed empty graph is
unsafe; no default graph or fallback database exists.

The snapshot has exactly these fields:

| Field | Meaning |
| --- | --- |
| `revision` | Nonempty revision token covering all contributing state/job views |
| `complete` | Must be true; incomplete or uncertain graphs fail closed |
| `references` | Links `{sha256, kind, id}`; kind is run, failure, tester_report, checkpoint_approval, attachment or build |
| `pins` | Explicit pinned SHA-256 values |
| `leases` | `{sha256, owner, active}` decisions from authoritative task/build lease owners |
| `ownership` | Digest-to-classification map: managed, original, user_save, checkpoint or unknown |

The complete graph must represent all retained failure/approval references,
active consumers and evidence retention policies even when supplied EvidenceRefs
cover a smaller scope. Unknown ownership retains bytes. Only explicitly managed,
verified, disposable, unreferenced bytes without active leases can become deletion
proposals. Originals, saves and checkpoints remain protected independently of
reference count. Only the lease owner determines whether expiry releases a resource.

The integration owner wires this guard and publishes returned EvidenceRefs through
existing revisioned state APIs. This library does not imply a connected Studio
view, state migration, CLI or private sweep runner. Existing screenshot uploads
have one metadata record per digest: retain distinct runtime associations in
run/case records instead of replacing screenshot metadata. No shared module edit
is needed for this library interface; live graph wiring is a separate handoff.

## Optional resolution-only guard

A composition root may supply `RuntimeArtifacts(..., graph_guard=connector.guard,
read_guard=connector.read_guard)` for an `ArtifactState` attached to the SAME
existing Store and dedicated directory. The optional guard is used only by
`resolve` and existing callers that delegate to it. Without it, the original full
graph guard remains the default. Both guards remain explicit trusted local
configuration; browser input cannot choose either owner or a database.

`ArtifactState.read_guard()` keeps the same artifact-lock-then-Store lock order,
uses `BEGIN IMMEDIATE` to exclude authoritative writers, and validates the complete
schema and selected project/source identity for every read. It yields no graph,
reference completeness, or deletion authority. It does not scan retained history,
build payloads, policy references or leases because resolution cannot release or
change any of them. No persistent graph cache or extra database is created.

The directory writer lock and exact byte-length/SHA-256 verification are retained
on EVERY resolution. Changed/missing bytes remain unavailable; results are detached
immutable bytes. Registration, recovery registration, admission estimates, retention
plans and plan rechecks still require the FULL current reference graph. An unknown
schema or changed selected identity refuses resolution. Unknown reference content
continues to fail or conservatively protect bytes in full-graph operations; the
resolution guard never certifies it as complete or authorizes its removal.

This avoids reference-history work on each immutable byte read; it is not a cached
integrity result. Owners must bind both supplied guards to the same authoritative
service and preserve normal caller serialization for parallel requests.

## Bytes, references and worker inputs

`reference(data, evidence_id=..., media_type=..., provenance=...,
retention="referenced")` creates an unverified EvidenceRef.
`register(reference, data)` checks digest/length, deduplicates bytes exclusively
through OutputPolicy and returns a detached verified reference. Every returned
reference retains its own evidence ID, producer, method, run and case. Identical
bytes do not erase case associations or promote synthetic provenance. The caller
persists associations through existing state APIs. A crash before publication
leaves conservative unreferenced bytes, not a passing observation.

`resolve(reference)` returns `{available, evidence, data, reason}`. It rechecks
actual bytes and returns immutable Python bytes, never a canonical write path.
Missing/changed files return available false, data null and integrity missing or
mismatch. Consumers must preserve the unavailable-evidence outcome and cannot
count it as a passing capture. Invalid requests or uncertain ownership raise
ArtifactError. Successful resolution does not itself certify execution/assertions.

`retained_build(binding, role, reference)` also checks the RunBinding role digest.
Register a retained build once and reuse its verified reference instead of cloning
a ROM or state per message. An adapter accepting immutable bytes can use resolution
directly. An adapter that may modify file inputs needs
`worker_copy(reference, destination, budget_bytes=...)`: exclusive, independently
verified creation through OutputPolicy in an existing explicit parent outside
retained storage. The adapter receives only that disposable path. The allowance
limits this one copy; its caller owns aggregate external workspace accounting.
No canonical artifact, original or save becomes a writable worker file.

`restore(reference, retained_identical)` reads one explicitly supplied retained
source and registers identical hash-verified bytes. Missing destinations can be
restored; changed destinations and wrong sources are rejected. Recovery sources
remain read-only. No corrupt evidence is silently repaired or overwritten.

## Budgets and interrupted workers

The budget counts physical blob bytes in the selected directory.
`budget(additional_bytes)` reports current usage, allowance and explicit incomplete
execution information; it is an estimate, not a reservation. `register` serializes
admission under an exclusive writer lock and rechecks sizes. Cooperating writers
cannot overbook; deduplicated bytes add zero usage. BudgetExceeded means reduce
the declared batch or record interruption/incompleteness. Never silently evict
required evidence, skip captures or award passes. Actual I/O failures likewise
require a failed/interrupted runner outcome. Count all other storage separately.

Interrupted writes may leave a partial blob and `.writer-lock`. Partial bytes are
retained for diagnosis and resolve as mismatched. ArtifactBusy never steals locks
based on age: an operator must inspect the lock and confirm the original worker
has stopped before recovering it. A normal exception releases only its own
operational lock; no artifact cleanup or overwrite-resume occurs.

These checks coordinate cooperating local callers, not hostile processes or
hard-link mutation/filesystem races. Keep canonical directories private and under
the project owner's control. Never select a general output folder, original
collection, saves or checkpoints as blob storage. Unexpected directory entries,
symlink redirects and malformed graphs fail closed.

## Dry-run retention

`retention_plan(evidence_refs)` inventories all blobs plus supplied references and
graph links/pins: digest, size (null when missing), integrity, every supplied
evidence identity, reasons and retain/propose_delete action. Recoverability is
explicitly not_established: a surviving source is never assumed. Reports include
graph revision, budget, dry_run true and a digest of the inventory. Duplicate
evidence identities fail. Nothing is deleted, including after interrupted review.

`recheck_plan(plan, evidence_refs)` repeats complete guarded graph/file checks and
rejects changed bytes, inventories, revisions, pins or leases. It remains a dry
run. A future separately authorized deletion executor must recheck hashes,
references, ownership, recoverability and leases while retaining exclusion through
mutation. A successful dry run is not permission to delete later. Current-artifact
deletion is outside this interface. Catalog completeness never releases evidence.

Run independent synthetic checks from the platform root with Python 3.10+:

```text
python -B -m unittest discover -s tests -p test_runtime_artifacts.py -v
python -B -m unittest discover -s tests -p test_runtime_contracts.py -v
```

Tests cover provenance, preservation, budget races, active leases, changed/missing
files, interrupted locks/review and identical-source restoration. They provide
no emulator, gameplay, editorial or hardware approval.

## Authoritative Store connector

`patchquest.runtime_artifact_state.ArtifactState(store, directory)` supplies the
concrete guard for schema-3 Store/Jobs/Coordination. Select an explicit dedicated
directory under this Store's state area, separate from its evidence, snapshots,
backups and database. Use the same directory in both objects:

```python
from patchquest.runtime_artifact_state import ArtifactState
from patchquest.runtime_artifacts import RuntimeArtifacts

connector = ArtifactState(store, selected_private_blob_directory)
artifacts = RuntimeArtifacts(selected_private_blob_directory,
    budget_bytes=configured_budget, graph_guard=connector.guard)
```

The guard holds Store's existing `BEGIN IMMEDIATE` transaction throughout the
byte operation, excluding cooperating state/job/coordination writers without
expiring leases or otherwise writing state. It scans current authoritative rows
and retained histories, not a second reference index. Reference tokens bind the
full snapshot plus blob inventory. Unknown/missing tables, unknown columns,
unsupported state versions, unknown metadata namespaces and malformed payloads
fail closed and require an explicitly supported reader. No incomplete graph is
labeled complete.

The supported sources include build artifacts and retained build histories,
legacy runtime reports and contract observations, failures, tester intake/triage,
attachments/history, checkpoint approvals, verification/review/issue state and
other existing reference-bearing rows/history. Hash mentions are conservatively
retained, including historical references. Build-report artifact values are
legacy path references, not typed immutable role identities. The connector never
opens them to synthesize a historical digest, and a filename consisting of 64 hex
characters is not proof of a content identity. Any nonempty legacy artifact map in a
current/historical build or completed job result conservatively protects the whole
known inventory, including after worker leases are released. Validated typed
RunBinding role hashes are handled as immutable references, not path uncertainty.
Independently recorded hashes in existing evidence/bindings remain references;
the connector does not replace them with whatever bytes now occupy a path.
Originals are never opened by the connector. Other opaque legacy references and
unknown build-validation extensions also protect the entire known inventory.

For example, a live build/history path originally naming H1 can later name H2.
The retained H1 blob remains protected even in a newly generated dry run; rechecking
the new plan cannot silently release it. A path-only historical row also stays
protective after a later build report omits that path. Undigested references cannot
prove which retained bytes are unreferenced, so unrelated blobs may be retained
as well. No new database, stored reference index, hash migration or deletion
executor is introduced to recover that missing identity.

External path contents are intentionally not part of this graph's identity. If
only those contents change, a conservative all-retain plan may remain identical;
this never grants deletion. Changed retained blob bytes, inventory or authoritative
state/reference/lease rows still invalidate plans through the existing rechecks.
This is deliberate preservation, not perfect legacy parsing or proof of the
current contents of an external build path. Consumers still resolve/check their
explicit immutable build/evidence references before use.

Any registered build worker, queued/running job, leased task or active agent
session protects the full known artifact universe because existing scopes do not
prove a narrower set of file users. Expired-but-unreconciled rows stay protective
until their owning Jobs/Coordination API reconciles them. Snapshot reads never
expire or steal a lease. These conservative decisions are represented as active
leases; they do not certify that a stale worker is still executing.

`connector.policy()` reads explicit pins/ownership. `set_policy(pins=...,
ownership=..., expected=revision)` uses CAS in existing Store metadata plus its
event history; it stores declarations only, not derived references. Historical
pins are history after explicit unpinning, while protected original/save/checkpoint
ownership cannot be downgraded. The pinned manifest source hash is always classified
original. Unknown ownership remains unknown unless explicitly declared.

`record_run(build_id, observations, expected=build_revision)` validates contract-v1
CaseObservations, build/snapshot identity and immutable observation IDs, then
publishes through existing Store.build CAS into `validation.runtime_cases`.
Distinct case/run evidence stays in build reports/history even when bytes deduplicate.
Consumers should use this seam for the runner's saved observations; no direct
translation, database-file or active-export edits are needed. This API preserves
reported provenance and never attests that a producer executed correctly.

The graph is intentionally bounded and may be expensive for long histories;
contract collection limits fail rather than silently dropping references. Lock
ordering remains artifact writer lock then Store transaction. Do not call this
service while already holding a state writer transaction. Filesystem checks still
require cooperative ownership; SQLite exclusion cannot lock external native file
writers. Before any future authorized deletion, keep both exclusions through the
actual mutation. No deletion executor is provided here.

Synthetic connector tests use the actual public Store/Jobs/Coordination/tester APIs
in temporary invented projects. They verify CAS, failed run history, approvals,
attachment/tester links, conservative workers/leases, writer exclusion and unknown
source rejection. No real project, Studio or emulator is connected by these tests.
