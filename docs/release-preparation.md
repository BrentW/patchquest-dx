# Private release preparation

Prepare an exact-file checksum manifest from an explicitly selected private build,
without copying its patch, original image or translated output. Preparation is not
a release, permission to redistribute, gameplay verification or publication. The
platform supplies no approval or publishing operation in this workflow.

## Studio workflow

Open **Release preparation**, then **New release candidate**. Select the build,
its patch artifact and its output image artifact. These are registered artifact
names, not browser-supplied paths. Optionally select a distinct repeat build using
the same artifact names. The source is exclusively the selected project's pinned
original. No private build adapter is invoked and no source collection is scanned.

Author the release ID, title, version, source edition/revision label, portable patch
and output filenames, compatibility requirements and limitations. Describe the
actual scope; do not imply a complete translation, runtime coverage or support for
untested editions. Actual values remain private. Private notes are separate.
Save the draft, **Validate saved candidate**, inspect **Manifest content**, then
**Mark metadata reviewed**. That records an inspection of these exact fields and
checksums, not a rights assessment or release approval.

**Export private release manifest** creates a fresh JSON file under the selected
project's output directory in `release-manifests/<generated-id>.json`. The result
returns the exact file path and SHA-256. Exports never replace an earlier file.
No binary file, screenshot, build report, translation or internal note is copied.
Edits, including notes, clear validation and review; old versions remain in the
private journal. Changed source bytes, artifacts, snapshot or build reports block
review/export until validated and reviewed again. Conflicting saves retain the
browser draft. Browsing a saved draft does not itself read the original image.

## Validation and its limits

- The entire original file must match the manifest's pinned SHA-256. There is no
  header stripping, padding, byte swapping, decompression, file repair or fuzzy
  source matching. A headered and unheadered image are different inputs.
- The registered build must have `validated` status and an intact immutable
  translation snapshot for this project/source. This status is a pipeline report;
  preparation independently checks the patch, not every assertion in that report.
- Selected patch and output bytes are bounded to 64 MiB each; so is the source.
  Explicit build artifacts are hashed under the project's output policy. Missing
  files, path escapes and changes observed during validation fail closed.
- BPS1 source/target sizes and all three CRCs must pass, and applying the patch to
  the pinned source must reconstruct the exact selected output bytes. The current
  verifier supports the platform encoder's **SourceRead/TargetRead subset**.
  SourceCopy/TargetCopy, IPS and other formats fail as unsupported, not validated.
  Oversized/truncated integers, invalid lengths, CRC errors and extra bytes fail.
- If a repeat build is selected, it must be a distinct registered build with the
  same snapshot and byte-identical selected patch/output artifacts. The result is
  `matched_registered_artifacts`; otherwise it is `not_provided`. Matching two
  reports does not prove independent execution. This module never reruns a recipe.
- Historical build snapshots remain fixed when current translations change.
  Preparation does not claim the candidate contains the latest corrections.
  Review the selected build's scope separately before any actual release.
- Runtime and rights remain `not_assessed`. Use the existing [verification](verification-readiness.md)
  and [runtime evidence](runtime-evidence.md) workflows for scoped observations.
  Checksums and patch reconstruction do not establish a completed playthrough,
  save compatibility, hardware compatibility, legal rights or owner acceptance.

Metadata and literal byte counts reveal how much patch content needs inspection,
not whether that content is redistributable. A patch may embed original-game data,
translated text, artwork, fonts or private metadata. Read the [licensing guide](licensing.md),
retain applicable notices, and perform a separate review of the exact proposed
distribution and its rights basis. No automatic legal classification is made.
Do not infer that every BPS is safe to publish because it is a patch.

## Manifest schema: version 1

The exact preview is the export. All fields are constructed explicitly; private
state rows are never serialized wholesale. Fields are:

| Field | Meaning |
|---|---|
| `schema_version`, `report_type` | `1`, `release-manifest` |
| `publication_approved`, `release_approved` | Always `false`; no approval is inferred or accepted as input |
| `release_id`, `title`, `version` | Explicit authored identity for this candidate |
| `source_label` | Explicit required edition/revision description |
| `patch_filename`, `output_filename` | Authored portable basenames; never inferred from private paths |
| `compatibility`, `limitations` | Required plain-text scope and requirements |
| `input_policy` | `exact_file_no_normalization` |
| `source`, `output` | Exact whole-file `bytes`, lowercase `sha256`, eight-digit lowercase `crc32` |
| `patch` | `format: BPS1` plus the same size/checksums |
| `checks.reconstruction` | `passed` for the exact selected source/patch/output |
| `checks.decoder` | `bps1-source-read-target-read` |
| `checks.metadata_bytes`, `checks.literal_bytes` | Counts only; no literal or metadata contents |
| `checks.repeat_build` | `not_provided` or `matched_registered_artifacts` |
| `checks.runtime`, `checks.rights` | Always `not_assessed` |

No internal project ID, build ID, snapshot hash, record IDs, local paths, review
actor, private notes, logs or timestamps are exported. Authored text and exact-file
checksums can themselves identify a project: these files are private until the
owner separately authorizes sharing the exact reviewed selection. Metadata review
cannot guarantee that an author did not put sensitive information in a text field.

A downstream patch consumer must accept only a supported schema/input policy,
verify the exact source size and SHA-256, verify the separately obtained patch
size and SHA-256, apply the supported BPS patch, then verify output size and
SHA-256 before offering the result. CRC32 alone is not the source identity gate.
Do not silently try another edition, strip a header or stack patches. This
manifest contains no download URL, binaries or permission to distribute them.
Treat all text as data, not markup or commands. Filenames are suggested basenames.

## Shared API

Use `python tools/patchquest.py state <explicit-private-manifest> <operation>` with
JSON through `--input <file>` or `--input -`. All operations are advertised through
`agent-context`, so provider adapters use this same contract.

| Operation | Parameters |
|---|---|
| `release-candidates` | None; private drafts, prior validation and reviews |
| `release-put` | `data`, `build_id`, `patch_artifact`, `output_artifact`, `expected`; optional `key`, `repeat_build_id`, `private_notes`, `actor` |
| `release-validate` | `key`, `expected`, optional `actor`; stores checked binding/manifest, clears review |
| `release-preview` | `key`; rechecks files and binding, returns exact `manifest`, `token`, `reviewed` |
| `release-review` | `key`, `expected`, inspected `validation_token`, optional `actor` |
| `release-export` | `key`, `expected`, inspected `validation_token`, new relative `destination`, optional `actor` |
| `release-history` | Optional `after` event sequence, `limit` (1–500, default 100) |

See the [invented candidate input](../templates/project/release-candidate.example.json).
`data` requires exactly the eight authored fields above. IDs are lowercase letters,
digits, underscores or hyphens, at most 80 characters. Text fields are nonblank,
up to 160 characters, or 4,000 for compatibility/limitations; notes allow 8,000.
Filenames allow ASCII letters/digits/underscores/hyphens and one extension, with
Windows device names rejected. Patches use `.bps`; outputs use `.sfc`, `.smc`,
`.nes`, `.fds`, `.d88`, `.rom` or `.bin`. There are at most 100 saved candidates.
Unknown fields, same-build repeat comparisons and identical artifact roles fail.

Writes use candidate revision checks and transactions. Review/export also compare
the inspected validation token with freshly read bindings; no `force` or approval
bypass exists. Studio supplies its actor and a generated export destination;
browser requests cannot choose a path or an actor. The authenticated local server
is not a public release service. Shared-server refresh ownership is unchanged.

Originals and artifacts are never modified, and preparation never writes records,
memory, human corrections, checkpoints or approval state. Output writes are
exclusive, complete JSON snapshots. Cooperating state writers are serialized;
external filesystem edits are not locked. Consumers must independently verify
the bytes they receive against the exported checksums. Interrupted exports may
leave a complete private file without a corresponding event; never overwrite it.

Regression coverage uses invented bytes, snapshots and reports. The optional
[browser check](../tools/releases_browser_check.cjs) uses an isolated synthetic
project and installed browser tooling; it does not restart shared Studio or
demonstrate actual emulator compatibility or permission to release any game.
