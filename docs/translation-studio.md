# Local Translation Studio

Within **Test & review → Runtime review**, the optional **Text coverage &
discovery** panel separates catalog gaps, uncaptured known text, unclear
mappings, preserved source text, graphics text and new discoveries. An explicitly
configured runtime provider supplies these investigation leads. Create an issue
to retain the exact build/revision evidence in the existing Issues workflow;
this never changes translations or awards verification. Duplicate creation
preserves the original issue, including human notes and resolution. See
[runtime review](runtime-review.md#text-coverage-and-discovery).

Studio opens on a **Dashboard** with catalog progress, the latest activity and
shortcuts into the workspace. Four main areas keep navigation compact:
Dashboard (overview and agents), Translate (translations and glossary),
Test & review (builds, runtime evidence, issues and tester reports), and
Prepare exports (milestones, screenshots and release preparation). Only the
current area's pages are shown; links between workflows select the right area.
Leaving an unsaved draft still requires confirmation. Navigation is blocked
while a save is in progress.

Common translation and runtime filters are clickable choices. Less-used fields
remain available under **More filters** or **Exception & content filters**.
Active filters stay visible as removable labels even when those panels are
closed. Filter controls use the existing API criteria and do not change saved
records. Text and report cards adapt to narrow screens; technical evidence
remains available in expandable details.

**Milestone updates** provides [reviewed editorial summaries](milestone-updates.md).
Draft, review and explicitly select summaries, inspect the exact export preview,
then save an immutable private JSON snapshot. Notes and internal logs stay out of
the export. Editing invalidates review and selection; conflicts retain the draft.
This separate editorial workflow does not approve translations, builds or releases.

**Screenshot selection** adds [reviewed capture metadata](screenshot-selection.md):
captions, accessible descriptions, spoiler flags, explicit build labels and
reported or registered capture provenance. Changed source associations require
a fresh review. Exports contain selected metadata only, with no image copies or
publication approval; existing screenshots and translations remain private.

**Tester reports** supports [private intake and triage](tester-workflow.md).
Preview and import immutable submissions, bind them to tested builds and saved
record revisions, and link investigations to existing issues. Re-imports are
idempotent; stale writes are rejected. Suggested wording remains inactive and
human corrections are never changed by intake or triage.

**Release preparation** provides [private checksum manifests](release-preparation.md).
Select a build and patch, verify exact reconstruction and optional repeat-build
artifacts, review the metadata, then export a fresh manifest. No binaries are
copied, and validation or metadata review never grants release approval.

The [exception and content workflow](translation-exceptions.md) extends existing
issues with categories, actionable details, revision staleness and independent
source labels. Filters and the Details column expose these without changing
saved translations. Use the shared APIs for conservative legacy migration and
actual provider outcome reporting; no provider is contacted by Studio.

Builds also display [runtime evidence](runtime-evidence.md): capture sequences,
named assertions and exact build/snapshot/emulator provenance. Checks launch from
the explicit local CLI; browser commands cannot launch native code. Changed
associated revisions mark evidence stale. Existing screenshot associations link
captures to issues without conferring per-record approval.

Agents can read optional versioned [narrative context](narrative-context.md) through
`agent-context` and `narrative-context` in the shared CLI/authenticated local API.
The guide is private and read-only through this interface. Review notes identify
stale translation revisions; they neither alter translations nor certify runtime
behavior. No separate profile editor or per-line approval queue is introduced.

Studio displays timestamps in the browser's local timezone using a 12-hour clock
with AM/PM and a timezone label. This applies to activity, revisions, builds,
evidence, screenshot association history and agent task history/lease times.
Stored timestamps, API responses, exports and handoff prose retain their original
values; formatting is presentation only. Changing a machine's timezone changes
the displayed time, not the underlying event. Invalid dates display as unknown.

Layout-aware private builds can expose [dialogue layout decisions](dialogue-layout.md)
in record details and build summaries. Reports identify the saved revision and
window context; older revisions are marked stale. They are static build evidence,
not live draft previews or emulator approval. Unsupported overflow fails the
private build while retaining the correction and frozen inputs.

Studio is an optional, locally hosted browser UI for the same state API agents
use from Python or JSON commands. Ordinary browsing, editing, history, memory,
issues and progress do not require an AI agent. No provider API is called.

Studio also refreshes a [private numeric progress file](progress-reports.md) in
each initialized registered project on startup and every five minutes. It records
saved translation coverage, totals and a UTC timestamp for optional downstream
use. It does not publish data.

## Start with an explicit private project

On an installation with an existing Studio, follow [shared Studio setup](#shared-studio-setup)
and use its established launcher. For a fresh installation, from a source checkout
using Python 3.10+ with its standard SQLite module:

```sh
python tools/patchquest.py state ../private-workspace/project-001/project.json overview
python tools/patchquest.py studio ../private-workspace/project-001/project.json
```

Open the private session URL printed in the terminal. The server binds only to
`127.0.0.1`, normally on port 8765. Use `--port 8766` if occupied, or `--port 0`
to let the OS choose an available port. Leave the terminal running; Ctrl+C stops
it. Starting again restores project data and prints a new session URL. The
browser holds the session token only in tab session storage; it is removed from
the address bar. Do not share that URL. There is no public hosting mode.

For an invented, ROM-free trial:

```sh
python examples/studio-demo.py --workspace .local/projects/studio-demo
python tools/patchquest.py studio .local/projects/studio-demo/project.json
```

The demo requires a fresh destination. It creates fictional translation data,
not a playable game or ROM. The Studio itself never opens a ROM merely to browse
state and never imports or executes private project Python.

## Shared Studio setup

Use one explicit project registry for a shared installation:
`.local/config/local.json` in the selected platform checkout. Discover the
established launcher and session runbook through `.local/notes/README.md`.
Private projects retain their own authoritative `.patchquest/` databases; adding
a project to the shared selector does not copy, merge or migrate its records.

For an authorized new project:

1. Coordinate ownership of the shared registry and server refresh using the
   [collaboration workflow](agent-collaboration.md). A project-scoped agent should
   hand this change to the shared-workspace owner when its scope excludes shared
   configuration. Preserve unrelated entries and concurrent work.
2. Validate the explicit manifest and initialize/import its state through the
   normal private project setup. Add its manifest under `projects` in the existing
   local configuration. Paths resolve relative to the platform root unless absolute.
   For example, add the fictional entry
   `"sample": "../private-workspace/projects/sample/project.json"` alongside the
   existing entries; do not replace the whole configuration with an example.
3. Refresh the shared session through its established launcher after checking
   actual process/port ownership, queued/running jobs, worker ownership and leases.
   The registry is read at server startup; reopening a tab or reusing a running
   server does not reload it. Let active work finish. Never kill an unrelated
   process, clear a lease to force startup, or bypass a security control.
4. Account for open tabs before restarting: drafts live in browser memory and
   restart rotates the session token. Arrange for pending saves to finish and
   drafts to be saved or preserved; do not reload or close someone else's tab to
   make the check pass. If that cannot be established, leave the registered entry
   ready and defer the refresh, explaining the remaining step.
5. Open the fresh session, verify the new project in **Translation project**, and
   compare its counts with its own state API. Verify that other projects still
   appear and that its [private progress report](progress-reports.md) refreshes.
   The state store remains authoritative while other agents continue translating.

The shared CLI uses this registry. Python launchers must pass the same explicit
platform root to `serve`/`StudioServer`; omitting it creates a single-project
session. Use the established shared launcher by default. A temporary isolated
session is appropriate only when explicitly needed; record its ownership and
purpose privately, and retire it only after its user verifies the shared view
and preserves any drafts. Do not terminate another agent's temporary session.

Registration enables browsing/editing and progress reporting. Build support
requires a separately configured private adapter/worker; a selector entry alone
does not enable builds. Nothing in registration uploads project data or authorizes
publication. Real aliases, paths, ports, progress and refresh evidence belong in
private configuration/notes, not common documentation or skill adapters.

## Work in the browser

### Choose a translation project

The **Translation project** dropdown at the top right lists the launch project
and projects explicitly registered in `.local/config/local.json`. Registry paths
resolve relative to the platform root; no ROM-folder scanning or private code
loading occurs. Initialize each project's state through its normal setup first.
Missing manifests or uninitialized projects appear unavailable. Restart Studio
after adding or changing registry entries.

Selection applies to this browser tab. Switching reloads the view and asks before
discarding an unsaved translation, issue or screenshot form. The selector is
temporarily disabled while a save is in flight. Each project keeps its own
records, protected corrections, memory, issues, images, snapshots, jobs and build
history. Running builds continue in their original project when you switch away.
The Build button follows the selected project's registered worker; choosing a
project does not start its private pipeline or make an unavailable build ready.
The **Build worker** panel identifies loaded builders across registered projects
and shows queued/running job IDs and their current stages. **Switch builder to
selected project** unloads this Studio session's idle builder and loads the
selected project's explicitly configured adapter. It does not queue a build.
Queued/running jobs block switching; saved corrections and past outputs remain
in their original projects. Unconfigured adapters are identified explicitly.
Workers owned by separate launchers are visible but cannot be unloaded here.

The CLI enables the configured platform registry. Python composition roots opt
in with `serve(manifest, port=8765, platform_root=platform_root)`; omit the keyword
to retain a single-project session. No build callbacks are inferred from the
registry. Existing private workers continue to serve only their own state store.

HTTP clients can read authenticated `GET /api/projects` and pass an opaque
catalogue ID in `X-Studio-Project` for every `/api/` or `/media/` request. An absent
header retains the launch project for older clients; an unknown, empty or
unavailable ID is rejected, never silently redirected. Selection is request-local,
not a server-wide mutable setting, so independent tabs cannot redirect one
another's writes. Catalogue names are private and require the session token;
the catalogue does not return filesystem paths. The session token authorizes
all projects explicitly included in this Studio session, not separate users or
per-project access roles. Do not share it.

- **Translations:** search Japanese, English and IDs; filter scene, speaker,
  category and status. Select a record to see context, raw controls, bindings,
  history, suggestions and available associated screenshots. Edit **Japanese /
  source** to correct a transcription, or **English** to correct a translation,
  then **Save correction** to create a new protected revision. Source corrections
  preserve extracted byte references, control metadata and build bindings; they
  do not re-encode the ROM or automatically mark decoding verified. Revision
  history shows both source and English. Restoring history restores both as a new
  revision; it never deletes intervening work.
- **Memory:** contextual suggestions and glossary matches appear beside the
  active record. Current human corrections are prioritized; historical wording
  is labeled. **Edit current item** opens the item's latest saved revision for
  source or English correction, even when selected from a historical match.
  Old memory revisions remain intact. “Use as draft” copies only English; it
  does not save or propagate a translation. Compare
  context, controls and meaning before using it. This is lexical/context scoring,
  not an embedding service or automatic translator.
- **Glossary:** browse and correct terminology using the same revision and
  precedence rules. A glossary correction informs future work; it does not
  blindly rewrite every occurrence or change game mechanics.
- **Issues:** record wording, voice, culture, rendering, clipping or gameplay
  problems, with record IDs, scene, build and private evidence references.
  Status changes retain history. Save an issue, expand **Upload a screenshot**,
  choose a PNG/JPEG, describe it and save. Issue/record/scene/build links are
  prefilled from the issue. Verify them; associations default to provisional.
  **Edit associations** corrects links with revision checks and retained history.
  No OCR or automatic text matching is claimed.
- **Builds & activity:** view reported builds, validation, approval evidence,
  snapshots and recent events. “Freeze current build inputs” creates an immutable
  snapshot; it does not launch a build or approve a checkpoint. **Build test ROM**
  queues a full integrated build when an explicit private worker is online. Save
  corrections first: unsaved drafts are excluded. Follow the live stage and open
  the result's ROM/patch/validation locations when it finishes. This does not
  approve the result or claim emulator testing. Screenshots can also be uploaded
  here and associated later.

- **Agents & work:** view registered sessions, queued/leased/blocked/completed
  tasks, progress, explicit scope, dependencies and durable handoff history.
  The browser does not launch agents or edit ownership. Session labels and
  progress are reports; expired leases indicate lost authority, not proof of a
  stopped process. Human editing remains available during agent work.

The dashboard polls every two seconds without reloading the page. Open drafts
are not replaced by agent changes. A stale save returns a conflict; the text stays
in the editor. Copy it if needed, reload the current revision and reconcile.
Saved data survives restarts; unsaved drafts are not database records. Activity
is a timestamped agent report, not proof that a process is still alive.

## Storage and authority

### CSV bulk corrections

In Translations or Glossary, **Export filtered CSV** downloads all saved rows
matching the current search, scene, speaker, category, status and assessment
filters, including rows beyond the visible page. Unsaved drafts are excluded.
The UTF-8 CSV includes project ID, record ID, revision, source, target and context
columns. Preserve the headers, IDs and revisions; edit only `target`. Use a
spreadsheet's text import mode to preserve literal text, controls, leading zeros
and cells that begin with formula characters. CSV cells are exported verbatim.

**Import CSV** uploads corrections for the rows in that file, independently of
the current view filters. Only target wording is updated; other context columns
are informational. Changed wording is saved as human corrections with history,
just like editor saves. Unchanged rows do not create revisions or acquire human
correction status. Duplicate/unknown IDs, another project's rows, malformed CSV
or any stale revision reject the entire batch without saving any rows. Re-export
and reconcile stale wording before retrying. Blank targets intentionally clear
translations. Save or discard drafts first. Uploads are limited to 10 MB in the
browser and remain local; imports do not queue builds or modify frozen snapshots.

Each explicitly selected private project gains:

```text
.patchquest/
  state.sqlite3              authoritative heads and immutable revision history
  state.sqlite3-wal/-shm     SQLite live transaction files (when present)
  snapshots/                hash-addressed, immutable JSON build inputs
  backups/                  consistent SQLite online backups
  evidence/                 explicitly registered private image copies
  jobs/                     private failure diagnostics
  migrations/               private adapter's lossless import ledger, if used
```

The database uses WAL transactions, a write timeout and compare-and-swap revision
checks. Use a local disk, not a network share or concurrently synchronized folder.
It is not encrypted and does not defend against another process with OS write
access. Roles are workflow provenance, not a permission boundary against a
malicious local user. Do not put credentials or unnecessary personal details in
context, actor labels, notes or reports.

`records` and append-only `revisions` are authoritative. `memory` is a separate,
derived index of revision wording/context and can be rebuilt without changing
active records. Proposals have no authority until a deliberate human correction
or ordinary unprotected agent edit incorporates them. SQLite revisioning is not
a new Git repository. Frozen JSON snapshots are portable, independently hashed
inputs; keep them and migration sources private.

An agent edit is active immediately if the record is not human-corrected. No
translation approval queue exists. Once a human changes a record, subsequent
agent/import edits cannot replace it: the API records alternatives as proposals.
All writers must provide the revision they read. CAS conflicts must not be
“fixed” by blindly substituting the latest revision number.

## Shared JSON and Python interfaces

Use `python tools/patchquest.py state MANIFEST ACTION --input parameters.json`,
or `--input -` for JSON on standard input. Omit `--input` for operations with no
parameters. Keep actual parameter files in the private project. All successful
responses are JSON; a revision/import conflict exits with code 3, other invalid
inputs with code 2. Python callers may use `patchquest.state.Store` directly.

| Action | Parameters | Purpose |
|---|---|---|
| `overview` | none | Independent counts, activity and event cursor |
| `list` | `query`, `kind`, `scene`, `speaker`, `category`, `status`, `offset`, `limit` (optional) | Search/filter records; kinds translation/glossary |
| `get`, `history`, `proposals`, `evidence-list` | `key` | Read one record and its supporting history |
| `put` | `data`, `expected`; optional `role`, `actor`, `reason` | Create at revision 0 or update with CAS; role defaults to agent |
| `upsert` | `project_id`, `changes`; optional `actor`, `reason`, `dry_run` (default true) | Atomic agent-only batch with replay detection and protected corrections; see [record upserts](record-upserts.md) |
| `restore` | `key`, `revision`, `expected`; optional `actor` | Human restoration as a new protected revision |
| `import` | `records`; optional `actor` | Atomic, idempotent initial migration; different original payloads conflict |
| `work-publish` (source interpretation) | `session`, `key`, `fence`, `changes`, nonempty `reason`, `source_revision: true` | Fenced, atomic source/decoded/controls/context revisions; preserves targets and raw bindings. See [coordination](agent-collaboration.md#conflicts-and-recovery). |
| `memory` | `key` or `source`, `scene`, `speaker`; optional `limit` | Suggestions, never automatic replacement |
| `memory-rebuild` | none | Rebuild derived memory from authoritative revisions |
| `activity` | `message`; optional `actor`, `status` | Persist working/idle/blocked/finished report |
| `events` | optional `after`, `limit` | Monotonic durable event cursor |
| `evidence` | `key`, `revision`, `stage`, `passed`, `reference`; optional `build_id` | Record an explicit, evidenced technical/runtime result |
| `issues`, `issue-history` | none / `key` | Browse issue state and history |
| `issue-put` | `data`, `expected`; optional `actor` | Versioned issue update with record associations |
| `snapshot`, `snapshot-export` | none / `digest` | Freeze a consistent transaction, then materialize its hashed JSON |
| `builds`, `build-report` | none / `data`, `expected` | Read/write versioned build reports, not command execution |
| `attach`, `attachments` | `path`, optional `description`, `record_ids`, `build_id` / optional `key` | Register a private PNG/JPEG under the project; list registered evidence |
| `backup` | none | Consistent online SQLite backup; do not copy a live DB alone |
| `attachment-update`, `attachment-history` | `digest`, `data`, `expected` / `digest` | Correct associations with CAS/history; image bytes remain immutable |
| `capabilities`, `jobs` | none | Inspect the worker, supported modes and durable job states |
| `build-submit` | `request_id`, optional `mode` (`full`) | Atomically capture saved revisions and queue an idempotent job |

A complete record example is in [the synthetic Studio example](../examples/studio-demo.py).
Core fields are `id`, `kind`, `source`, `target`, `scene`, `speaker`, `category`,
`context`, `controls`, `uncertainty`, `decoded`, `source_ref`, and `build_binding`.
The last three objects and control list carry private, opaque data. The generic
platform does not infer a game's encoding or execute a build binding.

Issue data includes `id`, `title`, `description`, `category`, `status`,
`record_ids`, `scene`, `build_id` and `references`. Build reports include `id`,
`snapshot`, `status`, `summary`, `artifacts`, `validation`, `approval` and
`evidence`. Build approval, when reported, requires an explicit reference to the
user's decision; success never sets it. Private project adapters must supply
truthful evidence, not claim that arbitrary API data was independently verified.

## Progress and build integration

Discovery counts only catalogued translation records, never an assumed whole
game. Decoded is explicitly reported, not inferred from the presence of Japanese
characters. Translated means nonempty active English. Uncertainty is independent
of translation and can overlap it. Inserted, automated, emulator and hardware
stages require separate evidence for the exact record revision. New edits do not
inherit stale validation; old evidence remains in history. A whole-build approval
does not certify all records or invent a full playthrough/save test.

Private runners consume snapshots, validate their hash/project/source identity,
and pass active text through the existing controls, encoding, layout, resource,
checksum, BPS and repeatability checks. Build from originals, not derivative
ROMs. If a binding cannot support an edit, retain it and report a technical
failure; never silently drop it, overwrite an original or approve a checkpoint.
Historical recipes can continue using their frozen legacy records for exact
reproduction. The new explicit snapshot command is the active editing route.

Snapshots isolate running builds from concurrent edits. Build reports must name
that snapshot; resulting per-record evidence names the captured revisions, not
whatever happens to be current when the build finishes. Language records and
glossary need no human approval to enter a build. Their semantic quality and
runtime validation are separate from generic state-store validity.

## Recovery, security and limitations

### Explicit private build worker

For browser-controlled switching, the private composition root explicitly
supplies callbacks for registered, initialized projects. The public platform
does not discover modules, infer pipelines from manifests or execute browser
commands. Example (independently authored placeholder projects):

```python
from patchquest.studio import serve
from patchquest.studio_builders import BuilderBinding

serve(harbor_manifest, port=8765, platform_root=platform_root,
      builders=[BuilderBinding(harbor_manifest, harbor_pipeline, "Harbor builder"),
                BuilderBinding(garden_manifest, garden_pipeline, "Garden builder")],
      initial_builder=harbor_manifest)
```

Omit `initial_builder` to start with no managed worker. A registry entry alone
does not configure a callback. `GET /api/builder-status` reports the selected
project, online workers, active job stages, switching eligibility and an opaque
version. Authenticated `POST /api/builder-switch` accepts only `{"expected":
"version-from-status"}`; `X-Studio-Project` selects the destination. Both routes
use the same token, origin and explicit project checks as other Studio APIs.
Stale tabs receive a conflict instead of unloading a newly selected worker.

The source worker's idle check and removal share a database transaction so
concurrent CLI/browser submissions cannot leave a newly queued job behind.
Target registration checks ownership and unfinished jobs again. Startup failure
attempts to restore the prior builder, reports failure and preserves job history;
it never steals another launcher's worker or resumes abandoned queued work.
Switches are serialized in the serving process. Separate launchers retain their
own per-project leases; this is not a machine-wide process manager. Loading a
callback preserves all normal snapshot, validation and content/build gates.
Restart a resident server to load newly configured callbacks or Python changes.

The earlier standalone-worker composition remains supported:

The generic Studio command supports browsing and corrections; its build button
is disabled without a worker. Start the private project's documented launcher
to enable builds. Public code never discovers/imports that project. A private
composition root imports `BuildWorker`, supplies its own validated callback,
then calls `patchquest.studio.serve` with the explicit manifest:

```python
store = Store(manifest)
worker = BuildWorker(store, validated_pipeline, "Project build pipeline").start()
try:
    serve(manifest, port=8765)
finally:
    worker.close()
```

Import these from `patchquest.state`, `patchquest.jobs` and `patchquest.studio`.
The callback receives `(job, progress)`; `job['snapshot']` identifies immutable
inputs. Read them via `store.export_snapshot`, validate project/source/bindings,
write a fresh destination through `OutputPolicy`, and return a build report with
`status: validated`, `approval: {approved: false}`, artifact paths and validation
evidence. Call `progress` for meaningful stages. Exceptions fail the job and
retain diagnostics privately. Run the same checksum, control/layout/capacity,
repeat-build and patch-reconstruction checks as the private CLI before returning
success. Browser requests supply no commands, module names, paths or callback code.

Only one worker and one active job are accepted per project. A repeated request
ID returns the same job, avoiding duplicate outputs after connection trouble.
New edits do not change queued/running snapshots; retry after failure creates a
fresh job and captures current saved revisions. Queued jobs survive restart.
A 120-second worker lease detects interruption: unfinished running jobs become
`interrupted`, never automatically successful or automatically retried. Graceful
shutdown drains the in-flight build. Forced termination can leave partial outputs;
preserve them and use a new job rather than overwriting. There is no build cancellation or
selective-build mode. Translation-work scheduling is separate from build jobs. Full builds are the only advertised mode.

### Screenshot evidence

Browser upload is token-protected and limited to PNG/JPEG, 10 MiB, dimensions
up to 8192 per axis and 16 megapixels. Bounded format/container checks reject
malformed headers/chunks; they are not a complete image decoder or malware scan.
Images retain original bytes and embedded metadata in the private project.
There is no automatic publication or metadata sanitization for public sharing.
Do not upload credentials or unrelated personal information.

Files are stored by SHA-256. Uploading the same image again preserves existing
associations. Use **Edit associations** to change record IDs, issue IDs, scene,
interface resource, build label, description, or provisional/confirmed confidence.
Record/issue IDs must already exist; scene, resource and build labels are contextual
text and require human interpretation. `Store.upload(bytes, metadata)` provides
the same Python API; HTTP transports base64 JSON without arbitrary filesystem
access. `attachments` accepts optional `key` and `issue_id` filters. Association
history is independent of issue history and does not certify gameplay, identify
text automatically or approve a translation. Correcting links preserves the image.

### Backups and limits

Run `backup` before a migration or deliberate storage maintenance. To restore,
stop Studio and all agents writing that project, preserve the entire current
`.patchquest/` as a private rollback, and restore the backup database alongside
the existing immutable snapshots/evidence. Do not mix a restored database with
old WAL/SHM files. Verify identities and run `overview`/history checks before
resuming. The backup covers database state; separately back up snapshots,
registered images, source records and recipes. Schema 2 adds jobs and attachment
history while retaining schema-1 data. Schema 3 adds agent sessions, scoped work
leases, permanent coordinated-record markers and task history; it preserves
translation heads and snapshots. Back up before upgrading and restart all
long-running Studio/worker processes to load coordinated write checks. Managed job
interruption is detected by the lease. A separate legacy runner's build report
may still say running: reconcile it with actual diagnostics, never infer success.

HTTP access requires a random per-launch token for every private read/write.
The server rejects foreign Host/Origin headers, serves only fixed public UI
files and registered hash-verified images, and exposes no shell, directory
browser or ROM download endpoint. It sets a restrictive content security policy
and no-store responses. This is a single-user local tool, not a multi-user
authentication service; do not reverse-proxy it onto a public interface.

Only explicitly registered/uploaded PNG/JPEG evidence is viewable. Automatic
screenshot matching, selective builds, provider orchestration and semantic/vector
retrieval remain later work. Translation-work leases are implemented through
[the coordination API](agent-collaboration.md); its `agent-context`,
`agent-sessions`, `work-list` and `work-history` read views are also authenticated
Studio routes. Coordination writes use the CLI/Python API, not browser commands. See
[roadmap](studio-roadmap.md) and [agent compatibility](agent-compatibility.md).

### Optional runtime review provider

A trusted local launcher may configure `StudioServer(...,
runtime_review_providers=[(manifest_path, provider)])` for an already registered,
initialized project. Each provider implements `read(store, params) -> dict` and
`image(store, evidence_id, sha256) -> bytes`. Duplicate, unknown and incomplete
provider registrations are refused. This does not discover private adapters or
enable review on other projects automatically.
The `serve(...)` convenience entrypoint accepts the same optional
`runtime_review_providers` argument for launchers using its managed server lifecycle.

Authenticated `GET /api/runtime-review` accepts optional `group_id`, `build_id`,
`status`, `method`, `purpose`, `offset` and `limit`. Selectors are opaque IDs, not
paths. Statuses use the existing coverage contract; methods are `synthetic` or
`automated_runtime`, and purposes are `renderer` or `normal_gameplay`.
Pagination defaults to offset 0 and limit 50, with a maximum limit of 200.
The response includes `schema_version: 1`, `project_key` and `available`.
Unconfigured projects receive `available: false` and empty results. Detailed
presentation fields belong to the review provider; the transport does not
recompute coverage or infer verification from viewing a report.

`GET /api/runtime-review-image?evidence_id=...&sha256=...` serves only immutable
PNG bytes returned by that selected project's provider. The server verifies the
digest, PNG signature and size bound. The existing token, local-origin and
`X-Studio-Project` protections apply to both routes; images need authenticated
fetches rather than token-bearing URLs. Responses are never cached. Unknown
parameters, duplicate selectors and filesystem paths are rejected. JSON pages
are bounded to 2 MiB and images to 14 MiB.

The provider must use the [coverage receiver](runtime-catalog-coverage.md) with
server-owned producer admission and artifact resolvers, recheck catalog
freshness, and allow only evidence belonging to the selected project. Neither
request parameters nor imported result labels can configure authority. Prepare
and register new contact sheets through the existing artifact service before
serving them; a GET is not permission to run emulators, create artifacts, modify
translations or publish screenshots. Original captures remain immutable.

This optional transport seam does not itself install a provider, refresh the
shared server, persist a coverage report, or supply the Studio review interface.
