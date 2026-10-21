---
name: game-translation-team
description: Apply focused Patch Quest DX roles for project management, text and glyph decoding, translation, ROM and layout engineering, or game testing. Use when assigning a bounded translation-project task or handing work between these specialties. Uses existing project state and collaboration tools; does not create or launch agents.
---

# Game translation team

Use only the role needed for the current task. These are reusable working guides;
one agent may perform several roles sequentially. A role name does not establish
expertise, grant permissions or require a separate model or persistent chat.

Read root [AGENTS.md](../../../AGENTS.md), the selected project's instructions
from `agent-context`, and the [collaboration skill](../translation-collaboration/SKILL.md).
Then read the chosen guide and the shared [assignment and handoff](references/assignment-and-handoff.md).
Do not load every reference for a single-role task.

| Role | Use when | Deliverable |
| --- | --- | --- |
| [Project Manager](references/project-manager.md) | A bounded batch needs ownership, sequencing or a closeout | Assignment, dependency decisions and concise status |
| [Text & Encoding Specialist](references/text-encoding.md) | Source text, glyphs or controls are missing or uncertain | Traceable catalog/decoding evidence and explicit unknowns |
| [Translator](references/translator.md) | Decoded text needs contextual English or an editorial review | Revisioned translations or inactive review proposals |
| [ROM & Layout Engineer](references/rom-layout.md) | Text needs safe insertion or a display repair | Reproducible test build, layout findings and test cases |
| [Game Tester](references/game-tester.md) | A build needs actual gameplay or renderer verification | Build-bound observations and actionable failures |

## Keep the assignment bounded

Start with the user's existing scope, records/scenarios, acceptance criteria and
stop condition. Fill missing routine details from evidence; ask only when a
material decision cannot be made within that scope. Record unrelated discoveries
as deferred findings, without opening tickets or extending the task automatically.

Reuse the existing task queue and revisioned state. Claim before writing; use the
actual returned session, fence and revisions. Delegate only when authorized and
only for independently owned scopes. Shared encoding tables, guides, adapters,
emulators and output destinations need agreed resource keys and file ownership.
Transfer overlapping work explicitly; do not race another owner.

Typical handoff: decoded records -> translations -> build -> test report.
Enter at the appropriate step, reuse valid evidence, and return defects to their
owner. A small label correction need not repeat extraction or a full playthrough.
Completion means the assigned deliverable is ready, not that the whole game is
translated, tested or approved for release.

Keep game evidence and concrete assignments private. Follow existing correction,
snapshot, privacy and provider safeguards. Roles do not authorize paid calls,
installation, shared-server restarts, checkpoint approval or publication.
