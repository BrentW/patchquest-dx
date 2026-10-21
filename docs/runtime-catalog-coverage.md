# Runtime catalog coverage

`patchquest.runtime_coverage` reconciles reviewed runtime evidence with an
explicitly selected existing translation catalog. It is a read-only library:
it does not start an emulator, initialize a Store, translate text, create records,
approve checkpoints, or award per-record verification stages.

It consumes the [v1 contracts](runtime-coverage-contract.md),
[runner manifests](runtime-sweeps.md), [detector findings](runtime-detectors.md)
and [immutable artifact resolution](runtime-storage.md). Studio and regression
consumers use these results rather than implementing their own coverage math.
An available module does not imply whole-game runtime acceptance.

## Trust and input boundaries

Call `reconcile(selection, groups, admit_run=reviewed_registry_lookup,
resolve_evidence=artifacts.resolve)`.

`selection` is an explicit `ProjectContext` or an already initialized `Store`.
The receiver opens the existing `.patchquest/state.sqlite3` with SQLite
`mode=ro`, uses one consistent read transaction, and validates the stored
project/source identity against the selected context. It reads retained builds,
their exact canonical snapshot payloads and current record heads. It never calls
`Store()` itself, `snapshot()` or `export_snapshot()`. A missing database is an
error; no catalog or directory is created.

The caller supplies trusted inventory/mapping policy in `groups`. Each group
contains exactly one validated `RunBinding`, so different builds, scenarios,
configuration, adapters, detectors or expectation documents remain separate.
Do not flatten historical runs into a synthetic common binding.

Versioned image expectations may select intermediate captures from an original
observation. Reconciliation re-runs the detectors against the checked bytes and
requires the entire pinned plan. A favorable final image or diagnostic result
cannot replace a failed or missing required page check. Missing or ambiguous
selected captures remain unknown, and native instrumentation checks remain
unsupported when the adapter cannot observe them. Image matches establish only
their declared regions; they do not prove page completion, waits, scrolling,
termination, glyph geometry, gameplay coverage or extraction completeness.
Older runs cannot inherit new selectors or detector versions by rebinding.

Imported manifests, filenames, passed labels and project IDs do not authenticate
execution. `admit_run` receives the SHA-256 of the **original manifest bytes**,
not a normalized reconstruction. It must consult an independently reviewed
local registry; it must never echo a receipt included in the imported bundle.
Return `None` for unreviewed data. Such data remains in the attempt ledger and
cannot pass a coverage row.

A trusted receipt has these fields:

| Field | Meaning |
| --- | --- |
| `binding_sha256`, `capabilities_sha256` | Canonical contract digests of the independently reviewed exact binding and capabilities |
| `build_revision`, `build_payload_sha256` | Existing selected Store build row and canonical payload reviewed for this admission |
| `reviewer`, `reference`, `reason` | Nonempty independent review provenance and bounded scope |
| `artifacts` | Every binding role mapped to its accepted immutable `EvidenceRef` |
| `emulator` | Accepted emulator-binary `EvidenceRef`, matching the binding |
| `purposes` | Case-definition digest to explicit purpose descriptions |

Each purpose is `renderer` or `normal_gameplay`, with its own `reason` and
`reference`. Its claim must match the entire reviewed expectation plan. A
renderer-only case reached by ordinary buttons does not thereby test gameplay.
State/debug access cannot satisfy normal-route coverage even with a mislabeled
receipt. A selected save-slot persistence check must be described as that limited
claim, not general gameplay or all save configurations.

The reviewer owns inspection of actual execution, lifecycle/stop results,
scenario/input provenance and independent calibration. The receipt ties these
facts to the exact original manifest, capabilities, expectation/configuration
binding and retained build row. The receiver checks the binding/definition and
configuration digests, requested cases and observations; it does not pretend that
a valid JSON schema proves a native core ran. It does not consult the current
runner version to invalidate historical results: resume compatibility and
historical evidence assessment are different operations.

Build paths alone are mutable references. The separate reviewed build-row pin
and immutable role references establish the admitted association; available
bytes alone do not. Every role and emulator reference is resolved and its bytes
verified. A changed build revision requires renewed explicit admission.

These are trusted local caller APIs, not an HTTP admission endpoint, a signature
scheme or protection against an actor with arbitrary filesystem/Python access.
Browser-provided data must not select callbacks, paths or producer authority.

## Group envelope

Each group contains:

- `binding`: the complete v1 RunBinding.
- `scope`: `id`, `description`, `extraction_completeness` and `extraction_basis`.
  The receiver derives the full `case_ids` and `case_digests`.
- `cases`: all declared CaseSpecs, including unexecuted, unsupported and deferred
  cases. Every original requested case must remain in this denominator.
- `runs`: bundles with `manifest_bytes`, `expectations` and `findings`.
  `expectations` is the complete pinned manifest or legacy single-case detector
  plan. `None` means capture-only evidence; it cannot create a detector pass.
- `associations`: case ID to `kind: exact`, exact `case_sha256`, **all** composed
  `records` and revisions, and a reviewed `basis`. Partial or ambiguous mappings
  credit no component. An empty-record screen may explicitly use `kind:
  screen_only`, the case digest and basis; otherwise it remains an uncatalogued
  candidate. Do not guess associations from a familiar portrait or text snippet.
- `record_requirements`: record ID to sorted `case_ids`, `complete` and `basis`.
  These must include all declared contexts for the record. Only a reviewed
  complete inventory can support record-level completeness. Omission or
  `complete: false` leaves it unknown even when one context passes.
- Optional `supersessions`: `{old, new, reason}` observation IDs. Both originals
  remain. Different case/binding/method/reach/purpose, duplicate edges and cycles
  are refused. Timestamp ordering alone is not a disposition.
- Optional `declarations`: `{kind, revisions, reason, reference}` for
  `preserved_source` or `graphics_text`. Exact snapshot revisions are required.
  Current drift is labeled; declarations do not remove rows or award passes.

Receiver source payloads are private reports. Do not put real manifests, paths,
snapshots, names, revisions or screenshots in public examples.

## Assessment and denominators

Canonical `check_observation` validates each CaseSpec/observation/capability
relationship, including every contributing record revision. Those revisions must
exist in the selected immutable snapshot. Historical results retain their
original binding; current corrections are never copied backward into evidence.

The receiver validates every check in the complete pinned expectation document,
including unselected case plans. It verifies capture bytes and independently
recomputes the existing deterministic detectors for supplied findings. Missing
imported requirements stay missing; recomputation never manufactures an imported
pass. Changed or disagreeing findings, unavailable bytes and unobserved controls
remain unknown; unsupported capabilities remain unsupported. A passing diagnostic
never replaces a failed required destination. No new detector algorithm is added.

Each report retains renderer/synthetic, renderer/automated-runtime and
normal-gameplay/automated-runtime sections, with every declared case in every
denominator. Missing purpose admission is untested. Conflicting attempts stay
unknown unless explicitly superseded. A valid captured failure is exercised
but failed; an exercised case does not imply its record is fully verified.

Results include:

- `catalog_receipt`: selected identity, immutable snapshot revision maps, current
  heads and exact build-row pins, with `read_sha256`.
- Per-binding `report`: a validated CoverageReport with required runtime links.
- `attempts` and `runs`: original observations/findings, derived decisions,
  admission provenance, superseded history and runner discovery ledgers.
- `historical_catalog` and `current_catalog`: method/purpose-specific summaries
  over the snapshot or current known records. Changed composed components make
  the current projection stale. Records with missing contexts/mappings remain
  unknown; newly added catalog records are not silently omitted.
- Reasoned unexercised, unmapped, uncatalogued, preserved-source and graphics
  candidates. They do not generate source text or mutate the catalog.
- A per-group `gap_contexts` sidecar maps diagnostic gap indexes to exact
  declared case IDs. Identical descriptions for different contexts remain
  distinct; the CoverageReport schema and denominators are unchanged.
- `global_verified_percent: null` and `verification_awards: false`.

Per-section percentages describe only their declared denominator. Unknown
extraction completeness cannot become a whole-game percentage. A supplied
`declared_complete` extraction claim still requires its independent basis;
enumeration or a translation count does not establish that claim.

## Freshness, persistence and limitations

The receiver rechecks its catalog read at completion and refuses drift. Call
`catalog_unchanged(selection, result["catalog_receipt"])` before later use.
This optimistic check is not an atomic write lock: a persistence integration must
recheck in its existing authoritative transaction and apply its existing CAS
contract. This library has no persistence endpoint and cannot approve or publish
anything. Preserve original run artifacts through the existing artifact graph
and retain prior state/report history through existing APIs.

No generic detector can infer Japanese glyph absence, correct translation,
native scrolling, semantic input waits, termination, audio or hardware behavior
from a matching screenshot. Reports retain what the adapter actually observes
and what the reviewed complete plan requires. More instrumentation or separate
normal-speed/gameplay/hardware checks need their own evidence and authorization.

Synthetic tests use authored one-pixel images, invented records, existing Store
fixtures and explicit invented review receipts. Actual-labelled fixture objects
test validators; they are not actual emulator runs.

## Discovery review and issue handoff

`patchquest.runtime_gaps` projects this receiver's candidates into bounded pages,
without its own coverage math. `page(store, result, groups, params)` supports
`kind`, `group_id`, `offset` and `limit` (at most 100). It links existing issue
heads and preserves current versus tested revisions. An unobserved declared
context is explicitly not proof that any text was displayed.

Original runner enumeration gaps retain their manifest hash, run/worker origin
and original details. They do not expand the declared case inventory, fabricate
observations or establish extraction completeness. Private adapters can use the
existing bounded runner for scripted or random navigation; adapters must retain
the input sequence/seed and stopping bounds in their pinned configuration.
This consumer does not start a discovery run.

A trusted group's optional `discovery_modes` maps an original manifest SHA-256
to `{mode, reason, reference}`. Supported modes are `exhaustive_renderer`,
`scripted_navigation`, `random_exploration`, `debug_assisted` and `unknown`.
The default is unknown. Observed debug injection cannot be relabeled as ordinary
navigation or exhaustive rendering. These reviewed route labels are not producer
admission or verification awards; ordinary inputs alone do not prove gameplay
coverage, and enumeration alone does not prove exhaustive text rendering.

`create_issue(store, result, groups, candidate_id=..., catalog_read_sha256=...,
note=..., actor=...)` accepts a freshly reconciled **trusted local** result.
Never pass browser-supplied reports, callbacks or group policy to it. It checks
the read receipt again while the existing Store's `BEGIN IMMEDIATE` transaction
excludes catalog/build writers, then uses the ordinary issue/history operation.
No database, table or alternate catalog is introduced. It preserves exact
historical build/snapshot/revision associations, discovery provenance and the
review receipt; oversized associations are rejected rather than truncated.

Candidate identity includes the exact binding, diagnostic context and evidence.
Repeating creation returns the linked issue unchanged, including human notes or
a resolved disposition. Later triage uses existing `issue-put` CAS and history.
A changed catalog/build requires refreshing before creation; an old candidate
does not bypass freshness because it already has an issue. Creating a lead never
inserts source text, rewrites a translation/correction, approves a checkpoint or
awards verification. No automatic bulk import is performed.

Studio exposes this through its explicitly configured project-bound runtime
provider. Headless callers can use the same Python API with their own trusted
composition. Tests exercise stale writes, concurrent duplicate creation,
rollback, human issue resolutions, protected corrections, context identity and
discovery-method distinctions using invented projects only.
