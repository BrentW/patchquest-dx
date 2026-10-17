# Patch Quest DX

Reusable tools for AI-assisted ROM translation, with private translation projects kept separate from the public platform. Python 3.10+ and Git are sufficient for the supplied workflows; there are no required third-party Python packages or automatic downloads.

- [Fresh installation and commands](docs/local-setup.md)
- [Local workspace and information classification](docs/local-workspace.md)
- [Private project contract and migration](docs/project-architecture.md)
- [Local Translation Studio and shared state APIs](docs/translation-studio.md)
- [Studio roadmap](docs/studio-roadmap.md) and [Codex/Claude Code compatibility](docs/agent-compatibility.md)
- [Localization](LOCALIZATION.md), [typography](TYPOGRAPHY.md), and [agent instructions](AGENTS.md)
- [Publication readiness](docs/publication-readiness.md)
- [License scope](LICENSE-SCOPE.md), [licensing conventions](docs/licensing.md), and [third-party notices](THIRD_PARTY_NOTICES.md)

Public maintainer: **BrentW**. Platform code, tools, tests, examples and documentation use **Apache-2.0**; designated **Quest Pixel font assets use CC BY 3.0 Unported**, preserving applicable upstream terms. Maintainer credit is not a claim of sole authorship or exclusive ownership. The exact scope and complete terms are linked above.

## Quick start

From the platform checkout:

```powershell
python tools/patchquest.py doctor
python -B -m unittest discover -s tests -p "test_*.py" -v
python examples/synthetic-project/project.py --platform . --workspace .local/projects/synthetic-demo
```

Choose a fresh workspace for each example run. The sample generates fictional bytes, a guarded edit, a checksum, a BPS patch and a typography preview. **It is not a playable ROM.** No original ROM or private project is needed. [Example provenance](examples/synthetic-project/README.md) describes exactly what it demonstrates.

For a real private project, copy [templates/project](templates/project/README.md) to an external directory, supply verified inputs and implement its game-specific adapter there. The platform never loads a private project's Python code. Consult that project's instructions before building or testing.

## Public source layout

The optional [Translation Studio](docs/translation-studio.md) runs locally with
the Python standard library. It provides a searchable editor, protected human
corrections, revision history, contextual translation memory, progress, issues
and build reports. Use `python tools/patchquest.py studio PATH/TO/project.json`
for an explicit private project. Its private worker launcher enables **Build test
ROM** from saved revisions. Upload screenshots to issues and retain provisional
or confirmed associations with history. Agents use the same APIs without the browser.

```text
src/patchquest/core/          explicit project paths, guarded edits and extraction
src/patchquest/consoles/      SNES inspection/checksum/tiles and linear 65816 disassembly
src/patchquest/patches/       deterministic BPS subset
src/patchquest/typography/    integer pixel artwork, metrics and block layout
assets/fonts/quest-pixel/    reusable source artwork and neutral metrics
examples/                    independently invented demonstration project
templates/project/          private-project starter (copy outside this checkout)
tests/                       synthetic and public-font regressions
docs/                        public setup, architecture and workflows
.agents/skills/              reusable agent workflow
.local/                      ignored machine configuration and local knowledge
```

Originals, derivatives, saves, project identities, hashes and reverse-engineering research belong in private projects. No ROMs or extracted game assets are supplied. Tools do not infer character encoding or prove a game's safety from header heuristics. BPS decoding supports the SourceRead/TargetRead subset emitted by this encoder; independent patch-tool interoperability is a separate pre-distribution check. Typography previews do not establish runtime behavior.

Keep source artwork and known-good checkpoints unchanged, use fresh outputs and preserve expected-byte/source-hash checks. Test actual navigation, highlighted selections, transitions and saves in an emulator; hardware support requires hardware testing. Installation, Git initialization, commits and publishing require separate authorization. Licensing preparation does not authorize publication or grant rights in a commercial game's contents.

For shared Codex/Astra and Claude Code work, see [agent compatibility](docs/agent-compatibility.md)
and [the coordination workflow](docs/agent-collaboration.md). Both clients use
one canonical policy, shared private memory, scoped task leases and the same
build interfaces. Studio's **Agents & work** view shows progress and handoffs;
provider execution remains explicitly controlled by the developer.
