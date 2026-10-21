# Assignment and handoff

This is a prose template for existing task `instructions` and `handoff` fields,
not a new API schema or a command to launch agents. Concrete values stay in the
selected private project. Omit inapplicable fields rather than inventing inputs.

## Assignment

```text
Role and mode: chosen role; ordinary translation or proposal-only review if relevant
Outcome: one observable deliverable
Project: exact explicitly selected manifest
Scope: record IDs, scenarios, files and agreed resource keys
Inputs: current revisions; snapshot/build identities and private evidence as needed
Prerequisites: existing task IDs or specific missing input; current owner
Allowed changes: exact owned scope; note protected corrections and immutable inputs
Acceptance: checks that demonstrate this deliverable
Bound and stop: batch size / cases / execution limit; unresolved findings allowed
Deferred: adjacent work outside this assignment
Handoff to: responsible role or current project owner; no automatic agent launch
```

Map existing record IDs, exact resource keys and prerequisite task IDs to
`work-create` fields; keep the remaining description in `instructions`. For new
catalog records use an agreed resource scope until IDs exist. Start a session,
claim and read the returned revisions/fence before writing. Follow the
[coordination contract](../../../../docs/agent-collaboration.md) for publication,
renewal and recovery. Neither a file path nor a role label alone creates a lock.

## Handoff

```text
Result: completed, blocked or returned to queue; explain any partial outcome
Changed: exact records/revisions or files; active translations versus proposals
Artifacts: private build/snapshot/report references with applicable identities
Verified: checks actually run, their inputs and evidence level
Unresolved: remaining uncertainty, failed cases and untested behavior
Preserved: relevant human corrections and immutable inputs
Next dependency: concrete input needed and responsible owner, or none
```

Use actual returned revisions, never copy example numbers into a write. Close the
finished claim and session; the next writer obtains its own identity and claim.
If work is blocked or requeued, retain the reason and published partial results.
The next owner verifies the handoff inputs before consuming them.

## Small invented example

The following identifiers, revisions and wording are independently invented.
They illustrate the workflow, not results of a game test.

The manager scopes one garden-gate message and its two-line window. The encoding
specialist establishes `sample-gate` revision 2 with a verified name placeholder
and end control, while leaving a different unknown glyph outside this batch.
The translator reads revision 2 and publishes the complete greeting as revision
3, retaining those controls. A neighboring human-corrected `sample-sign` stays
unchanged; any alternative for it requires its own authorized scope and remains
a proposal.

The engineer consumes a fresh snapshot containing `sample-gate` revision 3,
produces a new test build and records that static wrapping fits. The tester
checks the assigned greeting with its supported longest name, advances the page
and exits the window. If the last line is clipped, the handoff returns the exact
build/revision and capture to the engineer. It does not silently shorten the
translation or mark gameplay coverage complete. Once the repair passes the
assigned case, the manager closes this batch; the unknown glyph remains deferred.
