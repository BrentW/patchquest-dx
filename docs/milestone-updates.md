# Reviewed milestone summaries

Milestone summaries are deliberately authored editorial content, separate from
translation records, activity logs and verification evidence. Studio and all
agents use the same revisioned API. Nothing is selected or exported by default;
there is no automatic summarization, publication, release approval or network call.

## Workflow

In Studio, open **Milestone updates**, choose **New summary**, and save a draft.
Describe the bounded outcome and remaining limitations. Choose the actual basis
for the statement: not verified, static checks, automated runtime, human-reported
testing or hardware testing. Put internal references and investigation details
only in **Private notes**.

Open **Edit / review** to inspect the saved content. Check wording, privacy and
evidence before **Mark reviewed**, then explicitly **Select for export**. The
exact export preview shows the selected content. **Export selected summaries**
creates a fresh JSON file under the selected project's output directory in
`milestone-updates/`. It does not start a build or change translations.

Every edit, including notes-only edits, invalidates review and removes that item
from selection. A stale save, review, selection or export is rejected. Studio
retains unsaved drafts on conflicts and warns before switching projects or tabs.
Refresh summaries explicitly to see other editors' changes; polling does not
replace an open editorial draft. Edits to different summaries can proceed
independently. A selection export checks the whole collection revision.

Review is an explicit assertion by a local caller, not an authentication system,
proof of runtime testing, or permission to publish. Provider and reviewer labels
are provenance only. Keep publication and checkpoint approval separate. Evidence
labels describe the summary's stated scope, not overall project completion.

## Shared API

Use `python tools/patchquest.py state <explicit-private-manifest> <operation>`.
Write parameters can be supplied with `--input <json-file>` or `--input -`.
The same operations are discoverable through `agent-context`.

| Operation | Parameters and result |
|---|---|
| `milestones` | Private board: schema version, collection `revision`, items including drafts, review provenance and notes |
| `milestone-put` | `data`, `expected`, optional `key`, `private_notes`, `actor`; creates an opaque ID when key is omitted and expected is zero; otherwise updates the expected item revision |
| `milestone-review` | `key`, `expected`, `content_sha256`, optional `actor`; binds review to the exact saved draft and content digest |
| `milestone-select` | `key`, `expected`, boolean `selected`, optional `actor`; selecting requires a current review; deselection is explicit |
| `milestone-preview` | Exact allowlisted export payload for the current selection |
| `milestone-export` | Collection `expected`, fresh relative `destination` under the output policy, optional `actor`; returns private path, byte SHA-256, selection revision and count |
| `milestone-history` | Optional `after` event sequence (default 0), `limit` (1–500, default 100); private revision and export history |

`expected` is the item revision for item writes and the collection revision for
export. Review requires the `content_sha256` actually inspected. Never fetch a
new revision merely to force a conflicting draft through. Each write returns the
new item revision and `board_revision`. Retain the history for reconciliation.
The metadata/event journal reuses the existing state database without a schema
migration. No translation, memory, snapshot or build record is changed.

The `data` object has exactly these six fields; unknown fields are rejected:

```json
{
  "date": "2026-01-02",
  "title": "Invented menu review",
  "summary": "The invented menus now have consistent spacing.",
  "category": "testing",
  "verification_basis": "static",
  "limitations": "Runtime navigation remains untested."
}
```

The date is `YYYY-MM-DD`. Title and summary are nonblank, with limits of 160 and
2,000 characters; limitations allow 1,000. Categories are `progress`,
`translation`, `review`, `testing`, `tooling`. Verification bases are
`not_verified`, `static`, `automated_runtime`, `reported_human`, `hardware`.
Private notes allow 8,000 characters. Content is plain text: render it as text,
never executable markup. No automatic redaction can make arbitrary authored
text safe; reviewers must check the six exportable fields for private details.

Browser writes have an explicit allowlist and use the selected project, local
session token and a fixed `Studio user` provenance label. The browser cannot
choose output paths or impersonate another reviewer through these endpoints.
CLI callers use the same validations and compare-and-swap behavior.

## Export schema, version 1

The JSON document contains only:

- `schema_version: 1`, `report_type: "milestone-updates"`;
- `selection_revision`, the private board revision captured by this export;
- `publication_approved: false`, `release_approved: false`;
- `items`, each with an opaque `id`, item `revision`, `content_sha256`, and the
  six explicitly reviewed content fields above.

Items are sorted by date descending, then opaque ID descending for stable ties.
The content digest is SHA-256 of UTF-8 JSON with sorted keys, compact separators,
unescaped Unicode and no nonfinite numbers. The export result's separate byte
SHA-256 identifies the actual file. Drafts, unselected reviews, reviewer labels,
private notes, project identities, paths, ROM hashes, source text, raw evidence,
record IDs and internal logs are not copied from state into the payload.

An export is a complete selection snapshot, including an empty `items` list when
nothing is selected. Consumers should use an explicitly chosen snapshot, handle
unsupported schema versions as unknown, and replace their previous selection
rather than merge historical exports. A deselected or edited summary disappears
from future exports; old files remain immutable and are not automatically revoked
or removed from any consumer. Export again and explicitly replace the consumed
snapshot when changing a previously handed-off selection.

Files are completed and flushed before an atomic, exclusive hard-link promotion
under the project's output policy. Existing destinations are never overwritten.
Filesystems without hard-link support fail without producing a partial export.
The collection is locked during capture and file creation, so another write cannot
change the selection mid-export. Filesystem and database commits are not one
transaction: a crash after file creation can leave a complete unjournaled file.
Treat a missing success response as uncertain; inspect it privately and use a
fresh destination for a retry. This is not a hostile-process filesystem sandbox.

## Verification

`tests/test_milestones.py` exercises the shared API, review invalidation, stale
and concurrent writes, private-field exclusion, immutable exports, failed writes,
browser route restrictions and protected translation preservation. The optional
`tools/milestones_browser_check.cjs` uses invented projects and installed browser
tools to check the editorial flow, drafts, conflict recovery and responsive UI.
These checks validate the feature; they do not verify any real milestone claim.
