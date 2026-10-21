# Coding-agent compatibility

Both adapters discover [exceptions and content handling](translation-exceptions.md)
through `agent-context`. Use `assessment-context`, revisioned `issue-put`, and
`provider-result` for evidence-bound annotations, never provider-specific queues
or automatic routing around restrictions.

All agents use the same Python/JSON state API, private project contract and
localization policies. No provider SDK, API key, model selection or second
translation engine is required. An agent's optional identity/model label is
provenance, not a requirement or an authorization mechanism.

| Agent | Instruction entry | Skill entry | Setup |
|---|---|---|---|
| Codex, including Astra workflows | `AGENTS.md` | `.agents/skills/` | Open the platform checkout; select the explicit private project via local registry |
| Claude Code | `CLAUDE.md` imports `AGENTS.md` | `.claude/skills/` adapters | Open the platform checkout, accept applicable workspace trust, and grant access to the selected external project as needed |
| Other coding agents | Read `AGENTS.md` explicitly | Read canonical `.agents/skills/*/SKILL.md` | Use Python CLI/JSON; native auto-discovery is not claimed |

The model is not the discovery mechanism; the agent application is. Installed
versions, managed policies, workspace trust and filesystem permissions can
change what a client loads. Opening an external private project by itself does
not automatically load instructions from a sibling platform checkout. Open the
platform too, or explicitly supply its instructions/skill path. Private project
instructions supplement the platform rules.

## Documented conventions

Checked against official documentation on 2026-10-17:

- Codex reads repository instructions along the root-to-working-directory chain,
  with configured overrides and limits. Its skills use repository
  `.agents/skills/` discovery. See [AGENTS.md discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
  and [local skills](https://learn.chatgpt.com/docs/build-skills).
- Claude Code supports `CLAUDE.md` imports with `@` paths resolved from the
  importing file. Project skills live in `.claude/skills/<name>/SKILL.md`.
  See [memory/imports](https://code.claude.com/docs/en/memory)
  and [skills](https://code.claude.com/docs/en/skills).

Current Claude Code also documents native AGENTS.md discovery, conditional on
version and instruction settings. We retain the documented `@AGENTS.md` bridge
for compatible older installations and avoid changing user/managed settings.
The official memory guide states that keeping this import does not double-load
the same instructions. Native support does not remove the skill adapter check.

Only the Claude instruction file uses import syntax. Skill adapters explicitly
tell the agent to read the canonical workflow; they do not assume `@` imports
are implemented inside a skill. Links point back to the canonical file, whose
supporting paths must be resolved from its own directory. Regular text adapters
avoid symlink privileges and worktree checkout differences on Windows.

## Maintenance and validation

Edit shared instructions in `AGENTS.md`, and workflows under `.agents/skills/`.
Run:

```sh
python tools/sync_agent_adapters.py
python tools/sync_agent_adapters.py --check
python -B -m unittest discover -s tests -p "test_*.py"
```

Adapters contain canonical-content hashes (UTF-8 with LF line endings) and derived descriptions, so stale
metadata is detected. New agents should receive thin adapters using documented
conventions, not independent copies of policy. Recheck official documentation
when conventions change; keep these instructions and tests synchronized.

Automated tests verify files, metadata, canonical hashes, references and a copied
checkout with spaces in its path. They do not prove that a particular installed
agent actually selected a skill. No unattended Claude/Codex provider session is
required or run by the tests. For a manual runtime check, open a fresh checkout,
ask the agent which project instructions and translation skill it found, then
ask it to read an explicitly selected synthetic project's state. Do not use
private project data in a cloud client without a separate intentional decision.

See [Studio and state](translation-studio.md) for shared operations. Human edits
remain protected regardless of which agent writes the next revision; CAS
conflicts require rereading, not blind retries with a newer revision number.

## Sequential and concurrent workflows

Both clients use `state MANIFEST agent-context` to discover canonical paths,
shared operations and build capability. Follow [the collaboration contract](agent-collaboration.md)
and the `translation-collaboration` skill. The same work queue, memory, glossary,
protected corrections and immutable build inputs apply regardless of provider.
No API keys or provider SDKs belong in project configuration.

The same discovery packet advertises the optional private [narrative guide](narrative-context.md),
its revision/hash and the `narrative-context` read action. Both clients read the
same work, character, scene and revision-bound review context. These are data,
not a provider-specific instruction copy or permission to rewrite human edits.

Use `python examples/collaboration-demo.py --workspace .local/projects/agent-demo`
for a fresh synthetic trial. It prepares a protected greeting and two dependent
tasks without a ROM or AI request. Open the platform in each client, explicitly
select that manifest, and ask the first client to discover its instructions and
skill, claim `review-greeting`, read memory, publish an alternative and leave a
handoff. Ask the second to claim `review-lantern`, read that handoff and glossary,
then publish a contextual improvement. Inspect histories/proposals and verify
the protected greeting is unchanged. Neither client should edit provider policy,
source data, controls or database files directly. Use `capabilities` before any
`build-submit`; the demo has no ROM pipeline by default.

Validation has separate levels: adapter/hash checks, real-process synthetic API
races, installed-client discovery/tool execution, and private build integration.
A passing API test with a provider label does not certify that provider runtime.
Record installed versions, selected model, operations observed, auth/permission
failures and test evidence privately. A blocked login or unavailable model is a
runtime limitation, not permission to install software, bypass policy or silently
switch models. Recheck help for the installed version before using automation.

For opt-in CLI probes, use a reviewed public-only copy and invented data. Codex
supports `exec` with explicit model/workspace and ephemeral sessions; Claude Code
supports print mode with bounded turns, explicit tools and permission settings.
Keep normal authentication and permission boundaries; never use bypass flags.
Inspect project hooks/MCP configuration before a noninteractive Claude invocation.
Do not use `--bare` when testing normal instruction/skill discovery, because it
skips that configuration. These probes are intentionally not run by ordinary
unit tests. See [Codex CLI](https://learn.chatgpt.com/docs/cli/reference) and
[Claude programmatic mode](https://code.claude.com/docs/en/headless).

### Keep isolation and discovery checks distinct

A long-running terminal may retain an old PATH after an agent installation.
Try a fresh shell or a verified executable path and check `--version`; do not
reinstall merely because the current process cannot find the command.

Claude's `--restricted` mode can suppress project skill discovery along with
project settings. A failed native Skill invocation in that mode does not by
itself indicate a broken adapter. Directly reading the canonical skill verifies
its use, but does not verify native discovery. Check both the initialization
skill list and the successful Skill tool result in a normal-discovery probe.
See the installed CLI help and [CLI modes](https://code.claude.com/docs/en/cli-reference).

For a synthetic probe that needs normal discovery, remove general shell,
file-writing and unrestricted file-reading tools. A test-only tool bridge can
instead pin one invented project manifest, allowlist state operations, and read
only hash-checked public files. It should call the existing CLI without shell
interpolation, reject arbitrary paths, and log actual requests and results.
Review hooks, settings and MCP sources before launch; retain normal authentication
and managed policy. Such a validation harness is not a shipped production MCP
integration or a certification of unrestricted terminal access.

Bound opt-in probes by model, dollar budget, turns and elapsed time; never launch
them from ordinary tests. Save the resolved model, reported usage/cost, native
skill results and state history privately. Provider cost estimates are not
verified invoices. Confirm protected heads, proposals, task fences and handoffs
from saved state rather than relying on the model's summary. Separate live
sequential handoff evidence from automated concurrency tests and private ROM
build verification; one does not prove the others.

For a live concurrent-client claim, retain process start/end times and actual
operations performed while both clients are running. Overlapping lease expiry
times alone do not establish overlapping execution. If a client reports a policy
block, stop that probe and record it; a successful process exit is insufficient.
Do not weaken policy, change transports to evade it, or relabel scripted API
tests as a live provider test.

### Windows sandbox configuration in isolated launchers

The requested access scope (`--sandbox read-only` or `workspace-write`) and the
native Windows implementation (`windows.sandbox`) are separate settings. A
launcher using `--ignore-user-config` omits the user's configured implementation
as well as unrelated preferences. It must explicitly retain a verified,
already-provisioned implementation permitted by managed policy. For an
installation configured for the elevated backend, the per-invocation setting is
`-c 'windows.sandbox="elevated"'`; this selects the enforcing sandbox, not an
administrator shell. Do not apply that value blindly on other installations.
See the official [Windows sandbox guide](https://learn.chatgpt.com/docs/windows/windows-sandbox)
and [CLI option reference](https://learn.chatgpt.com/docs/cli/reference).

Diagnose a rejection with the installed CLI's help, redacted `codex doctor --json`
report, effective settings and relevant rules before changing anything. A
`blocked by policy` message alone does not identify a forbidden rule, an OS
script policy, or a broken project. A read-only `execpolicy check` tests the
specified rule files; no matching rule does not prove every policy layer allows
execution. Do not remove rules, disable sandboxing, grant full access, or change
PowerShell execution policy to make a test pass.

Validate a justified launcher correction with one bounded read-only synthetic
probe, retaining the original scope, rules, model and prompt. Record actual
command completion, preserve the failed evidence, and verify saved security
configuration remains unchanged. A successful read resolves only that preflight:
workspace writes, project isolation and real concurrent execution still require
their own validation.

Before a write-enabled probe, test an allowed write in the selected synthetic
workspace and a denied write to a disposable canary outside all allowed roots.
Account for any temporary-directory access granted by the installed sandbox:
another temporary directory may not be a valid negative control. Check the
canary's contents afterwards. This tests those paths, not every possible access
or read-isolation boundary. Never use a real project file as a denial probe.

Verify the interpreter under the same sandbox before launching paid clients.
A Windows app-execution alias can resolve successfully for the signed-in user
yet fail to start under the sandbox account. Use a verified, already-installed
regular interpreter when appropriate; do not weaken permissions or reinstall
software to make the probe pass. Invoke Python with `-X utf8` for Japanese text
and JSON, and specify UTF-8 on both ends of captured subprocess streams.

Have the harness create shared event logs before starting sandboxed workers,
then preflight worker appends and coordinator reads. Files newly created by a
restricted account may be inaccessible to the coordinator. Preserve failures;
do not change their ACLs to conceal an isolation issue. Keep task decisions in
the actual agents. A driver may provide explicit synchronization barriers and
synthetic human edits, but must not claim or publish on an agent's behalf.
Measure independent lease overlap from successful claim/finish intervals:
a later status snapshot can miss a fast worker that already finished.

Report discovery observations precisely. A skill listed at startup, an explicit
native Skill invocation, a canonical file read, and a configured instruction
import are different evidence. Do not infer an unobserved tool call from a
successful workflow. Retain aborted runs and their partial usage separately;
an interrupted client may not emit its final cost report. Do not silently retry
paid probes or present a later successful run's cost as the whole investigation.
