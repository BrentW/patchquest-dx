# Safe translation-record upserts

An upsert creates an absent record or updates an existing one under its stable
ID. The headless `state ... upsert` command uses the same revision store as
Studio. It does not open a ROM, translate text, select a provider, insert bytes,
run a build, or approve a checkpoint. No installation or private game is needed
for the synthetic tests.

## Preview and apply

Keep real requests and responses in the selected private project. Start from
[the independently authored, nonsexual example](../templates/project/upsert.example.json).
Set `project_id` to the explicit manifest's ID; mismatches are rejected.

```sh
python tools/patchquest.py state ../private-workspace/example/project.json upsert --input ../private-workspace/example/create.json
```

The default `dry_run: true` validates the complete batch and reports planned
outcomes without writing records, proposals or events. Opening a project for
the first time may initialize its empty state store. To apply the reviewed
request, set `dry_run` to the JSON boolean `false` and run the same command.
A preview does not reserve revisions: intervening edits can invalidate it.

Use `get` to read a record and its current revision before preparing an update:

```json
{
  "project_id": "invented-demo",
  "actor": "example-agent",
  "reason": "Clarify an independently authored fictional sign.",
  "dry_run": true,
  "changes": [
    {
      "expected": 1,
      "data": {
        "id": "harbor.sign.welcome",
        "target": "Welcome to the harbor."
      }
    }
  ]
}
```

The revision above is illustrative, not a value to reuse without reading.
Python callers use `Store(manifest).upsert(project_id, changes, actor=...,
reason=..., dry_run=True)`. The JSON CLI also accepts `--input -` for stdin.

## Contract

- Each batch contains 1–100 changes and at most 2,000,000 UTF-8 bytes of
  serialized change data. Each change has exactly `data` and `expected`.
  IDs must be supplied and unique within the batch. The tool never derives an
  ID from wording, row order, translated text or a filename.
- A create uses `expected: 0` and full record data, including explicit `id`,
  `source` and `target`. The existing record validator checks all metadata.
  A blank target can represent untranslated source; no completion is inferred.
- An update uses the revision read and only `id`, `target`, and optional
  `uncertainty`. Source text, controls, context, decoding status, source
  references and build bindings are retained. For source interpretation changes,
  use the explicit `source_revision: true` mode of fenced `work-publish`, described
  in [coordination](agent-collaboration.md#conflicts-and-recovery). It retains
  targets and raw bindings; it is not a media re-extraction operation.
- The batch is one transaction. A malformed row, stale differing edit, wrong
  project, or coordinated record rejects the whole batch, including proposals
  and events. Previously committed batches remain intact.
- Exact repeats return `unchanged` without creating revisions or events, even
  if the supplied revision is older. This exemption permits **no mutation**:
  differing content at a stale revision still conflicts. A future revision is
  always rejected. A repeated create compares the entire normalized record.
- Human-reviewed corrections remain active. A current-revision alternative is
  saved as an inactive proposal. Repeating the same normalized proposal against
  the same protected revision returns `proposal_exists`, without duplication.
  A newer human revision requires fresh review. This operation always uses the
  agent role; it has no human override or checkpoint-approval option.
- Any record enrolled in coordinated work is rejected, including unchanged
  replays. Continue through the existing fenced `work-publish` workflow.
  Batch upsert cannot bypass a lease or its history.

The response contains `dry_run` and a result per ID: `created`, `updated`,
`unchanged`, `proposed`, or `proposal_exists`. During preview, `revision` is the
current revision (zero for an absent record), not a promised next revision.
After applying, it is the resulting active revision; proposals do not advance
the protected head. These outcomes do not assert linguistic correctness or
insertion, emulator, hardware, or human acceptance.

Conflicts exit 3 and invalid requests exit 2 through the existing CLI. Read the
latest source, target, context and correction history, then reconcile. Do not
blindly increment `expected`, change IDs, impersonate a human, or modify a
database/export to make an error disappear. There is no automatic retry or
provider routing. The browser edit API is unchanged; this operation is for the
explicit CLI/Python interfaces.

## General translation-engineering principles

Stable identity, source fidelity, language quality, layout and runtime behavior
are separate concerns:

1. Assign durable IDs from a project's extraction model and retain original
   bytes, source context and control boundaries privately. Rewording a line
   should not create a different record. Prove lossless decoding/reinsertion
   before changing the source representation.
2. Preserve opaque controls and their operands. A byte resembling an end marker
   may be data inside a control. Generic record validation cannot prove an
   adapter's encoding, pointer reachability, or storage capacity.
3. Translate permitted content with scene and speaker evidence. Use the shared
   [localization policy](../LOCALIZATION.md), [narrative context](narrative-context.md)
   and [exception workflow](translation-exceptions.md). Do not invent context,
   sanitize source meaning, replace content with a refusal, or claim unsupported
   processing succeeded. Preserve corrections and actual provider outcomes.
4. Measure the saved wording with actual font advances and pixel bounds. Adapt
   the layout within verified capabilities; do not damage meaning to force a
   string into an arbitrary byte or character count.
5. Freeze a consistent revision snapshot for a private build. Keep extraction,
   translation, insertion, automated checks and actual runtime observations
   distinct. A successful upsert establishes only a state-store operation.

Tests in `tests/test_upsert.py` use invented signs and temporary ROM-free
projects. They cover replay behavior, validation, atomic rollback, metadata
preservation, stable IDs, human correction/proposal protection, lease boundaries,
concurrent revision conflicts, and the JSON CLI.
