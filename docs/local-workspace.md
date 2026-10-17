# The private local workspace

.local/ supplies environment-specific configuration and durable working knowledge to developers and AI coding agents. It is Git-ignored because tool paths, project registries, testing details and evidence origins can disclose private information. It is not encrypted storage, a secrets vault or a replacement for public documentation. Filesystem copies/backups can include ignored files.

Patch Quest DX is the public platform. Individual translations are private projects, preferably outside the checkout. Their identities, hashes, research, encodings, addresses, scripts, translations, hooks, recipes, checkpoints and progress stay private. The boundary applies to code, fixtures, generated reports, screenshots and Git history as well as prose.

## Recommended structure

```text
.local/
  config/local.json           supported settings and project registry
  notes/README.md             discovery index linking canonical records
  notes/tools.md              installed versions and verified capabilities
  notes/environment.md        platform quirks and reliable workarounds
  notes/testing.md            local emulator/debugger/hardware procedures
  research/                  evidence origins and durable local findings
  logs/                      raw experiments, audits and diagnostics
  projects/                  optional projects; external folders preferred
```

Keep game evidence in the external project's docs/, data/, tests/, output/ and archive/ rather than duplicating it here. Local registry/index entries may point there privately. See [the architecture](project-architecture.md) and [project starter](../templates/project/README.md).

## Information classification table

| Information or discovery | Canonical home | Public counterpart |
|---|---|---|
| Active translation revisions, human corrections, contextual memory and issues | External private project `.patchquest/` state store | Generic schema/API documentation and invented tests |
| Immutable translation snapshots and private adapter build reports | External private project snapshots/output/checkpoint records | Snapshot protocol and safe pipeline integration guide |
| Agent instruction discovery conventions | Canonical public AGENTS.md/skills and thin agent adapters | [Compatibility guide](agent-compatibility.md); installed-client quirks stay local |
| Emulator executable location/version | Local tools note; supported executable path in local config | Template fields and version-check procedure; fictional ../toolkit/emulator/emulator.exe |
| Debugger launch settings and game breakpoints | Local environment notes for settings; private project for breakpoints | General debugger workflow without machine values or game addresses |
| ROM collection path/inventory | External private inventory/project | Immutable-input setup instructions without titles or hashes |
| Game revision/header assessment and checkpoint hashes | Private manifest/checkpoint records | Generic hash verification and console header definitions |
| Character encoding, pointer table, compression parameters or discovered routine | Private project data/research/code | Independently generalized decoder/validator with freshly invented fixtures |
| Extracted Japanese, translated lines/names, glossary decisions | Private project language data/notes | Shared localization policy and clearly contextual vocabulary examples |
| Quest Pixel artwork and Unicode metrics | Public assets/fonts/quest-pixel/ with provenance | Editable shared font/profiles; public asset hashes are valid public identities |
| Font dump, ROM glyph codes, palettes or allocation | Private project assets/data | Generic tile/layout/bounds technique using shared or synthetic artwork |
| Renderer hook, VRAM allocation, original trace or regression | Private project code/tests/research | General capacity/lifetime invariant with independent tests; title removal is insufficient |
| Console-defined register/header behavior | Public console adapter/docs after verification | Standard console addresses are public facts, not private game signatures |
| Reusable reverse-engineering technique | Public workflow if verified and independently described | How to validate pointer hypotheses without copying the actual table/trace |
| Compiler/assembler/graphics utility locations and versions | Local tools note | Supported interfaces and optional prerequisites, not automatic installation |
| Machine-specific failure/workaround | Local environment note or durable finding | General cause/workaround when reusable; raw logs and paths remain private |
| Local save directories/hotkeys/testing steps | Local testing note; game routes/results in private project | Generic cold-boot/SRAM checklist without screenshots or project progress |
| Hardware/flashcart capabilities and firmware | Private testing/tool notes | How to document hardware tests, not claims about the owner's equipment |
| Preferred output directory | Private project manifest/output policy | Generic contract without a selected private project |
| Reusable architectural decision | Public design record with independent evidence | Private project links to it and retains its adaptation/evidence |
| Mixed general and game-specific debugging discovery | Split public technique and private evidence | Public side never links back to an actual private project |
| Temporary experiment/unresolved guess | Private logs; durable issue only if decision-relevant | Do not convert speculation into permanent public instructions |
| Credentials/access tokens | External credential manager | Document mechanisms if needed; never plaintext credentials in .local/ |
| Migration ledger, raw Git/object audit or private fingerprints | Local logs or external archive | Generic audit procedures/limits, no actual private history or filenames |

Not every hexadecimal value is private: console definitions and intentionally public font hashes differ from game fingerprints. Conversely, replacing a title or filename does not anonymize distinctive code, byte patterns, translations or assets.

## Fresh installation

1. Check Python 3.10+ and Git, run doctor and public tests from [local setup](local-setup.md). No local config or ROM is required.
2. Copy [the config example](../config/local.example.json) into .local/config/local.json only when absent. Never move originals just to satisfy settings; no game is selected by default.
3. Create the local note index and useful notes. Record observed tool versions, how they were checked and applicability. Mark missing debugger/emulator/hardware capabilities unavailable or unknown.
4. Copy the private project template to external storage. Supply its pinned source reference, research and runner there. Optionally register its manifest locally.
5. Run project-check on the explicit manifest. It checks source/schema only. Use the private runner for authorized work and retain approved/rejected checkpoints.
6. Check `git check-ignore .local/config/local.json` and `git ls-files`: ignores do not protect already tracked files. Setup does not authorize staging or publication.

Fictional configuration:

```json
{
  "schema_version": 2,
  "projects": {"sample": "../private-workspace/projects/sample/project.json"},
  "emulators": {"snes9x": "../toolkit/emulators/snes9x.exe", "mesen": null},
  "privacy_terms": ["fictional-project-alias"]
}
```

These values are examples, not evidence of an installed tool/project. Registry/emulator paths are relative to the platform root unless absolute. Human-readable notes do not define additional supported settings. See [local setup](local-setup.md) for schema validation and migration.

## Templates and agent discovery

Use [tool inventory](templates/local-tool-inventory.example.md), [environment](templates/local-environment.example.md), [testing](templates/local-testing.example.md) and [durable finding](templates/local-finding.example.md) templates. Copy only useful records privately; do not create empty paperwork for every capability.

An agent first reads public AGENTS.md and the relevant skill/architecture. Then it checks for .local/notes/README.md and local configuration, following only task-relevant links. Read the chosen private project's instructions before touching its data. Use explicit paths and the shared loader, not a second configuration system. Missing private files are normal. Do not recursively dump the local workspace, paste private logs into public reports or inventory unrelated ROM collections.

Useful local information includes installed emulators/versions; debugger settings; immutable collection references; compilers/assemblers and graphics tools; platform-specific quoting/path details; reliable workarounds; local testing procedures, save locations and output preferences; hardware testing capabilities; and machine-specific debugging findings. Use verified, user-reported, unknown and superseded statuses with scope/limits.

Collect only what helps the task, not personal biography, accounts or plaintext credentials. A tool path does not authorize installation, launching an interactive session or operating hardware. A stored test procedure does not mean a test has run. Recheck stale capabilities when relevant and reuse established findings across sessions.

## Permanent maintenance workflow

When verified discoveries affect setup, configuration, debugging or workflows:

1. Classify as platform, private project, or both using the table. Keep source evidence private when project-derived.
2. Update the canonical record and index only where needed. Public documentation describes general techniques; private records supply actual values/adaptation/evidence. Link rather than duplicate procedures.
3. Synchronize implemented settings, defaults/validation, tests, public examples and migration/setup instructions. Do not document speculative settings as supported or overwrite private values from a template.
4. Separate verified observations, user reports, materially unresolved hypotheses and superseded findings. Include applicability and limits. Temporary experiments remain in private logs.
5. Inspect candidates, staged content and intended exports before handoff. Run audits with local fingerprints and review their limits. Never automatically publish private folders.

Keep useful superseded records, original backups and known-good checkpoints. Do not delete evidence or Git snapshots to make an audit appear clean. A failed checkpoint reproduction during migration requires stopping and asking the owner. Review backup/export contents because Git ignores do not govern filesystem archives.

This discipline preserves reusable public knowledge and private working context across sessions. It does not authorize new translation scope, downloads, commits or publication.

Studio setup and backup procedures are documented in [Translation Studio](translation-studio.md). Keep the platform registry in `.local/`; the selected project's `.patchquest/` owns translation state. Never copy real databases, snapshots, session URLs or registered images into public examples or reports.

Record a verified private Studio launcher and its build capabilities in the
project's setup notes; the generic launcher alone does not register a pipeline.
Keep worker diagnostics, uploaded screenshots, association histories and actual
artifact locations private. Public examples describe this contract using invented
data. Do not store per-launch browser tokens in configuration or shared reports.

## Agent coordination knowledge

Canonical collaboration policy lives in `AGENTS.md`, the shared skills and
[the coordination contract](agent-collaboration.md). Agent session IDs, task
claims, handoffs, translation memory and build snapshots live in the selected
private project's `.patchquest/`, not duplicated in each provider's memory.
Keep installed client versions, login/permission availability (never secrets),
local runtime probe results and troubleshooting in private environment notes.
A useful record names the tested version, date, synthetic or private scope,
verified operations, exact failure category and remaining limits. Do not store
access tokens or complete provider environment dumps. Promote a reproducible
general workaround into public documentation with invented paths/data.
