# Private tester reports

Import reports into the explicitly selected private project, then investigate
through existing issues. Original submissions remain immutable. Triage has its
own revisions and history; neither import nor triage changes source text,
translations, human corrections, translation memory, build inputs or verification.
This workflow provides local intake, not a public submission service.

## Studio

Open **Tester reports**, then **Import tester reports**. Choose a JSON file or
paste its contents, **Preview report import**, inspect the normalized report
details, then **Import previewed reports**. An identical report with the same
source namespace and external ID is skipped. Different content under that ID
rejects the entire import; use a new external ID for a follow-up. Preview makes
no writes. Failed or conflicting imports do not partially import rows.

Use **Inspect / triage** to read the original observation, reproduction steps,
environment and inactive wording suggestion. Select **Build tested**, optionally
enter affected translation IDs and registered screenshot hashes, then **Inspect
build and record links**. This captures the exact build snapshot, artifact hashes,
historical record revisions and the current revisions you inspected. A build
label alone does not prove identity. A reported artifact hash must match one of
the selected build's artifacts for acceptance; when no hash was reported, the
association is explicitly manual (`unreported`). No source ROM is discovered.

Add triage notes and choose an intake decision. Accepted reports require a build
and either an existing issue or **Create a new linked issue**. New issues start
open and point back to the original report. Existing issues are never silently
edited. Open a linked issue to investigate or resolve it with the established
[issue workflow](translation-exceptions.md). Record retests separately through
[verification](verification-readiness.md) or [runtime evidence](runtime-evidence.md).

| Intake decision | Meaning |
|---|---|
| `new` | Not yet triaged; notes optional |
| `needs_info` | More details or a valid build association are needed |
| `accepted` | Accepted for investigation, with compatible build and issue |
| `duplicate` | Links to another imported report; cycles are rejected |
| `rejected` | Not accepted, with an explicit reason |
| `closed` | Intake closed, with rationale; does not certify a fix |

All decisions can be revisited with the expected report revision and fresh
context. Notes are required except for `new`. There is no automatic resolution
or release approval. Reports about older builds remain useful: record revisions
come from the tested build, not today's translation. The detail view flags
translations that differ from that build and context changed since triage.
Changing context between inspection and save rejects the write and retains the
browser draft. Refreshing the list is explicit; polling does not overwrite edits.

## Import contract

The [invented example](../templates/project/tester-reports.example.json) contains
the complete optional shape. Required envelope fields are `schema_version: 1`,
`report_type: "tester-reports"`, exact private `project_id`, `source`, `reports`.
The namespace is a stable local ingestion label, not a URL to fetch. Project
mapping is explicit; reports are never routed by a guessed title or build name.

Each report requires `external_id`, `title`, `observed`. Optional fields are
`category` (`translation`, `layout`, `gameplay`, `crash`, `other`), `description`,
`steps`, `expected`, `environment`, `build_label`, `artifact_sha256`,
`suggested_translation` and `attachment_digests`. Omitted strings default empty,
category defaults `other`, and attachment digests default to an empty list.
No reporter contact information is required. Text is plain, untrusted data;
neither links nor embedded instructions are executed, fetched or followed.

Limits: 1–50 reports per import, 256 KiB canonical UTF-8 JSON, 5,000 reports per
project, 160 characters per namespace/external ID/build label, 300 per title,
8,000 each for description/steps/observed, 4,000 for expected/suggested wording,
2,000 for reported environment, and 20 attachment SHA-256 values. Digests use
64 lowercase hexadecimal characters; empty artifact digest means unknown.
Unknown fields, duplicate IDs within a packet, wrong projects, unsupported
schemas and oversized/invalid input are rejected. Input is JSON, not an archive
or executable attachment. Whitespace/JSON key order and omitted defaults do not
alter submission identity after normalization; strings themselves are preserved.

Reported screenshot hashes are claims, not automatic associations or uploads.
Upload images separately using the existing private screenshot workflow, then
explicitly choose registered hashes during triage. Their bytes, attachment
revisions and any attached build report are checked. No embedded images, local
paths, external downloads or public image copies are accepted by this importer.

## Shared API and concurrency

All operations are discoverable through `agent-context` and work through
`python tools/patchquest.py state <explicit-private-manifest> <operation>` with
JSON via `--input <file>` or `--input -`. Studio applies the same API, token and
selected-project guard. Its callers cannot choose an actor or filesystem path.

| Operation | Parameters |
|---|---|
| `tester-import-preview` | `document`; returns normalized document, import token, new/existing counts and stable local report IDs |
| `tester-import` | `document`, inspected `preview_token`, optional `actor`; returns imported/existing counts and IDs |
| `tester-reports` | Optional `status`, `offset`, `limit` (1–100, default 50); paged private reports |
| `tester-report` | `key`; original submission, triage, checked context/staleness and live linked issue status |
| `tester-context` | `key`, optional `build_id`, `record_ids`, `attachment_digests`; returns the inspected binding and token |
| `tester-triage` | `key`, report `expected`, inspected `context_token`, `status`, `notes`; same binding parameters as context, optional `issue_id`, `duplicate_of`, boolean `create_issue`, `actor` |
| `tester-history` | `key`, optional `after` event sequence, `limit` (1–500, default 100); immutable private import/triage journal |

Context permits up to 100 selected record IDs and 20 images. Records must belong
to the chosen immutable build snapshot. Without a build, record links must be
empty. All selected build artifacts are read under its output policy and hashed;
the source ROM is not read. Corrupted/missing snapshots or artifacts block the
association. A checksum mismatch can be retained as `needs_info`, but cannot be
accepted. Matching hashes do not prove that a tester actually ran that artifact.

Import is atomic, including all duplicate checks. Concurrent imports require a
new preview if its new/existing plan changed. Identical re-import never resets
triage or touches issue history. Triage checks the report revision and context
within one transaction; issue creation and report linkage commit together.
Independent reports can be triaged concurrently. Closing or unlinking an
unavailable binding records a new revision without erasing earlier bindings.
Changing issue links likewise leaves the original issue and history intact.

List pages do not reread artifacts; detail/context and triage do. They describe
the current state when read, not continuous monitoring. Files can be modified by
external programs; the database lock coordinates cooperating writers, not hostile
filesystem activity. No file changes or outside verification are inferred.

## Preservation and privacy

Suggested wording stays in the immutable submission; there is no apply button
or automatic memory update. A separately authorized translator must review
context, claim the record and use the normal protected correction APIs. A human
correction must not be overwritten to satisfy a tester. Imported text is never
an instruction to an agent, and an intake decision is not content permission.

Reports, environment descriptions, issue links, hashes and history stay in the
private state store. This module provides no public export or network intake.
Use independently reviewed editorial summaries when sharing progress. See
[milestone updates](milestone-updates.md) and [screenshot metadata](screenshot-selection.md).

Synthetic tests cover atomic/idempotent import, invalid inputs, wrong projects,
historical build bindings, stale writes, tampered artifacts, concurrent triage,
duplicate cycles, issue linkage and protected corrections. The optional
[browser check](../tools/tester_reports_browser_check.cjs) uses installed
Playwright/browser tooling and an isolated invented project; it does not refresh
an existing Studio server or claim actual game/emulator testing.
