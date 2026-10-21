# Start a game translation

Start one agent in the Patch Quest DX checkout, give it the Project Manager
role, and supply the exact original game-file path or an existing private project
manifest. Include the game title, platform if known, and target language. The
agent can investigate the encoding and build requirements; you do not need to
know them first.

The default first milestone is one small menu and one short dialogue passage
working in a reproducible test build. This checks the path from source text to
actual rendering before a larger translation batch. If the game lacks a menu or
dialogue, use an equivalent small text sample. An existing project keeps its
saved work and current milestone instead of starting over.

## Use the shortcut

The repository includes the [translate-game skill](../.agents/skills/translate-game/SKILL.md).
Open the platform checkout so its project skills are discoverable. A sibling
private-project folder alone does not automatically load the platform skills;
in that case explicitly provide the canonical skill path as well.

- **Codex:** mention `$translate-game`, or ask to use the `translate-game` skill.
  In clients with a skill picker, select it there.
- **Claude Code:** use `/translate-game`; the generated adapter reads the same
  canonical instructions.
- **Other agents:** explicitly ask them to read the canonical skill and root
  `AGENTS.md`. Native shortcut support depends on the host application.

For example, replace the placeholders before sending:

```text
$translate-game
Game file: [full path to the original ROM or disk image]
Platform: [if known]
Target language: English
Start with the small first milestone, then report the result.
```

In Claude Code, replace the first line with `/translate-game`. Invoking the skill authorizes bounded specialist delegation within the selected
project and milestone; no separate permission is needed. The manager performs
roles sequentially when sub-agents are unavailable, restricted, or not useful,
or when the user asks to work alone. This is an
instruction-based workflow, not a new command in the Patch Quest CLI or Studio.
It does not automatically configure LM Studio, choose a model, install tools,
or start persistent agent chats.

Invocation and discovery conventions:
[OpenAI skills](https://learn.chatgpt.com/docs/build-skills) and
[Claude Code skills](https://code.claude.com/docs/en/skills).
See [agent compatibility](agent-compatibility.md) for the repository adapters
and the distinction between static discovery checks and live client verification.

## Full starter prompt

Use this when you want an explicit assignment without relying on a shortcut.
Replace the placeholders and adjust the milestone or delegation line to suit
your request. The examples here are templates, not authorization to act on a
game merely because an agent reads this document.

```text
Act as the Project Manager for a new Patch Quest DX translation project.

Game: [game title]
Platform: [console or computer, if known]
Original game file: [full file path]
Target language: English

Follow the repository's AGENTS.md and game-translation-team skill. Check whether
this game already has a private project before creating one. Reuse any existing
state, ownership and milestone rather than resetting its progress.

Our overall objective is a complete, playable English translation. For the first
milestone, establish the private project and produce a reproducible test build
containing one small menu and a short dialogue passage, or an equivalent small
text sample when those do not exist.

Inspect the original without modifying it. Investigate the actual encoding,
glyphs, control codes, text storage and renderer rather than assuming their
format. Keep game-specific data and evidence private, and register the project
with the existing shared Studio using its established workflow. Coordinate any
required refresh with its owner, preserving unsaved drafts and active jobs.

You may delegate bounded tasks to specialist agents where useful. Give each
agent clear ownership and prerequisites, and coordinate their handoffs.
Preserve human corrections and existing artifacts.

Validate the sample through the actual game renderer where available. Clearly
distinguish static checks from emulator observations and anything still requiring
my testing. If a capability is missing, record the concrete blocker and continue
independent work; do not claim an untested build works in-game.

Keep the scope limited to this first milestone. Report the test build, findings,
blockers and recommended next batch when finished. Do not automatically begin
bulk translation or add more roadmap tickets.

Do not install tools, make paid-provider calls, commit, push, publish, or approve
checkpoints without my authorization. Follow the configured provider safeguards.
```

## Roles and handoffs

The [game translation team](../.agents/skills/game-translation-team/SKILL.md)
provides the detailed guides; the manager uses only the roles needed.

| Role | First-milestone responsibility |
| --- | --- |
| Project Manager | Bound the sample, assign ownership, review handoffs and report the result. |
| Text & Encoding Specialist | Recover the sample's source text and verify glyph/control meanings. |
| Translator | Translate with scene context, glossary and character voice. |
| ROM & Layout Engineer | Insert the saved text safely and create a reproducible test build. |
| Game Tester | Observe actual rendering, navigation and text progression; return defects. |

These roles can share one agent. Parallel work is useful only when its inputs and
ownership are independent. A role name does not prove model suitability or
connect a local model to the platform.

The handoff should identify the private project, what was saved and built, what
was actually tested, unresolved issues and the next proposed batch. Registering
a project in Studio does not create a working build adapter, and a passing sample
does not establish whole-game translation coverage or approve a checkpoint.
