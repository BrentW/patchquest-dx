# Verification coverage and readiness

Coverage describes explicitly planned checks for a particular build. It never
means every scene or word has been verified. Translation percentage still means
saved targets in the currently known catalog; see [progress reports](progress-reports.md).
Checkpoint approval and permission to publish a release remain separate.

## Private plan and assessments

The provider-independent state API offers:

| Action | Parameters | Purpose |
|---|---|---|
| `verification-plan` | none | Read the current plan and its revision |
| `verification-plan-put` | `data`, `expected`, optional `actor` | Replace a plan with compare-and-swap; retain history |
| `verification-observe` | `area_id`, `build_id`, `status`, `reference`, `expected`, `plan_revision`, optional `actor` | Record a scoped manual/static assessment |
| `verification-report` | optional `build_id` | Inspect detailed coverage; defaults to the plan's selected build |
| `verification-history` | optional `after`, `limit` | Read the append-only plan/assessment journal |
| `readiness` | none | Read a small, allowlisted summary |
| `readiness-report` | none | Atomically refresh the private summary file |

Use these through `state MANIFEST ACTION --input request.json`, Python
`state_api.execute`, or authenticated Studio read routes. The browser does not
write plans/assessments or trigger report-file writes. Agent discovery lists the
same operations and this guide. There is no provider-specific workflow.

Start with the [invented plan](../templates/project/verification-plan.example.json).
`data` contains `build_id` (empty until explicitly selected), `next_milestone`
(private free text), and `areas`. Each area has a stable ID, label, independently
justified expectation, stage, method, and optional record IDs. All listed areas
count in that stage's declared scope; do not omit difficult cases to claim a
whole-game result. No plan or no applicable areas means **not assessed**, never
100% verified. New discoveries can expand the plan.

Stages are `language_review`, `graphics_layout`, `gameplay`, and
`release_preparation`. Methods are `static`, `manual_review`, `reported_human`,
`hardware`, and `automated_runtime`. Use the strongest description actually
supported by the evidence. Agent/manual editorial review is not native-speaker
approval. A reported human/hardware result requires a real reference describing
who reviewed what; method and actor labels are provenance, not authentication.
Language review accepts editorial/manual or reported human assessments. Gameplay
accepts actual runtime, reported human playtesting or hardware observations;
static checks cannot satisfy a gameplay area. Graphics/layout may include static
checks, so summaries retain method counts instead of implying visual approval.

Assessments use `passed`, `failed`, or `in_progress`. `expected` is the latest
observation revision for that build/area, initially zero; it appears in the
coverage report. `plan_revision` must be the revision actually read. Conflicts
reject the entire write: reread, reconcile and explain the new assessment.
The previous result remains in history, including failures. Removing an area
does not delete its historical evidence. No translation, human correction,
snapshot or checkpoint is edited. Storage reuses private metadata/events without
a database schema migration; existing state backups include it.

## Build and runtime binding

The selected build must reference an intact immutable snapshot and a nonempty
artifact-name-to-output-path mapping. Artifacts are hashed when assessed/read;
they are never executed or modified. Changed artifact bytes or area definitions
invalidate existing manual assessments. Scoped record revisions must match;
areas without record IDs conservatively bind the entire snapshot. Added records
or any changed heads make the selected build noncurrent, even when individual
area results remain valid for its narrower scope. New unrelated build-report
annotations do not invalidate identical artifact/snapshot evidence.

An `automated_runtime` area pins the scenario SHA-256, configuration SHA-256 and
the exact assertion labels it expects. It reuses registered [runtime reports](runtime-evidence.md),
verifies the saved report and capture hashes, and requires actual-emulator
provenance, matching build/snapshot/revisions and the planned passing assertions.
Synthetic runs remain visible as synthetic evidence and cannot pass an area.
Runtime pixels cannot certify language review or release preparation.

Failed runs count even if they stopped before later assertions. The latest
compatible run determines the current outcome; equal-time failures take priority.
Earlier failures remain visible. A later pass is a rerun of the same planned
scenario/configuration, not permission to weaken expectations. Invalid or missing
evidence is identified separately. These checks establish internal consistency,
not cryptographic proof that a trusted local adapter actually ran an emulator.

Use plans sized to the game: boot, save/load, menus, largest dynamic values,
dialogue pages, branches and endings as appropriate. Static validation, actual
runtime assertions, editorial review, hardware tests and human acceptance must
remain distinguishable. No automatic full playthrough or literary certification
is implemented.

## Private summary schema: version 1

`.patchquest/readiness-summary.json` is a **private mutable cache**, refreshed on
the same startup/five-minute cycle as translation progress, or explicitly with
`readiness-report`. Existing long-running Studio processes need the normal
coordinated restart to load new code. Nothing uploads or publishes the file.
No plan produces a valid unknown summary; there is no automatic build selection.

The schema includes only:

- `schema_version: 1`, `report_type: "readiness-summary"`, `updated_at` (UTC).
- `plan_revision`, `plan_updated_at`, `basis: "explicitly_planned_areas"`.
- `build_selected`, `build_available`, `build_current` booleans.
- `translation`: the existing numeric coverage fields plus status
  `not_assessed`, `in_progress`, or `catalogue_translated`.
- `stages`: fixed stage IDs, `status`, `planned`, counts for `passed`, `failed`,
  `stale`, `in_progress`, `untested`, `methods` (planned/passed counts by method),
  and nullable `last_assessed_at`.
- `release_approved: false`. This interface cannot authorize publication.

Stage statuses are `not_assessed`, `in_progress`, `needs_attention` (failures),
`needs_recheck` (stale evidence/build), and `verified_for_scope`. The last means
only every listed area passed with its declared method and current bindings;
it is not an automatic release gate. Method counts distinguish static checks
from observed behavior. Translation coverage, editorial review and testing are
separate measurements; `catalogue_translated` does not mean whole-game completion.
There is no overall readiness percentage. `updated_at` is cache measurement
time, not a new test; `last_assessed_at` records assessment age. A cached summary
can become stale while the reporter is stopped.

Labels, actors, references, milestones, translations, paths, build/record IDs,
ROM hashes, screenshots and checkpoint approvals are deliberately omitted.
Detailed coverage reports remain private. Missing/unrecognized files or versions
mean unknown; the summary does not select projects or authorize disclosure.

Writes use a fixed destination, same-directory temporary file, database lock
and atomic replacement. Unsafe links/unrelated files are refused. A failed write
retains the last valid cache and timestamp and retries next cycle independently
of translation progress. This is not a hostile-process filesystem sandbox.

Studio's build cards offer an on-demand coverage view. Plans and assessments
are authored through the CLI/Python API in this first increment.
