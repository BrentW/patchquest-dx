# Regression planning and coverage consumption

`patchquest.runtime_regression` produces explainable contract-v1 ChangeImpactPlan
records for the existing runner. It runs no emulator, constructs no Store,
changes no translations/checkpoints, computes no alternate coverage percentage
and awards no verification. The [coverage receiver](runtime-catalog-coverage.md)
owns assessment; the [runner](runtime-sweeps.md) owns execution and resume.

## Production coverage consumer

```python
from patchquest.runtime_regression import (
    coverage_identity, dependency_map, plan_from_coverage, ordered_cases,
)
from patchquest.runtime_coverage import catalog_unchanged

# Select ONE exact binding group from an admitted receiver result. Keep its
# historical report and catalog_receipt unchanged. Obtain a fresh read_catalog
# receipt covering baseline AND target builds through the explicit selected owner.
plan = plan_from_coverage(
    cases, target_binding,
    baseline_binding=baseline_binding,
    coverage_report=baseline_report,
    baseline_catalog=baseline_catalog_receipt,
    current_catalog=current_catalog_receipt,
    admit_coverage=independent_review_registry_lookup,
    check_catalog=lambda receipt: catalog_unchanged(selected_context, receipt),
    dependencies=target_dependencies,
    baseline_dependencies=baseline_dependencies,
)
execution_cases = ordered_cases(cases, plan)
# Build the existing explicit case_inventory in this order and pass
# selection_plan=plan to run_sweep with its required pinned inputs and limits.
```

The planner is pure: only the explicit trusted local callbacks may perform I/O.
Never let browser/imported data choose callbacks, paths, contexts or authority.
The caller supplies canonical receiver reports, not gap summaries or passed labels.
Different build/configuration/scenario/expectation groups require separate plans;
no shared binding or aggregate coverage is invented.

`coverage_identity(report, catalog_receipt)` pins the complete normalized
CoverageReport AND its complete read receipt. Configure an independent local
registry for that identity; never implement admission by echoing imported tags.
`admit_coverage(pin)` returns `None` for unreviewed evidence, or a receipt with:

| Field | Required meaning |
| --- | --- |
| coverage_sha256 | Exact coverage_identity pin |
| binding_sha256 | Canonical contract_digest of the reviewed report binding |
| catalog_read_sha256 | Reviewed receiver catalog read receipt identity |
| scope_kind | renderer; gameplay/editorial results cannot substitute |
| method | Exact requested prior_method, normally automated_runtime |
| reviewer, reference, reason | Nonempty bounded independent review provenance |

The catalog shape is the existing read_catalog result: identity, heads, builds,
snapshots and read_sha256. Its canonical digest and bounded positive integer
revision maps are checked. Baseline report revisions must match its retained
build/snapshot. The current receipt must include baseline and target build rows;
changed/missing baseline build metadata needs renewed coverage admission. Target
build/snapshot/record revisions must match the current receipt and target records
must match current heads. Current project/source identity must agree with the
baseline. These structural checks are not authentication by themselves.

`check_catalog(receipt)` normally closes over the canonical receiver freshness
helper and explicitly selected context. It must return exactly True for a fresh
read; missing, false or unavailable freshness forces the full declared scope.
This optimistic check is not a transaction lock. Recheck immediately before
execution and use existing authoritative CAS if later persisting anything.

Unknown/missing/untrusted coverage, stale read receipts, wrong methods/purposes
and current revision drift conservatively select ALL declared cases with explicit
fallback reasons. Malformed receipts or callback types fail closed. Historical
reports/observations remain untouched. Valid admission permits narrowing only
when the independently supplied dependency evidence is also complete/current.
`producer_admitted` is diagnostic registry consistency, never runtime verification
or permission to execute. No planner can authenticate a deliberately false local
registry, incomplete dependency claim or hidden binary change.

## Explicit dependency evidence

`dependency_map(cases, binding, revisions, case_dependencies, complete=False)`
freezes a module-local RegressionDependencies document. It is not a shared runtime
schema or a second catalog. It pins the canonical binding, exact CaseSpec digests,
explicit version strings, dependency membership and completeness. Cases/revisions
are bounded to10000 and aggregate edges to100000. Inputs are detached; dependency
order is normalized. Case IDs retain the canonical opaque identity rules; the
ASCII namespace syntax applies only to dependency IDs. Malformed identities/
versions/duplicate cases are rejected.

Completeness is an explicit trusted build/adapter composition assertion, never
inferred from text equality, labels or a previous pass. Record changes use exact
binding revision maps. Other namespaces are context, layout, font, control,
pointer, renderer, scenario and configuration. Every changed namespace selects
all declared current/baseline consumers. Shared dependencies expand to every known
consumer; unknown references/categories, incomplete or stale graphs and unexplained
changes force the full declared scope. Preserve unknown out-of-scope requirements;
a declared scope is not a whole-game extraction claim.

Adapter/emulator/detector/configuration changes are globally conservative. Scoped
scenario changes need explicit scenario dependency evidence. Artifact-role changes
and unexplained build/binary/snapshot/expectation changes require full scope.
Narrowing explained content changes relies on the explicit complete-graph trust
boundary; it is not proof against unreported patches.

## Historical scheduling and runner composition

`plan_changes` is the lower-level primitive for composition roots that ALREADY
hold an independently admitted CoverageReport. It does not authenticate that
input or check a live catalog. Production consumers should use plan_from_coverage
with the canonical report/read receipts and independent admission/freshness hooks.
No evidence is admitted merely by calling the primitive.

Every declared case receives selected/deferred with a reason. Missing/failed/
interrupted/stale/unknown/unsupported/untested baseline renderer results cause
reselection. Normal gameplay cannot replace rendering evidence. Default method
is automated_runtime; synthetic must be requested explicitly for invented tests.
Even a historical pass for identical text cannot verify a new binary. Deferred
rows explicitly say NOT verified for the target build and do not receive a pass.
No baseline observation, report, purpose or catalog assessment is rewritten.

Changed-record consumers run first, followed by stable input order. The runner's
selection seam uses membership sets; build its inventory from ordered_cases to
apply that priority. All deferred cases remain in the plan/inventory denominator
and are recorded excluded without new captures or verification. An explicit
full_sweep=True always selects the entire declared scope. Plan identities include
normalized graph/report admission/read identities and remain deterministic.

Current runner resume requires its original exact definition/plan and confirmed
stopped workers; changing a plan uses a fresh destination and cannot bypass an
unknown stop. Historical runner observations remain scheduling inputs under their
own exact admitted binding; current resume format rules do not relabel old evidence.

## Separate obligations and benchmark gate

additional_checks always retains normal-gameplay, cold-boot, save-load,
normal-speed-pacing, audio and responsiveness. These are obligations, not pass
results or permission to execute. Unsupported/irrelevant checks need explicit
later disposition. Targeted renderer runs cannot replace them.

Use the existing highest-reliable-speed guidance and runner/adapter mechanisms.
Preserve input durations, capture points, gameplay logic and emulated clocks.
Fall back when control becomes unreliable and restore any changed persistent
settings. No alternate runner, CPU-clock modification or native hook is added.
Normal-speed audio/pacing/responsiveness remain unverified without their own
appropriate evidence.

No measured optimization or native benchmark is supplied by this module. Synthetic
wall time cannot prove acceleration. Existing same-mode repeats can describe that
mode's observed variation but cannot establish an optimization benefit. Unequal
routes, omitted input controls or cold-vs-state workflows cannot be presented as
an equivalent-workload speed multiplier.

Before regression-v1-ready, separately authorize repeated private workloads with
pinned equivalent cases, binaries/core/configuration, inputs and every capture
obligation. Retain startup, host wall time, emulated frames, navigation time, case
counts, input/capture failures, completeness and all scratch/retained/managed/evidence
storage. Unknown measurements stay unknown. Native missed-input truth is not
established by callback delivery alone. A caller-owned measured sidecar may add
navigation timing only after owner review; existing aggregate elapsed data does
not supply it automatically. No native execution or performance promise follows
from a benchmark proposal or this consumer integration.

For worker batching comparisons, count worker processes and cold core instances
separately: batching may amortize process startup while every case still reloads
its pinned inputs. Use the same reset, input and capture obligations in both
arms, plus equally empty per-trial output archives so earlier trials do not give
later ones a capture-deduplication advantage. Preserve every output rather than
clearing evidence to recreate an initial state.

Partition retained and workspace allowances across the whole repeated window;
a per-run ceiling is not automatically a cumulative allowance. Report reused
immutable input bytes separately from newly written working copies, and count
inspection snapshots, sidecars and failed outputs in total storage. Record an
explicit balanced order such as ABBA with equivalent workloads; it does not
remove cache, host-load or cumulative-accounting effects.

Retain raw lifecycle and case/navigation intervals, their observation points and
clock resolution. Overlapping intervals cannot be added as an exclusive phase
breakdown, and a zero quantized interval does not establish zero work. Separate
startup savings from complete-run wall time and show each sample and variation.
A lower mean with few overlapping samples is exploratory, not reliable evidence
of acceleration or a reason to change a default execution policy.

The public invented tests cover conservative selection and the current canonical
receiver/read-receipt consumer boundary. Tests use isolated authored fixtures and
synthetic runner output; they do not constitute a private benchmark or final
runtime/gameplay acceptance.
