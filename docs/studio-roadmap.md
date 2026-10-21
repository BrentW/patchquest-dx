# Translation Studio roadmap

Granular [exceptions and source classifications](translation-exceptions.md) now
extend shared issue history and Studio filters/details. Legacy notes migrate
without rewriting translations. Automatic semantic content detection and live
provider processing are not implemented; agents/users supply contextual evidence.

Automatic by default. Human correction by exception. Translation approval is
not a prerequisite for a build; technical validation and checkpoint approval
remain separate.

| Milestone | Dependencies | Scope | Status |
|---|---|---|---|
| 1. Translation memory and state | Existing project contract | Versioned records, correction precedence, concurrency, history, snapshots, private migration | Implemented; synthetic and private integration tests |
| 2. Local Studio MVP | Milestone 1 | Editor, memory/glossary, persistent live progress, issues, build history | Implemented; HTTP and browser regression tests |
| Early agent compatibility | Canonical instructions and skills | Codex discovery, thin Claude adapters, drift checks | Implemented; documented conventions and portable file checks, not end-to-end provider runtime certification |
| 3. Expanded workflows | Validated private snapshot consumers | Screenshot uploads/association history and capability-based full build jobs | Implemented; selective builds and automatic screenshot matching remain deferred |
| 4. Advanced coordination | Transactional state and snapshots | Shared agent context, scoped leases, dependencies, scheduling, handoffs and Studio status | Implemented; synthetic races and provider-independent interfaces; live runtime evidence is installation-specific |
| Narrative context foundation | Canonical localization policy and shared state | Evidence-linked work tone, character/scene guides, shared read discovery and revision-bound sample reviews | Implemented; synthetic API tests and a separately private editorial sample; no automatic literary-quality certification |
| Runtime inspection | Explicit emulator capabilities and private scenarios | Actual captures, observed assertions and exact build/revision evidence | Bounded scenarios, software libretro adapter and Studio evidence implemented; installed-emulator results remain separate private evidence |
| Verification coverage and readiness | Existing runtime reports, snapshots and progress | Explicit area plans, revisioned assessments, stale/build binding, private status summaries and an on-demand Studio view | Implemented foundation; synthetic validation, no automatic full-game coverage or release approval |

The [verification/readiness contract](verification-readiness.md) defines explicit
coverage plans, build-bound assessments and private status summaries. Existing
issues, attachments and immutable build APIs remain authoritative.

Preserve approved outputs, historical recipes and font artwork during migration.
Public tests use invented data; private integrations retain actual language,
source identities, evidence and reproduction results externally. Game translation
scope and scheduling are authorized and recorded in each private project.

Studio can upload private screenshots, retain provisional/corrected associations,
and queue full builds through an explicitly registered private worker. It can
freeze build inputs and display stages, failures and result locations. It does
not infer text associations, execute browser-provided commands or run selective builds.
Snapshot consumers remain explicit private adapters; unsupported edits fail
technical validation instead of being omitted. Memory uses lexical/context
scoring; no embedding service, provider SDK or separate translation engine is
required. Concurrent updates use revisions; translation-work scheduling and leases now
use the [shared coordination contract](agent-collaboration.md). Provider launching,
automatic model routing and filesystem merging remain outside this milestone.

Run the standard public test suite and `python tools/sync_agent_adapters.py --check`.
For optional browser regression, use `node tools/studio_browser_check.cjs` with
an already installed Playwright module/browser. `PLAYWRIGHT_MODULE`,
`BROWSER_EXECUTABLE`, and `PYTHON` can select existing tools; `STUDIO_SCREENSHOT`
can save private QA output. The check never downloads a browser. Python/SQLite
and a normal browser are sufficient to use Studio; Node and Playwright are only
development test tools. See [launch and recovery](translation-studio.md).
