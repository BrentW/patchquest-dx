# Local Translation Studio

Layout-aware private builds can expose [dialogue layout decisions](dialogue-layout.md)
in record details and build summaries. Reports identify the saved revision and
window context; older revisions are marked stale. They are static build evidence,
not live draft previews or emulator approval. Unsupported overflow fails the
private build while retaining the correction and frozen inputs.

Studio is an optional, locally hosted browser UI for the same state API agents
use from Python or JSON commands. Ordinary browsing, editing, history, memory,
issues and progress do not require an AI agent. No provider API is called.

## Start with an explicit private project

From a source checkout, using Python 3.10+ with its standard SQLite module:

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

## Work in the browser

- **Translations:** search Japanese, English and IDs; filter scene, speaker,
  category and status. Select a record to see context, raw controls, bindings,
  history, suggestions and available associated screenshots. Save a correction
  to create a new protected revision. Restoring history also creates a revision;
  it never deletes intervening work.
- **Memory:** contextual suggestions and glossary matches appear beside the
  active record. Current human corrections are prioritized; historical wording
  is labeled. “Use as draft” does not save or propagate a translation. Compare
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
| `restore` | `key`, `revision`, `expected`; optional `actor` | Human restoration as a new protected revision |
| `import` | `records`; optional `actor` | Atomic, idempotent initial migration; different original payloads conflict |
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
