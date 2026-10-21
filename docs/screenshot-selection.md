# Reviewed screenshot metadata

Screenshot selection prepares explicit, reviewed metadata for existing private
captures. It does not capture gameplay, edit images, copy image bytes, authorize
publication, or approve a build. Uploaded images remain in the selected project's
private evidence store. Existing attachment associations remain unchanged.

## Studio workflow

Upload or register a screenshot through the existing **Builds & activity**
workflow. Then open **Screenshot selection** and choose **Prepare screenshot**.
Inspect the displayed image, write a caption and accessible description, choose
a spoiler flag, and supply an explicitly reviewed build label if it is linked to
a build. The private build ID is not copied into the export. Leave the capture
date blank when unknown. Notes and evidence references belong in **Private
capture notes**, which are excluded from exports.

Capture provenance defaults to unknown. A reported emulator or hardware capture
remains a report, not proof of execution. Static previews and synthetic images
have separate labels. If an image has a registered runtime capture, choose the
specific **Registered capture reference**. The platform checks the registered
report, source image, capture occurrence, snapshot, build artifacts, scenario and
configuration before allowing that provenance to be reviewed.

Save the draft, reopen it and **Mark capture reviewed**, then **Select capture for
export**. Review covers the image, caption, build label, provenance and spoiler
classification. The exact metadata preview is available before export. A fresh
JSON file is created under the private output directory in `screenshot-selection/`.
No image bytes or embedded image metadata such as EXIF are exported.

Edits invalidate review and selection. Changes to attachment associations or the
linked build report make the saved selection stale; registered captures also
become unavailable if their checked evidence changes. Stale selected entries
block the whole export instead of being silently omitted. Save a refreshed draft
and review it, or use **Remove from export**, which also works when an image is
missing. Earlier exports remain immutable. Refresh the section to see changes
from other editors; polling does not overwrite an open draft.

## Provenance and scope

- `reported` provenance describes an explicit local claim. Confirmed attachment
  associations are still reported associations; they do not verify runtime.
- `registered_run` binds the selected image to the recorded capture and build.
  A real-emulator-shaped report exports `registered_runtime`; a synthetic report
  remains `synthetic` and cannot be relabeled as real runtime through this API.
- The run's `passed` or `failed` status is retained. A screenshot from a failed
  run can be useful, but selection never changes that result.
- Identical images may occur at several frames. Choose the capture occurrence
  explicitly when ambiguous; the exported frame then describes that occurrence.
- Captures document the named historical build, not current translations. Later
  translation corrections do not rewrite historical images or establish that
  they depict current work. No per-record evidence or approval is created.

Local report registration is provenance, not cryptographic attestation of an
emulator or adapter's honesty. Review assertions are likewise caller provenance,
not authenticated publication permission. Image rights and owner publication
decisions remain separate; see [licensing](licensing.md). No network service is
contacted and no existing checkpoint or production translation is changed.

## Shared operations

Use `python tools/patchquest.py state <explicit-private-manifest> <operation>`
with `--input <json-file>` or `--input -` for parameters. Discovery is shared
through `agent-context`. Studio exposes a bounded subset with its local token
and selected-project guard; browser callers cannot supply an output path or actor.

| Operation | Parameters and behavior |
|---|---|
| `screenshot-context` | Required image `digest`; optional `runtime_report` SHA-256 and `runtime_capture` occurrence ID. Returns private binding token, image dimensions/type, association status and registered capture choices |
| `screenshot-selection` | Private board with collection revision, draft metadata, private notes, review provenance and live `stale` flags |
| `screenshot-put` | `digest`, `context_token`, `data`, `expected`; optional `key`, `runtime_report`, `runtime_capture`, `private_notes`, `actor`. New entries omit key and use expected zero |
| `screenshot-review` | `key`, item `expected`, inspected `review_token`, optional `actor`; binds review to metadata and screenshot context |
| `screenshot-select` | `key`, item `expected`, boolean `selected`, optional `actor`; selection requires fresh review; removal does not |
| `screenshot-preview` | Exact allowlisted selected metadata, or an error for any stale selected item |
| `screenshot-export` | Collection `expected`, fresh relative `destination`, optional `actor`; returns private path, byte SHA-256, count and selection revision |
| `screenshot-history` | Private journal with optional `after` sequence and `limit` (1–500, default 100) |

Get context before editing and retain the returned token. A changed context or
item revision rejects the write. Review uses the saved `review_token` actually
inspected. Runtime references are optional; use empty strings when absent. The
data object requires exactly these six fields:

```json
{
  "caption": "Invented menu spacing comparison.",
  "alt_text": "A tiny invented color grid.",
  "spoiler": "unknown",
  "build_label": "Test build one",
  "capture_kind": "unknown",
  "capture_date": ""
}
```

Caption and alt text are nonblank, limited to 1,000 and 500 characters. Build
labels allow 160 characters; linked images require a label, unlinked images
require an empty label. Spoiler values are `unknown`, `none`, `spoilers`; unknown
must not be presented as spoiler-free. Capture kinds are `unknown`,
`reported_emulator`, `reported_hardware`, `static_preview`, `synthetic`, and
`registered_runtime`. A runtime reference requires the kind derived from its
checked report. Capture dates use `YYYY-MM-DD` or empty for unknown and are
explicitly reported dates, not inferred file dates. Private notes allow 8,000
characters. Text is literal; consumers must not execute markup.

## Export schema, version 1

The document contains `schema_version: 1`, `report_type: "screenshot-selection"`,
`selection_revision`, `publication_approved: false`, `release_approved: false`,
`images_included: false`, and `items`. Each item contains:

- Opaque `id`, item `revision`, `caption`, `alt_text`, `spoiler`;
- `image`: selected image `sha256`, `mime`, `width`, `height`;
- `build`: reviewed `label` and `association` (`unlinked`, `provisional`, `confirmed`);
- `capture`: `kind`, `basis` (`reported` or `registered_run`), reported `date` or
  null, `runtime_status` (`passed`, `failed` or null), and `frame` or null;
- `metadata_sha256`: SHA-256 of that item's other fields in canonical UTF-8 JSON
  (sorted keys, compact separators, unescaped Unicode, no nonfinite numbers).

Entries are ordered by opaque ID. This is a complete selection snapshot, including
an empty list when nothing is selected. It excludes paths, filenames, raw build
IDs, ROM/source hashes, record IDs, review actors, notes, raw reports, image bytes
and internal logs. The selected image hash identifies the exact bytes reviewed;
it does not confer rights to distribute them. Explicitly authored fields can
still contain private text; reviewers must inspect them, with no promised
automatic redaction. Metadata export cannot clear or redact an image.

Use an explicitly chosen snapshot and replace the previous selection, including
an empty one. Do not merge historical exports: deselection does not revoke old
files or automatically retract content from an external consumer. Unsupported
schema versions must remain unknown. Any later image distribution must verify
the chosen bytes against the metadata digest and have its own authorization.

The shared [editorial snapshot writer](milestone-updates.md#export-schema-version-1)
uses complete, exclusive file promotion and never overwrites an output. The
database lock prevents cooperating writers from changing associations during
capture/export. It is not a hostile filesystem sandbox; files can be changed by
external programs and consumers should recheck hashes. A crash after creating
the file but before the journal commit can leave a complete unjournaled export.

## Validation

Synthetic tests cover review binding, stale associations/builds, tampered image
and runtime evidence, failed runs, synthetic versus real-report shapes, repeated
frame occurrences, privacy allowlists, conflicts, isolated projects, exports and
protected corrections. The real-report-shape fixture tests parsing only and is
not evidence of emulator execution. The optional browser check covers the Studio
flow, loaded-image review, spoiler labels, conflict retention and mobile layout
using invented images. No private game data is needed for these checks.

Run `python -m unittest discover -s tests` for the automated suite. The optional
[browser check](../tools/screenshot_selection_browser_check.cjs) uses an already
installed Playwright module and browser, with optional `PYTHON`,
`PLAYWRIGHT_MODULE` and `BROWSER_EXECUTABLE` environment settings. It creates an
isolated synthetic project/server and retains its temporary evidence locally;
it never starts or refreshes an existing Studio session.
