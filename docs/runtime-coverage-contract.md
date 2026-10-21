# Runtime coverage connector contract v1

`patchquest.runtime_contracts` defines shared, JSON-serializable records for scene
launchers, bounded renderer sweeps, artifact storage, detectors, reconciliation,
review and regression selection. It performs no I/O, database writes, emulator
execution or project discovery. Use the existing state, runtime and verification
interfaces for persistence and execution; this is not a second evidence store.

The contract establishes internal consistency, **not proof that an emulator ran**.
Actual files, captures and independently justified expectations still need their
existing verification. A trusted local adapter can misreport its provenance.
Synthetic conformance data never certifies gameplay, language, hardware or a
checkpoint. None of these records grants release approval.

## Entry points

```python
from patchquest.runtime_contracts import (
    validate, contract_digest, require_capabilities, binding_changes,
    check_observation, check_finding, observation_status,
    check_coverage_runtime_links, verify_evidence_bytes,
)

case = validate("CaseSpec", {
    "schema_version": 1,
    "kind": "CaseSpec",
    "case_id": "invented-opening-page-0",
    "coverage_scope": "invented-opening-scope",
    "required_capabilities": ["capture_frames"],
})
# Unknown message/page/window/context/variant remain None, not fabricated facts.
```

`validate(kind, data)` returns a detached normalized dictionary. It never mutates
the caller. Missing required fields, incorrect types, duplicate identities,
unknown kinds/versions/fields and non-finite or non-JSON values raise
`ContractError` (a `ValueError`). Integers do not accept booleans. Required unknown
or missing capabilities raise `UnsupportedCapability`, a `ContractError` subtype.
Records must remain within bounded arrays/maps and JSON nesting limits.

All records require `schema_version: 1` and their exact `kind` from the table below.
`extensions` defaults to `{}`. Namespaced keys such as `example:note` allow
non-semantic annotations only. An extension cannot enable a capability, change a
binding, suppress a fault or override a standard field. Unknown standard fields
fail closed. V1 field meanings are frozen: new semantic fields/capabilities or
changed meanings require a coordinated schema version; optional defaults must
be documented and tested. Do not silently upgrade records on read.

## Shared records

These are dictionary contracts, not new Python class hierarchies. IDs are opaque,
bounded nonempty strings. SHA-256 values are lowercase 64-character strings;
revision numbers start at 1. Version strings must be explicitly known. Missing
binding information cannot be replaced with guessed hashes or placeholder
versions to produce a valid runtime result. Retain unbound raw evidence privately
until its identity can be established.

| Kind | Owner / producer | Consumer |
| --- | --- | --- |
| `AdapterCapabilities` | Explicit private adapter | Scene launcher and runner |
| `CaseSpec` | Explicit case inventory | Runner, reconciliation, selection |
| `RunBinding` | Build/evidence interfaces | All runtime consumers; editorial reviews reuse revision semantics |
| `SceneHandle` | Scene launcher | Runner |
| `EvidenceRef` | Artifact service and runner | Detectors, reconciliation, visual review |
| `CaseObservation` | Runner | Detectors and reconciliation |
| `DetectorFinding` | Detector | Reconciliation and visual review |
| `CoverageReport` | Reconciliation | Studio review and regression planner |
| `ChangeImpactPlan` | Regression planner | Runner |

### AdapterCapabilities

Required: `adapter: {id, version}`, `provenance` (`actual_emulator` or `synthetic`),
and `capabilities`, an explicit boolean map. Missing known capabilities default
to false. The known keys are:

`enumerate_messages`, `capture_frames`, `observe_glyphs`, `observe_resources`,
`input`, `page_advance`, `native_scroll`, `restore_state`, `game_save`, `debug_access`.

Frame capture or input support does not imply glyph inspection, scrolling or
debug access. Empty observed glyph/resource collections mean the instrumentation
was available and observed no entries; `null` means it was not observed. Unknown
required capabilities fail rather than falling back silently.

### CaseSpec

Required: `case_id`, `coverage_scope`, `required_capabilities` (unique known names).
Defaults: `record_ids: []`, `message_id: null`, `page: null`, `window_id: null`,
`context_id: null`, `variant_id: null`. Known pages are zero-based integers.

Assign stable case IDs independently of build identity or translated wording.
Each caller/window/context/dynamic-value variant needs its own case when behavior
differs. Unknown associations stay unknown. `record_ids` reference existing
catalog records, not copied source/target text. Uncatalogued observations can
have no associated records.

`contract_digest("CaseSpec", case)` hashes normalized, sorted-key UTF-8 JSON,
including defaults and annotations. It binds the exact definition separately
from stable identity. Array order remains significant. A changed definition
cannot inherit another context's pass merely because its ID was retained.

### RunBinding

Required fields:

- `build_id` and `artifacts`: a nonempty role-to-SHA-256 map, e.g. `rom` or an
  explicitly selected disk role. This contains no executable paths.
- `snapshot`: the existing immutable translation snapshot digest, and `records`:
  the scoped map of catalog IDs to exact revisions. An empty map is screen-level
  evidence, not proof for every translation.
- `scenario_sha256`, `configuration_sha256`, `expectation_sha256`.
- `adapter: {id, version}` and `emulator: {id, version, sha256}`.
- `detectors`: detector ID-to-version map; empty only when none is used.

`binding_changes(previous, current)` returns changed top-level binding fields.
Every field, including annotations conservatively, participates in comparison.
Unchanged wording alone does not make a new binary runtime-verified.

`binding_from_runtime_report(report, *, adapter, emulator_id, emulator_version,
expectation_sha256, detectors)` adapts the existing schema-1 runtime identity
fields (`rom_sha256` becomes `artifacts.rom`). Missing new facts must be supplied
explicitly and justified by the caller. This creates only a binding, never an
observation, new assertion or promoted provenance. Existing runtime report,
scenario and verification schemas are unchanged.

### SceneHandle

Required: `scene_id`, `binding`, `reach_method`, nonempty `arrival_assertions`
(assertion IDs), and `status` (`ready`, `incompatible`, `unsupported`, `failed`,
`unknown`). Defaults: `checkpoint: null`, `reason: ""`; non-ready status requires
a reason. `checkpoint`, when present, is an `EvidenceRef`.

Reach methods are `cold_boot_navigation`, `in_game_save`, `emulator_state` and
`debug_injection`. State/save methods require a checkpoint reference; cold boot
cannot restore one. The scene implementation must check actual checkpoint bytes,
compatibility and arrival assertions. A schema-valid `ready` declaration does not
establish any of those facts. Save-state replay does not verify cold boot or
SRAM persistence. Exact build/emulator/configuration matching remains mandatory
unless a separately verified compatibility strategy explicitly permits reuse.

### EvidenceRef

Required: `evidence_id`, `sha256`, `media_type`, `byte_length`, and
`provenance: {producer, method, run_id, case_id}`. Run/case IDs can be `null` for
evidence not associated with a runtime case. `method` uses the existing
verification labels plus `synthetic`: `static`, `manual_review`, `reported_human`,
`hardware`, `automated_runtime`, `synthetic`.

Defaults: `integrity: "unverified"`, `retention: "referenced"`. Integrity may be
`verified`, `unverified`, `missing`, `mismatch`; retention may be `referenced`,
`pinned`, `disposable`. These are declarations, not permission to delete files.
The artifact owner resolves the digest within the selected private project and
checks references/leases/pins. No file path, URL or command is accepted here.

`verify_evidence_bytes(reference, data)` verifies supplied bytes against digest
and length without reading files or changing the record. Deduplicate bytes by
digest while retaining distinct `evidence_id`/case/run associations. Never discard
provenance just because two captures are byte-identical.

### CaseObservation

Required: `observation_id`, `run_id`, `case_id`, `case_sha256`, `binding`,
`provenance`, `method`, `reach_method`, `execution`, `assertion`, `validity`,
`frames` (count from this run) and `captures` (array of `{frame, evidence}`).
Capture frames are 1-based and cannot exceed `frames`. Evidence provenance must
match the observation's run/case/method. Capture IDs cannot repeat within a case.

| Axis | Values |
| --- | --- |
| Execution | `not_run`, `running`, `completed`, `failed`, `interrupted`, `unsupported`, `excluded` |
| Assertion | `passed`, `failed`, `not_assessed`, `unknown`, `unsupported` |
| Evidence validity | `current`, `stale`, `missing`, `invalid`, `unknown` |

Defaults: `reason: ""`, `glyphs: null`, `resources: null`, `controls: {}`.
Failure, interruption, exclusion, unsupported/uncertain assertions and noncurrent
evidence require reasons. A completed execution may have failed or unassessed
assertions. A passing assertion requires completed execution and captured frames;
a current pass also requires verified capture integrity. A historical pass may
remain passed on the assertion axis while explicitly stale on validity.

Optional glyph entries contain `glyph_id`, `frame`, `x`, `y`, `width`, `height`;
negative origins can describe overflow. `resources` is an explicit metric-to-count
map. `controls` can contain boolean-or-null `page_complete`, `line_advanced`,
`scrolled`, `input_wait`, `terminated`. Omission/null is unknown, not false or
success. A control observation does not certify every transition.

`check_observation(case, observation, capabilities, *, expected_binding=None)`
checks case digest/identity, scoped revisions, adapter/provenance, claimed
instrumentation and required capabilities. Synthetic adapters cannot declare
`automated_runtime`. Changed expected bindings require explicit stale validity;
the function does not rewrite old evidence or the current translations.

### DetectorFinding

Required: `finding_id`, `observation_id`, `case_id`, `case_sha256`, `binding`,
`detector_id`, `detector_version`, `expectation_id`, `status`, `evidence_ids`.
Statuses: `passed`, `failed`, `unknown`, `unsupported`. Defaults: `reason: ""`,
`region: null`, `control: null`. A region is `[x, y, width, height]`; control is an
opaque control/expectation label. Non-passing results require a reason; definite
pass/failure requires evidence references. Detector version must match its binding.

`check_finding(finding, observation)` checks observation/case/binding and capture
references. A detector cannot pass an incomplete execution. It does not execute
the detector or certify an expectation's independent justification.

### CoverageReport

Required: `report_id`, `binding`, `scope`, `sections`, `gap_candidates`.

`scope` contains `id`, `description`, `case_ids`, `case_digests` (one digest for
every case), `extraction_completeness` (`unknown`, `partial`, `declared_complete`)
and `extraction_basis` (reason required for non-unknown declarations). A catalog
or declared scope is not automatically the complete game.

Each section has `scope_kind` (`renderer`, `normal_gameplay`, `editorial`,
`hardware`), `method`, `rows`, `denominator`, `counts`, `passed_percent`.
Each row has `case_id`, `status`, `reason`, `observation_ids`, `finding_ids`.
All scoped cases must appear exactly once per section, including untested and
excluded cases. Use separate reports for different declared scopes.

Statuses/count keys: `passed`, `failed`, `untested`, `in_progress`, `interrupted`,
`stale`, `excluded`, `unsupported`, `unknown`. Counts must match rows. Denominator
includes every case, including exclusions. Percentage is `round(100 * passed /
denominator, 2)` or `null` for empty scope; an empty plan is never 100%. No overall
readiness percentage is allowed. Editorial/hardware/gameplay methods remain
restricted to the corresponding existing verification semantics.

Gap entries contain `kind` (`uncatalogued`, `unexercised`, `unmapped`,
`preserved_source`, `graphics_text`), `observation_ids`, `record_ids`, `reason`.
They are candidates for investigation, not automatic catalog edits.

`observation_status(observation, expected_binding)` classifies a single supplied
observation: changed binding/explicit stale validity becomes stale; other invalid
or unknown validity becomes unknown; execution and assertion outcomes remain
distinct. It does not choose the latest run or aggregate coverage.

`check_coverage_runtime_links(report, observations, findings=(), expectations=None)` checks the
runtime/synthetic sections' supplied references. It rejects synthetic promotion,
different contexts/case definitions, stale passing evidence and missing or
non-passing referenced findings. Debug injection and emulator-state shortcuts
cannot count as normal-route coverage; use renderer scope for those checks.
Independent gameplay evidence may be recorded separately through its existing
method. Other methods' assessment verification, latest-run selection, conflict
policy, actual artifact integrity and reconciliation remain the consumers'
responsibility. Validation of a report alone is structural, not proof of its claims.

### Complete expectation plans and separate assessments

Capturing a completed case does not imply its checks passed. The sweep retains
`assertion: "not_assessed"`; detectors publish separate immutable findings.
For that workflow, pass the **complete pinned expectation document** through the
keyword-only `expectations` argument. Omitting it retains the earlier connector
behavior and cannot upgrade an unassessed capture.

For multiple cases, use the additive container below. It does not change the
existing connector records or permit rewriting their bindings:

```json
{
  "schema_version": 1,
  "kind": "RuntimeExpectationManifest",
  "finding_id_algorithm": "patchquest-detector-v1",
  "cases": {
    "<exact CaseSpec SHA-256>": "<complete single-case expectation object>"
  }
}
```

This is a shape illustration, not a valid fixture. Each case value is the full
schema-1 or schema-2 object documented in [runtime detectors](runtime-detectors.md), including
`expectation_id`, matching `case_sha256`, independent `basis`, every required
`check` and any `exceptions`. There are 1–10,000 distinct case digests and each
plan has 1–1,000 uniquely named checks. The entire container is hashed as sorted
key, compact, non-ASCII-escaped UTF-8 JSON with non-finite numbers rejected. Pin
that hash in `RunBinding.expectation_sha256` before capture. Changing another
case in the same manifest also changes this pin. Single-case schema-1 and schema-2 documents
remain supported explicitly; they imply the same finding identity algorithm.

`expectation_manifest_data(value)` validates the common envelope, algorithm,
case keys and check identities and returns a detached dictionary without adding
defaults. Detector-specific parameter validation remains with the detector.
Unknown manifest/algorithm versions, missing cases, mismatched keys and duplicate
check identities fail closed. Builders must reject duplicate case entries before
constructing a dictionary; file readers must reject duplicate JSON object keys.

For `patchquest-detector-v1`, a required semantic finding ID is `detector-` plus
the SHA-256 of the canonical JSON array `[observation_id, check_id, pinned_hash]`.
`required_finding_plan(observation, expectations)` derives **all** IDs from the
hash-checked document, with the exact detector/version and expectation identity.
Consumers must not accept a separately supplied subset as a complete plan.
Diagnostic extensions are annotations and cannot substitute for these identities.

`assess_observation_findings(observation, expected_binding, findings,
expectations=...)` returns an assessment and explicit required, missing, failed,
unknown and unsupported finding-ID lists. A current completed unassessed capture
can pass only when every required finding is present exactly once and passes.
A confirmed required failure can fail the assessment while retaining other
missing or unavailable checks. Stale bindings, invalid evidence, native failure,
incomplete execution and explicit capture uncertainty retain their meaning.
Definite findings require verified final-frame evidence references by default. Actual bytes
still require independent resolution/rechecking by the consumer; metadata alone
cannot prove they remain available or correct.
An actual-emulator observation cannot accept a definite pass/fail finding backed
by a `synthetic_control` expectation basis. Such declarations are contradictory
and rejected; truthful unknown findings remain unknown. An independent-inspection
basis is required for actual evidence, and its truth still needs external review.

Schema-2 `image_region` checks require `capture: {"frame": N}` and image detector
version `"2"` in the run binding. The frame is an integer from zero through
2^63−1. It selects exactly one PNG capture at that frame in the **original**
observation. A selector beyond the observed run, a missing capture, or multiple
captures at that frame is unavailable; the detector returns unknown rather
than using another image. Definite findings reference only that selected
capture's evidence ID. `expectation_capture_frame(check, schema_version, frames)`
validates the selector and returns its frame, or `None` when beyond the run.
Passing `frames=None` validates syntax before execution. All other checks retain
the final-frame evidence requirement and cannot use a capture selector.

Schema-1 image checks retain their final-frame semantics and detector version
`"1"`. Their JSON/digests do not acquire defaults. The manifest envelope and
finding ID algorithm remain version 1; changing a plan's version or selected
frame changes the complete expectation digest. A single run pins one version
per detector, so incompatible image versions require separate bindings/runs.
Never rebind an earlier observation to a new plan or truncate its frame history
to manufacture compatibility. Both plan versions preserve full-case completion
rules: a required page failure remains failed even if a diagnostic check passes.

Coverage rows must reference the complete passing finding set, not just the
favorable results. Provenance, exact case definitions and normal-gameplay reach
restrictions apply unchanged. These helpers never mutate observations, run a
detector, select a latest attempt, certify extraction completeness or award
emulator/human acceptance. Keep any unresolved checks visible even on failed rows.

### ChangeImpactPlan

Required: `plan_id`, target `binding`, `baseline_binding` (or null), `case_ids`,
`dependency_revisions` (explicit version map or null), `selected`, `deferred`,
`full_sweep_required` (boolean), `additional_checks` (unique check IDs).
Selected/deferred entries contain `case_id` and a nonempty `reason`. They must
partition the declared cases exactly. Unknown baseline or absent/empty dependency
information requires a full sweep; a full sweep cannot defer cases.

The regression owner computes impact and benchmarks. The runner consumes this
plan; it never awards verification to deferred cases. Normal gameplay, cold boot,
save/load and normal-speed timing/audio checks remain separate requirements.

## Ownership, privacy and conformance

Keep the canonical definitions in this module/document and invented fixture set.
Feature modules consume them; shared API/CLI/Studio changes require coordinated
ownership and relevant integration checks. Do not add runtime launchers, detector
algorithms or another proposal/state database to the contract module.

Real values, manifests, hashes, scenarios, glyph mappings, translations, saves,
captures and evidence belong only in the selected private project. Runtime
payloads are not public exports or safe to paste in issue comments merely because
their schemas are public. The validators are not privacy scrubbers or a sandbox.
Protected corrections remain governed by state/CAS/proposal APIs; these pure
contracts neither write translations nor confer authority to do so.

See `tests/fixtures/runtime_coverage/README.md` for independent fixture provenance
and `tests/test_runtime_contracts.py` for positive/negative conformance tests.
Run from the repository root with Python 3.10+:

```text
python -B -m unittest discover -s tests -p test_runtime_contracts.py -v
```

Actual renderer sweeps, detector calibration and normal gameplay validation are
downstream work. Passing these tests establishes only the shared contract.
