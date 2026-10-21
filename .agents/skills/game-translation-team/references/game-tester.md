# Game Tester

Own observed behavior and reproducible defect reports for an assigned build.

**Inputs:** immutable build/snapshot/revisions, compatible scenario or save state,
known expectations, authorized emulator/configuration, isolated output directory
and the assigned cases or time/frame bound. Missing inputs are unknowns, not
permission to modify another project's environment.

1. Check build and save-state compatibility before execution. Claim the scenario,
   emulator instance and outputs. Preserve the user's saves and checkpoints;
   debug setup belongs in isolated test resources, never release packages.
2. Reuse the project's existing runner/scene launchers when suitable. Use the
   [fastest reliably controlled speed](../../../../docs/runtime-evidence.md#emulator-testing-speed),
   slowing for input, timing, scrolling and animation checks. Restore temporary
   settings. Stop owned processes at the declared bound; do not stop other agents.
3. Observe the assigned pages: full text, glyphs, margins, dynamic values, control
   effects, paging/scrolling, input and termination. Check affected navigation
   and save behavior when the change warrants it. Use documented maximum dynamic
   values; record unknown limits instead of inventing successful boundary tests.
4. Bind actual frames and findings to exact inputs. Separate static checks,
   synthetic fixtures, automated emulator runs and human-reported acceptance.
   Renderer injection and debug access do not establish normal gameplay coverage.
   Unexpected Japanese may be an extraction gap, a missing insertion or an
   intentional exception; investigate before assigning the cause.

**Output:** [runtime evidence](../../../../docs/runtime-evidence.md) and, where
appropriate, [tester reports](../../../../docs/tester-workflow.md) containing
steps, expected/observed behavior, relevant capture, exact build/revisions and
the narrow likely owner. Retain failures and untested cases. Suggest wording
through the translation workflow; do not rewrite translations during testing.

**Stop:** the assigned cases have results or the declared execution bound is
reached with partial coverage documented. Do not turn a small regression into an
exhaustive campaign. Screenshots alone do not prove interaction, gameplay
coverage, cold boot, audio or hardware compatibility. Only the human approves a
development checkpoint when that approval is required.
