# Local setup

Use Python 3.10+ and Git. No third-party package is required; do not download tools automatically. Run from the platform checkout:

```powershell
python tools/patchquest.py doctor
python -B -m unittest discover -s tests -p "test_*.py" -v
```

Missing .local/ is normal. Doctor uses defaults and creates nothing. Public tests use synthetic data and shared font artwork without private project imports. Filesystem-link tests use the available OS facility and report unavailable capabilities explicitly.

## Private settings

Create .local/config/ and copy [config/local.example.json](../config/local.example.json) to .local/config/local.json **only if absent**. Never overwrite real settings from a template. Create .local/notes/README.md as a concise private index; see [the workspace guide](local-workspace.md).

| Supported schema 2 field | Behavior |
|---|---|
| `schema_version` | Integer 2; older versions require deliberate migration |
| `projects` | Alias → manifest path strings; relative paths are resolved by agents against the platform root; never auto-selected/executed |
| `emulators.snes9x`, `emulators.mesen` | Executable path or null; doctor checks existence without launching |
| `privacy_terms` | Local identifying strings/fingerprints of at least three characters used by publication audits |

Other tool locations, versions, hardware capabilities and procedures belong in human-readable private notes, not invented parser settings. Unknown fields and malformed values are rejected.

For schema 1 migration, preserve the old config privately, move collection/source identities into the private project, replace the old collection-path field with a projects registry and retain emulator/privacy values. Preserve the old config with any frozen legacy runner. No automatic migration overwrites values.

## Commands

```powershell
python tools/patchquest.py --help
python tools/patchquest.py project-check ../private-workspace/projects/example/project.json
python tools/patchquest.py inspect ../private-workspace/projects/example/roms/source.sfc
python tools/patchquest.py font output/font-review --output-root output
python tools/patchquest.py audit --history --report .local/logs/publication-review.json
```

Paths are fictional examples. Use fresh destinations. Actual inspection/extraction reports are private.

`extract SOURCE MANIFEST DESTINATION --output-root DIRECTORY` accepts source_sha256, explicit ranges with string offsets/integer lengths, and an optional hex-byte-to-text table. Unknown bytes remain visible and lossless.

`insert SOURCE MANIFEST DESTINATION --output-root DIRECTORY` accepts source_sha256 and edits with offset, expected_hex and replacement_hex. It requires equal lengths and does not repoint strings or choose a checksum header automatically.

`bps-create SOURCE TARGET DESTINATION --output-root DIRECTORY` and `bps-apply SOURCE PATCH DESTINATION --output-root DIRECTORY` write exclusively under the selected root. Verification rejects wrong sources/bad CRCs; decoding supports only the encoder's SourceRead/TargetRead subset. Independent interoperability is a separate pre-distribution check.

Copy [the project template](../templates/project/README.md) outside this checkout for real work. Use its private runner and verified recipe, with game extraction/encoding/assembly implemented privately. The [architecture guide](project-architecture.md) documents path and safety behavior.

Audit exit status is nonzero for findings, including historical objects with --history. This does not authorize deleting evidence or rewriting Git. Reports may contain private paths/object IDs; the CLI accepts only fresh reports inside .local/logs. A clean scan is not publication approval.
