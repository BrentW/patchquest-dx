# Patch Quest DX

**A local workspace for thoughtful, reproducible ROM translation.**

Edit translations in your browser, carry human corrections into reproducible
builds, inspect visual evidence, and coordinate coding agents around shared
project state. Patch Quest DX supplies reusable tools and workflows; each game's
text, ROMs, renderer adaptations and research live in a separate private project.

[Try the Studio](#try-the-studio) · [Feature tour](#feature-tour) ·
[Developer tools](#developer-tools) · [Documentation](#documentation) ·
[Licensing](#licensing)

![Translation Studio with a fictional catalogue, progress counters and a protected human correction](docs/images/studio/studio-overview.png)

*Actual Studio screenshots use the invented Lantern Harbor demo. No commercial
game text, ROM graphics or private project data is shown. Its build uses fictional
bytes; its runtime example uses a synthetic grid.
[Screenshot provenance](docs/images/studio/README.md).*

**Availability:** editing, memory, browser builds, screenshot issues, agent
coordination and dialogue layout are included in this checkout. The runtime
inspection and narrative-context sections preview work awaiting a separate code
review and publication. Screenshots were captured from the development workspace;
their appearance may differ from this checkout.

## Try the Studio

Use **Python 3.10+ with SQLite** and a browser. Basic workflows need no third-party
Python packages or provider accounts, and download nothing automatically. Git is
used for source development and publication audits.

From the platform checkout:

```sh
python tools/patchquest.py doctor
python examples/studio-demo.py --workspace .local/projects/studio-demo
python tools/patchquest.py studio .local/projects/studio-demo/project.json --port 0
```

Open the private session URL printed in the terminal. Leave the terminal running;
Ctrl+C stops the server. The demo needs a fresh destination initially. Later, rerun
only the Studio command to reopen saved data. It starts with a small fictional
catalogue; the screenshots show additional invented examples.

Studio binds to loopback and requires a per-session token. It does not contact an
AI service. Keep the launch URL private and the server on your machine. The demo
has no playable ROM or build worker; real builds use your private project's
explicit validated worker launcher.

[Setup guide](docs/local-setup.md) · [Studio guide](docs/translation-studio.md) ·
[Private project starter](templates/project/README.md)

## Feature tour

### Edit with context and preserve human judgment

Search source text, English or record IDs; filter by scene, speaker, category and
status. Inspect controls, context, build bindings and revision history alongside
the wording. Saved human corrections are protected: agents can offer alternatives
as proposals, and stale writes are rejected. Restoring earlier wording creates a
new revision while retaining history.

Progress distinguishes discovery, translation, uncertainty, insertion, automated
tests, emulator checks and hardware checks. Counts describe the catalogue; they
do not claim that every text path in a game has been found or tested.

### Translation memory and terminology

Reuse relevant wording from shared history and the contextual glossary.
Suggestions distinguish current, historical and human-corrected entries.
**Use as draft** lets you compare a suggestion before saving; it does not rewrite
related records. Memory uses lexical and context scoring, with no embedding service.

![Memory panel with human-corrected wording, glossary terminology, historical entries and Use as draft controls](docs/images/studio/translation-memory.png)

### Build from saved corrections

**Build test ROM** captures an immutable snapshot and queues a full build through
an explicitly registered private pipeline. Follow stages, retained failures and
result locations in the browser. Duplicate requests and concurrent builds are
guarded; later edits belong to a later snapshot. Unsaved drafts are excluded.

The private adapter validates encoding, controls, layout, allocation, checksums
and patch reconstruction before reporting success. Technical success does not
approve a checkpoint or certify gameplay. **Freeze current build inputs** saves
a snapshot without starting a build.

![Build controls and a completed synthetic job, with frozen inputs and artifact-location details](docs/images/studio/browser-builds.png)

*This exercises the real job workflow with a synthetic callback. “Test ROM ready”
is the standard job label; this demo produces invented binary data and a patch,
not a playable game.*

### Report issues with screenshots

Track wording, voice, layout and gameplay concerns against records, scenes and
builds. Upload PNG/JPEG evidence, retain provisional associations, and correct
links with revision checks and history. Images stay in the private project;
automatic OCR and screenshot-to-text matching are not implemented.

![Issues view with fictional concerns, an attached synthetic Studio screenshot and association-history controls](docs/images/studio/screenshot-issues.png)

### Inspect runtime evidence — development preview

This integration is not included in the current checkout. The development
preview demonstrates the following workflow:

Bounded scenarios can drive an explicitly configured software libretro core,
capture frames and check named pixel expectations. Reports bind observations to
the build, translation revisions, scenario and emulator configuration. Studio
shows captures, assertions and whether associated wording has changed.

Static checks, actual emulator evidence and human acceptance remain distinct.
The adapter supports frame-stepped joypad input, native states and explicitly
pinned SRAM transfer. Native execution starts through the local CLI; no browser
command launches a core. No emulator is bundled or downloaded.

![Runtime card with a labelled synthetic test, assertion details and two invented selection-grid captures](docs/images/studio/runtime-reports.png)

*This public example demonstrates report plumbing with a synthetic grid. It is
not evidence of emulator execution or game compatibility.*

Runtime inspection code and its detailed guide will be published together after
their separate review.

### Coordinate Codex and Claude Code

Agents discover one canonical instruction set, reusable skills, private memory
and build interfaces. Scoped claims, leases, dependencies and
revision checks support sequential handoffs and concurrent independent work.
Human corrections retain precedence.

**Agents & work** exposes sessions, progress, scope and durable handoffs. Provider
labels are reported metadata; Studio does not launch providers, route models
automatically or merge conflicting filesystem edits.

![Synthetic agent sessions, a completed handoff, a leased task and queued dependent work](docs/images/studio/agent-collaboration.png)

[Agent compatibility](docs/agent-compatibility.md) ·
[Coordination contract](docs/agent-collaboration.md)

## Typography and narrative quality

Quest Pixel supplies reusable pixel artwork, compact metrics and proportional
measurement. The dialogue planner uses actual pixel dimensions and explicit
window capabilities: preserve fitting text, make a safe small adjustment, wrap,
use verified native scrolling, resize or paginate where supported, and report
unresolved overflow. It preserves saved wording and requires private renderer
integration; a plan alone does not change a ROM.

Localization defaults favor Title Case menus and sentence-case dialogue, guided
by tone and context. The **narrative-context development preview**, awaiting
separate publication, records work tone, scene changes,
character voice, emotional state and intent, separating evidence from
interpretation. Versioned private guides are discoverable by every agent;
context reviews do not automatically rewrite translations.

[Typography](TYPOGRAPHY.md) · [Dialogue layout](docs/dialogue-layout.md) ·
[Localization](LOCALIZATION.md)

## Developer tools

Python APIs and JSON CLI operations support headless work alongside Studio:

| Area | Available tools |
|---|---|
| Persistent state | SQLite revisions, protected corrections, proposals, glossary, issues, snapshots and online backups |
| ROM primitives | Guarded extraction/insertion, expected-byte edits, explicit output policy and source-identity checks |
| SNES support | Header/checksum inspection, planar tiles and linear 65816 disassembly |
| Patches | Deterministic BPS creation and strict SourceRead/TargetRead subset decoding |
| Typography | Glyph data, proportional measurement, block layout and capability-gated overflow planning |
| Verification | Synthetic public tests, revision-bound build reports and privacy/history audits; runtime adapters remain a development preview |

```sh
python -X utf8 -B -m unittest discover -s tests -p "test_*.py" -v
python tools/sync_agent_adapters.py --check
python examples/synthetic-project/project.py --platform . --workspace .local/projects/synthetic-demo
```

UTF-8 mode keeps test text handling consistent across platforms, including
Windows installations with a different default encoding.

Choose a fresh destination for the synthetic build example. It creates invented
bytes, a guarded edit, a checksum, a patch and a typography preview; it is not a
playable ROM. [Example scope](examples/synthetic-project/README.md).

For real work, copy the [project starter](templates/project/README.md) outside this
checkout. Your adapter supplies verified encodings, renderer hooks, window
policies and build recipes. Public code does not discover or import private game
modules. See the [architecture contract](docs/project-architecture.md).

## Current boundaries

- Studio is a single-user local application. Browser access is token-protected;
  SQLite data is not encrypted, and local roles are not an OS security boundary.
- Builds require an explicit worker. Selective builds, cancellation, automatic
  screenshot matching and provider orchestration remain deferred. Heavy build
  validation can reduce server responsiveness; latency depends on the pipeline.
- The runtime development preview covers named scenarios and installed capabilities. Audio
  analysis, desktop debugger control and hardware certification are not provided.
  State replay does not establish cold-boot or battery-save compatibility.
- BPS supports the encoder's SourceRead/TargetRead subset. Independent patcher
  interoperability and patch contents need review before distribution; a patch
  format alone does not exclude original-game data.
- Header heuristics, passing pixel checks and a populated catalogue do not prove
  a safe or complete translation. Preserve checkpoints and inspect actual game
  navigation, highlights, text progression, saves and timing.

[Implemented milestones and deferred work](docs/studio-roadmap.md)

## Documentation

| Start here | Go deeper |
|---|---|
| [Fresh installation](docs/local-setup.md) | [Local workspace and classification](docs/local-workspace.md) |
| [Translation Studio](docs/translation-studio.md) | [Project architecture and migration](docs/project-architecture.md) |
| [Agent instructions](AGENTS.md) | [SNES skill](.agents/skills/snes-translation/SKILL.md) and [collaboration skill](.agents/skills/translation-collaboration/SKILL.md) |
| [Dialogue layout](docs/dialogue-layout.md) | [Typography](TYPOGRAPHY.md) |
| [Localization](LOCALIZATION.md) | [Publication readiness](docs/publication-readiness.md) |

Keep original ROMs, derivatives, saves, translations and reverse-engineering
evidence in external private projects. Ignored `.local/` holds machine settings
and working knowledge; reusable techniques and public-safe examples belong in
the platform. No ROMs or extracted game assets are supplied here.

## Licensing

Public maintainer: **BrentW**.

Platform code, tools, tests, examples and documentation use **Apache-2.0**.
Designated **Quest Pixel artwork/data files use CC BY 3.0 Unported**, preserving
applicable upstream terms. Generic font-processing code remains Apache-2.0.
Maintainer credit is not a claim of sole authorship or exclusive rights.

[Apache license](LICENSE) · [File-level scope](LICENSE-SCOPE.md) ·
[Quest Pixel attribution](assets/fonts/quest-pixel/ATTRIBUTION.md) ·
[CC BY 3.0 terms](assets/fonts/quest-pixel/LICENSE-CC-BY-3.0.txt) ·
[Third-party notices](THIRD_PARTY_NOTICES.md) · [Licensing conventions](docs/licensing.md)

These licenses do not grant rights in a commercial game's contents. Additional
tool installation, commits and publication remain separately controlled by the
developer; a successful build or audit does not authorize release.
