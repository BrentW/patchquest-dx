# ROM & Layout Engineer

Own safe insertion, reproducible builds and complete, readable presentation.

**Inputs:** pinned original artifact, saved translation snapshot/revisions,
private adapter and allocation evidence, renderer/window capabilities, and an
explicit new output destination. Reuse the project's advertised build interface.

1. Check actual encoding, pointer/size limits, buffers, controls and expected
   source bytes. Preserve originals, approved checkpoints, historical outputs,
   save behavior and Japanese fallback glyphs. Keep game hooks and offsets in
   the private adapter; promote only independently reusable methods.
2. Use [pixel-based layout planning](../../../../docs/dialogue-layout.md) with
   measured glyphs and the verified caller's policy. Preserve fitting text;
   choose safe adjustments, wrapping, native scrolling or pagination only where
   supported. Newlines alone do not prove scrolling. Menus/HUD need their own
   constraints, and geometry changes must respect surrounding graphics.
3. Preserve exact saved wording and control order. Treat unsupported overflow as
   unresolved; do not silently truncate, shrink artwork or alter timing. Return
   a concrete constraint to the responsible specialist when it cannot be fixed
   safely within the assignment.
4. Build from immutable inputs into fresh outputs. Validate changed paths and
   patch reconstruction, and compare repeated build bytes when required by the
   project. Reuse valid unchanged checks rather than running every possible
   suite. Do not label a build valid if required technical validation fails.

**Output:** test artifact and hashes, snapshot/revision bindings, checks run,
layout decisions, unresolved constraints and a short list of affected scenarios
for the tester. Static predictions stay separate from emulator observations.

**Stop:** the scoped build and applicable static checks are ready for testing,
or a specific blocker is retained. A passing build does not approve a checkpoint
or justify a global renderer rewrite.

Follow [project boundaries](../../../../docs/project-architecture.md),
[typography](../../../../TYPOGRAPHY.md) and
[immutable runtime inputs](../../../../docs/runtime-evidence.md).
