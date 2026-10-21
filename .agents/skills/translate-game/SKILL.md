---
name: translate-game
description: Start a private Patch Quest DX game translation from an explicitly supplied ROM, disk image, or project manifest, coordinating a small first playable translation milestone. Use for game-project onboarding, not isolated line edits or platform maintenance.
---

# Translate a game

Act as Project Manager for the user's selected game. Read root
[AGENTS.md](../../../AGENTS.md), the [starter guide](../../../docs/starting-a-translation.md),
and the [game translation team skill](../game-translation-team/SKILL.md), including
its Project Manager guide and assignment/handoff template. Load other role and
platform-specific guides only as their work becomes relevant.

Use the starter guide's first milestone unless the user supplies a different
scope. Invoking this skill authorizes bounded specialist delegation within the selected
project and milestone when the host supports sub-agents. Do not ask for separate
delegation permission. Respect an explicit request to work alone and any host
restrictions. The starter prompt remains a template, not authorization for other
provider or external actions.

## Establish the selected project

- Require an explicit source file or existing private manifest. Reuse an
  unambiguous selection already supplied; otherwise ask for it. Do not pick a
  game from a collection, scan unrelated folders, or execute placeholder paths.
- Default the target language to English if unspecified and state that assumption.
  Infer the platform only from evidence; retain uncertainty when identification
  is incomplete. A user need not know the encoding or supply a finished adapter.
- Check the explicit local registry and relevant handoff for an existing private
  project. Reuse its authoritative state, owner and current milestone; never
  recreate it, erase progress, or claim another agent's work to start over.
- For a new project, follow the [project architecture](../../../docs/project-architecture.md)
  and [private project starter](../../../templates/project/README.md). Pin the
  original source hash privately and keep the original unchanged. Once a manifest
  exists, use `agent-context` to discover its instructions and capabilities.
- Follow [shared Studio setup](../../../docs/translation-studio.md#shared-studio-setup)
  when registration is applicable. Report registration, live selector availability
  and build support separately. An unavailable worker or pending coordinated
  refresh must not prevent independent headless work.

## Deliver the first milestone

Choose one small menu and one short dialogue passage, or an equivalent small
text sample if the game lacks either. Investigate the real encoding, glyphs,
controls, storage and renderer, then translate with context, build reproducibly
and check the sample in the game where available. Follow the existing role
guides for claims, protected corrections, immutable inputs and evidence.

Delegate bounded, independently owned scopes where useful when the host supplies
sub-agents; the skill invocation supplies delegation authorization. Perform roles
sequentially when delegation is unavailable, restricted, or not useful.
Do not launch separate persistent chats or connect an external/local model merely
because a role is named. Keep shared tables, guides, adapters and emulator
resources under explicit ownership.

Stop at the requested milestone, or a concrete blocker with no independent work
remaining. Report saved text, build artifacts, static checks, actual emulator
observations, remaining user tests and the recommended next batch separately.
Do not automatically start bulk translation, create more tickets, schedule
follow-ups, approve checkpoints or publish anything. Keep the larger objective
in the private handoff without treating this sample as whole-game completion.
