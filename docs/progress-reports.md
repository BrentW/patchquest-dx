# Private translation progress reports

Studio writes `.patchquest/translation-progress.json` inside each initialized
project selected by its explicit local registry, including the launch project.
It refreshes on startup and every five minutes while the server runs. No browser
tab, AI agent or build worker is required. Unavailable/uninitialized projects are
skipped; projects added to the registry become available after restarting Studio.
No ROM is read and no translation, correction, snapshot or checkpoint is changed.

The file is a mutable private cache. Nothing is uploaded, published, committed or
exposed through an unauthenticated HTTP route. Authorized local consumers can
read the file independently of Studio. Keep the project directory and Studio
token private.

An invented example:

```json
{
  "schema_version": 1,
  "report_type": "translation-progress",
  "updated_at": "2026-01-01T12:00:00+00:00",
  "basis": "catalogued_translation_records",
  "total_records": 80,
  "translated_records": 60,
  "remaining_records": 20,
  "percent_translated": 75.0
}
```

Only current saved records of kind `translation` count. A target must contain
non-whitespace text. Glossary entries, historical revisions, inactive proposals
and unsaved browser drafts do not count. Each record has equal weight, regardless
of text length. Saved human corrections count as saved translations and remain
protected. Uncertain or unverified saved translations count too: this measures
translation coverage, not language approval, insertion, emulator verification or
release readiness. An untranslated exception remains in the denominator.

The denominator is the catalog currently known to the platform, not necessarily
all text or artwork in a game. Newly discovered records or cleared targets can
reduce the percentage. An empty catalog has `percent_translated: null` (unknown).
Percentages use one decimal place, capped at 99.9 until every catalogued record
has a saved target. Even 100% does not establish whole-game completion.

The timestamp is UTC and advances only after a successful measurement. Consumers
should display its age and treat old reports as stale, especially when Studio is
stopped. Refresh failures retain the last valid file and timestamp, emit a generic
local warning once per failing project, and retry next cycle without stopping
other projects. A locked file may delay a refresh. Consumers should close their
file handle after reading so Windows can replace it.

Writes use a same-directory temporary file and atomic replacement, serialized
with other report writers and saved edits through a brief project database lock.
Only this fixed cache filename can be replaced. Linked destinations, unrelated
existing files and unsupported report versions fail closed. These checks protect
against accidental redirection; OS write access remains trusted, as for the
state store. No arbitrary output path or publishing command is accepted.

## Headless use and interval

From a platform checkout:

```sh
python tools/patchquest.py state ../private-workspace/project-001/project.json progress
python tools/patchquest.py state ../private-workspace/project-001/project.json progress-report
python tools/patchquest.py studio ../private-workspace/project-001/project.json --progress-interval 300
```

`progress` returns a fresh read-only measurement without writing the file;
`progress-report` refreshes the file once and returns the same numeric object.
Neither starts a server. The authenticated local `GET /api/progress` follows the
selected project and has the same read-only behavior. The file-writing action is
CLI/Python only. Private launchers using `serve` or `StudioServer` automatically
receive the default refresh; optional `progress_interval` is an integer from 1 to
86400 seconds. CLI `--progress-interval` has the same bounds and default of 300.
The interval is a delay between refresh cycles; unavailable storage can delay it.

The schema deliberately omits project titles, paths, ROM hashes, source/target
text, record identifiers, issue details and runtime evidence. It is a numeric
measurement, not a project registry or permission to disclose project data.

The same reporter also writes the separate private
[`readiness-summary.json`](verification-readiness.md#private-summary-schema-version-1)
cache. Its explicit plans, method-aware stages and build-specific evidence never
alter this translation percentage. Missing plans remain unknown. Readiness
refresh failures do not stop translation-progress refreshes or publish anything.
