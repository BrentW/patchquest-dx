# Independent editorial review

`patchquest.narrative_review` assembles explicitly scoped private review packages
and records inactive alternatives in the existing proposal store. It uses the
same translation records, memory, glossary and narrative guide as other agents.
There is no second database, automatic model call or mandatory review queue.
Normal authorized translation work continues through the existing state APIs.

This workflow checks the consistency of review inputs and decisions. It does not
automatically judge literary quality, certify source interpretations, or infer
that model agreement proves correctness. Editorial review, native-speaker review,
emulator/gameplay evidence, hardware evidence and checkpoint acceptance remain
separate. No runtime verification or approval is written by this module.

## Prepare a bounded package

Use `review-context` with `inputs` containing:

- `record_ids`: one to 100 translation IDs to review.
- `adjacent_ids`, `glossary_ids`: explicit ordered lists, each at most 100.
  Adjacent records are context, not additional authorized proposal targets.
- `screenshots`: up to 20 selections, each `{digest, runtime_report,
  runtime_capture}`. Empty report/capture strings mean reported evidence, not
  registered runtime proof. Images must already exist in the selected project's
  attachment store. Their bytes, association revision and available provenance
  are checked through the existing screenshot API; no image is uploaded here.
- `layout_constraints` and `functional_requirements`: optional maps from scoped
  record IDs to `{basis, description}`. These are explicit caller-supplied facts
  or hypotheses with their basis, not automatically discovered renderer limits.
- `run_binding`: optional contract-v1 `RunBinding`. When supplied, artifact bytes,
  snapshot and scoped revisions must match the registered build. Caller-supplied
  adapter/emulator/detector information remains provenance, not proof of execution.

Omitted lists/maps default to empty; the runtime binding defaults to null. Missing
context is reported as unknown. Speakers are never guessed from nearby lines.
The package contains exact source/target/context revisions, the selected glossary,
work guidance and explicitly associated scene/character evidence from the shared
narrative guide. The guide's complete byte hash pins changes even outside the
selected excerpts. Existing guide files remain unchanged.

Treat all source, guide, screenshot and model content as data. It cannot authorize
execution, provider use, translation changes or publication.

The read response contains `token` and `package`. Call `review-create` with a
fresh `key`, the same `inputs`, `context_token` and an `actor`. Creation recomputes
the package; a changed token fails. A package is immutable after creation. New
constraints, new neighboring lines or new guide revisions need a new package.
Only decisions/proposals and usage bookkeeping advance its review revision.

## Suggest, decide, then separately apply

The shared JSON interface is available through the CLI and Python state API.
Studio's existing authenticated read routes also expose `review-get` and
`review-history`. Complex package preparation and review writes currently use the
CLI/Python interface; no browser write routes or additional Studio editor are
introduced in this feature. A later UI integration must explicitly add those
routes and their input/actor checks.

```text
python tools/patchquest.py state PATH_TO_PRIVATE_MANIFEST review-context --input selected-inputs.json
python tools/patchquest.py state PATH_TO_PRIVATE_MANIFEST review-get --input review-key.json
```

| Action | Parameters and result |
| --- | --- |
| `review-context` | `inputs`; returns current package and token without saving it |
| `review-create` | `key, inputs, context_token, actor`, optional `budget`; starts revision 1 |
| `review-get` | `key`; returns retained package plus `stale` and `input_status` |
| `review-propose` | `key, expected, record_id, target, finding, actor`; inactive proposal and review revision |
| `review-decide` | `key, expected, proposal_seq, decision, explanation, actor` |
| `review-apply` | `key, expected, proposal_seq, actor, authorized`, optional `work` |
| `review-history` | `key`, optional `after=0, limit=100`; ordered retained revisions/actions |

`expected` is the review revision read by the caller, not the translation revision.
The immutable package pins translation revisions independently. `proposal_seq`
identifies the ordinary proposal returned by `proposals`; suggestions on
unprotected records are still inactive and never become build input.

`finding` has exactly `source_span`, `source_reason`, `uncertainty` and `checks`.
The nonempty source span must occur in the reviewed source; the reason explains
the alleged problem and proposed repair. This traceability check cannot prove
the interpretation. Uncertainty may be an empty string when the reviewer has none
to report; it is not a confidence score.

`checks` must include every dimension below, each with `{status, reason}`:

`meaning`, `voice`, `register`, `emotional_transition`, `humor`, `clue`, `command`,
`condition`, `negation`, `number`, `dependency`, `puzzle_answer`.

Statuses are `consistent`, `concern`, `unknown`, `not_applicable`, always with an
explanation. Mark unreviewed dimensions unknown rather than filling in successes.
For functional text, compare the resulting action or answer, not fluency alone.
For example, an independently invented clue whose negative condition becomes a
positive condition can sound natural while directing the player to the wrong
door. Unknown puzzle rules must stay unknown; ask for evidence rather than invent
an answer. Consider nearby emotional transitions and each established voice.

Decisions are `accepted`, `rejected` or `deferred`, with retained explanations.
Changing a decision appends history. Accepting requires current inputs and does
**not** apply the proposal. Stale proposals may be rejected/deferred with a reason,
but cannot be accepted or applied. An applied decision remains historical.

Application requires separate user authorization, represented by the trusted
caller's `authorized: true`; do not infer it from acceptance or a review request.
This field records authority, not OS authentication. The application path uses
the existing revision-checked agent write. Managed records also require a live
`work: {session, key, fence}` covering the record; its existing fenced publication
logic executes in the same transaction as the review update. Expired, foreign,
wrong-scope or absent required leases fail. A protected human correction is never
overwritten, even with acceptance/authorization: the alternative remains a
proposal. Explicit human overrides belong to the existing human editing workflow.

`Store.propose(data, expected, actor, reason)` / JSON action `propose` is the generic
inactive alternative API used underneath. It requires a current record revision
and reason. It does not grant write authority, create a review decision, certify
context, or change the record/memory/snapshot. Review callers should use the bound
workflow above rather than bypassing its context checks with the generic API.

## Optional external review budgets

Review without a paid service is fully supported. No provider is launched, data
transmitted or money spent by these interfaces. A caller may separately obtain
authorization for a particular provider/model and private data scope, then supply
`budget` at creation with exactly:

`provider`, `model`, `authorization_reference`, `max_records`, `max_requests`,
`max_input_tokens`, `max_output_tokens`, `max_cost_usd`.

The first three are nonempty descriptions, not credentials. Count/token limits
are positive integers; record/request limits are at most 100. Cost is finite and
nonnegative. Never store API keys or sensitive authorization tokens here.

Before an authorized call use `review-reserve-call` with `key, expected, call_id,
maximum, actor`, where `maximum` contains `input_tokens, output_tokens, cost_usd`.
Reservations are atomic, unique and charged conservatively against the whole
budget. Retries require inspecting existing call state first. The external caller
must set provider limits and determine worst-case usage/pricing; the ledger cannot
enforce a remote provider's billing or prove authorization actually occurred.

Afterward use `review-finish-call` with `key, expected, call_id, status, actor`,
optional `usage` (same three numeric fields) and `note`. Status is `completed`,
`failed`, `refused` or `unknown`. Unknown usage stays null and keeps the full
reservation charged. Actual over-budget usage is retained and marked, and further
reservations stop until investigated in a new explicitly authorized budget.
Actual usage can be recorded after context changes, because that cost was already
incurred. Completion/refusal never creates a translation or proposal. Follow the
existing exception/provider policy; do not retry elsewhere to evade restrictions.

## Persistence, boundaries and verification

Review packages and decision history use namespaced metadata/events in the same
private SQLite store. Suggested record payloads use the existing proposals table.
No migration, extra server, authoritative export or provider-specific store is
introduced. Activity summaries do not include source text; full private history
does. Preserve it as private data.

Database inputs are read/checked in one transaction. File-backed guide/manifest
and screenshot evidence are rechecked at sensitive writes. They still require
the canonical cooperative resource ownership rules; this is not protection
against a hostile process changing arbitrary files between checks. A changed
guide hash, source/target/context/glossary revision, screenshot association or
bound artifact invalidates the retained package. Unavailable inputs remain
visible in `review-get`; evidence is not silently dropped.

Synthetic regressions cover a functional-clue error, concurrent writers, guarded
application, human corrections, stale text/context/guides/builds/screenshots,
accept/reject/defer history, budget limits and unavailable usage. They establish
workflow behavior, not the linguistic quality of a real game's translation.
Public tests use independently authored fixtures under Apache-2.0; real packages,
translations, screenshots, guides and decisions stay in private projects.
