# Private projects and the public platform

The dependency direction is **private runner → public Python library**. The platform owns generic algorithms and never imports project code. Encodings, pointer formats, hooks, allocations, translations and runtime tests remain private, even when they inspired a public improvement.

## Directory contract

Prefer an external private workspace beside the platform checkout:

```text
platform/                     public source checkout
  .local/config/local.json    ignored registry and machine settings
private-workspace/            never part of platform Git
  inventory/                  collection identities and hashes
  projects/project-001/
    AGENTS.md                 private scope and checkpoint decisions
    project.json              API contract and verified source identity
    project.py                private executable entry point
    environment.json          optional private bootstrap configuration
    src/                      extraction/rendering/build adapters
    data/                     encodings, pointers, translations and recipes
    docs/                     research, debugging evidence and progress
    tests/                    project regression coverage
    roms/                     immutable originals or external references
    output/                   generated ROMs, patches, previews and reports
    saves/                    testing saves/states
    checkpoints/              approved/rejected identities and evidence
    archive/                  frozen legacy recipes, tools, assets and notes
```

Existing projects may retain historical subdirectory names to preserve working recipes. Record that mapping privately. Ignored `.local/projects/` is an alternative, but external folders reduce accidental source-folder exports. Neither location is encryption.

## API version 1

`ProjectContext.load(path)` reads JSON as data only. It validates `schema_version: 1`, `platform_api: 1`, a local `project_id`, a source path and full lowercase SHA-256, named relative `resources`, and a relative `output_directory`. Optional `data` is project-owned metadata that the platform does not execute. See [the manifest template](../templates/project/project.example.json).

Paths resolve against the manifest directory, regardless of current working directory. Originals may be external read-only paths. Resources/outputs must stay within the project root; traversal and symlink escapes are rejected. Output cannot overlap originals, resources or the project root. `read_source()` verifies the pinned hash; `resource(name)` resolves a resource without executing it.

`OutputPolicy(root, inputs=...)` protects declared inputs, rejects output escapes and writes exclusively through `write_new(path, bytes)`. Relative destinations resolve against the output root. Existing files, including hard links, are refused. These checks protect ordinary local use, not hostile processes racing filesystem changes; this is not an untrusted-code sandbox.

| Module | Responsibility |
|---|---|
| `patchquest.core.edits` | Hash-pinned reads, equal-length expected-byte edits, overlap/bounds checks and explicit one-byte extraction tables |
| `patchquest.core.packing` | Deterministic placement of indivisible blobs in caller-verified intervals; explicit failure on insufficient capacity or search budget |
| `patchquest.consoles.snes.inspection` | File/payload hashes, header candidates, mapping heuristics and mirrored checksums |
| `patchquest.consoles.snes.checksum` | Checksum/complement updates at an explicitly validated header; no automatic mapping choice |
| `patchquest.consoles.snes.tiles` | SNES tile planes and pixel previews |
| `patchquest.consoles.cpu65816` | Linear disassembly with limited tracked M/X state; not control-flow analysis |
| `patchquest.patches.bps` | Deterministic SourceRead/TargetRead encoding and verification of that subset |
| `patchquest.typography.font` | Quest Pixel loading, rasterization, bitplane checks and specimens |
| `patchquest.typography.layout` | Metrics, wrapping, padding/alignment, substitutions and retained opaque controls |

No shared API guesses compression, pointer reachability, free space, Japanese encoding or game control semantics. Private adapters own those. Host typography does not implement a console runtime renderer.

## Running and evolving projects

Use an explicit `--platform` checkout path from the private runner, as [the template](../templates/project/project.py) demonstrates. No install or plugin loader is required. Optional environment.json belongs to the private bootstrap, not an automatically executed platform setting. The platform registry is a discovery aid, not authorization to build every project.

`doctor` reports configuration counts and emulator availability. `project-check` checks an explicit manifest and its source hash. Neither imports private Python code or launches an emulator.

During migration:

1. Capture a file/hash ledger, all inputs/checkpoints, research, old tools/font metadata and staged-only versions in a private archive. Preserve rejected work and Git objects.
2. Verify recipe reproduction before refactoring, comparing ROM **and BPS bytes**.
3. Separate shared APIs from project parameters. Private compatibility adapters may retain historical imports/paths; do not publish game-named aliases.
4. Rerun retained private tests and exact checkpoint builds. Distinguish source-recipe rebuilding from archived-patch reconstruction. **Stop and ask if a checkpoint cannot be reproduced.**
5. Retire old active paths only after checked private copies and successful builds. Annotate obsolete commands; do not delete useful research.
6. Test an exported public tree without private data. Audit candidate/index/export content and Git refs/objects. Never publish the archive or .git.

A migration does not alter translation scope or testing approval. Identical ROM bytes establish unchanged behavior, not previously unperformed emulator or hardware tests.

## Translation state contract

[Studio/state](translation-studio.md) extends the existing manifest without
changing API version 1: `.patchquest/` inside the explicit private project owns
the SQLite revision store, derived memory, snapshots and evidence copies. It
must be separate from originals, protected resources and build outputs. Private
runners import the state API and consume immutable snapshots; the platform
never imports a private adapter or interprets its game-specific build binding.
No ROM is needed for state browsing. Versioned records are authoritative for
new snapshot builds; legacy records remain frozen for old recipe reproduction.

## Promotion policy

Studio job orchestration follows the same direction: a private launcher imports
`BuildWorker`, registers its own validated callback and starts the public HTTP UI.
The browser queues only an advertised build mode; it cannot choose code or paths.
Jobs freeze current revisions transactionally, serialize builds, report stages
and preserve failure/interruption evidence. Screenshot bytes and revisioned
associations remain under the private `.patchquest/` directory. See the canonical
[Studio guide](translation-studio.md) for the callback contract and recovery.

Classify findings as platform, private project, or both using [the information table](local-workspace.md#information-classification-table). Promote independently generalized algorithms/invariants with synthetic or licensed tests. Keep actual game evidence, parameters, source patterns, scripts, hooks and progress private. Removing titles does not anonymize distinctive code or fixtures. Private notes may link to public techniques; public documents must not point back to real private projects.
