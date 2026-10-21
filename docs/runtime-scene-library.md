# Explicit runtime scene library

`patchquest.runtime_scenes` prepares one explicitly named destination on a
runner-owned emulator session. It consumes contract v1 `CaseSpec`, `RunBinding`,
`AdapterCapabilities` and `EvidenceRef`, and returns a validated `SceneHandle`
plus preparation evidence. It does not schedule message batches, load builds,
own worker lifetimes, write files, change translations or approve text quality.

Definitions and actual route/save/state data belong in the selected private
project. Nothing scans projects, directories or ROM collections. No private
module is imported. Tests use independently invented pixels and byte strings.

## Definition and exact selection

Construct `SceneLibrary([definition, ...])` from explicit dictionaries; select
with `library.select(scene_id)`. Missing IDs raise `KeyError`, duplicate IDs fail,
and inputs/selected definitions are detached. A v1 definition has exactly:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1` |
| `scene_id` | Stable destination/route identity |
| `case` | Complete contract v1 `CaseSpec`, including context/window/page/variant |
| `reach_method` | `cold_boot_navigation`, `in_game_save`, `emulator_state`, `debug_injection` |
| `checkpoint` | `EvidenceRef` for save/state routes; otherwise `null` |
| `checkpoint_binding` | Origin `RunBinding` for save/state routes; otherwise `null` |
| `steps` | Ordered `{frames, buttons}` setup inputs; buttons use the existing runtime vocabulary |
| `arrival_assertions` | Named existing runtime `region_hash` or `color_count` assertions |
| `limits` | Explicit total `{frames, seconds, attempts}` for the entire preparation |
| `regenerate_from` | Named cold-boot or independently checked game-save route for saved routes; otherwise `null` |

There may be at most 1,000 scenes, 500 setup steps, 100 unique arrival assertions,
20,000 total frame calls, 600 elapsed seconds and three attempts. Frames/seconds
start at one. Each step allows 1–3,600 frames. Setup plus a fresh arrival frame
must fit the total frame allowance. Unknown fields, unsupported versions and
invalid controls fail closed. Assertion rectangles are native frame pixels;
out-of-frame conditions fail during preparation rather than being cropped.

Arrival expectations must have an independent basis recorded privately. For
example, a known destination marker and a menu state distinguish arrival from
an arbitrary successful load. This module applies supplied expectations; it
cannot establish their correctness. A matching pixel alone does not certify
normal gameplay, dialogue completeness, wording, audio or hardware behavior.

## Runner interface

```python
from patchquest.runtime_scenes import SceneLibrary, prepare_scene

library = SceneLibrary(explicit_private_definitions)
result = prepare_scene(
    library, selected_scene_id, case, pinned_binding, declared_capabilities,
    loaded_adapter, checkpoint_bytes=explicit_checkpoint_bytes,
)
handle = result['handle']  # Validated contract v1 SceneHandle
```

The runner must verify the loaded artifact bytes, emulator binary/configuration,
snapshot and revisions against `pinned_binding`. The library checks case digest,
record scope, adapter identity, required capabilities and the adapter's existing
`describe()` `kind`, `sha256` and `version` fields. Capability declarations and
adapter reports remain trusted local inputs, not independent execution proof.
Configuration identity is supplied and verified by the runner; the library does
not hash arbitrary adapter descriptions whose save-state fields may change.

Use the existing adapter interfaces: `step(buttons) -> runtime.Frame`,
`restore(bytes)` for emulator states and `load_save_ram(bytes)` for game saves.
Cold boot starts from a freshly loaded build and isolated save RAM, without
restoration; the runner must establish this initial condition. Game-save import
occurs before frame execution and then follows its own explicit setup route.
State restore and save import require their respective declared capabilities;
neither is inferred from frame/input support. No route falls back silently.

The runner owns session startup, teardown and isolation. With multiple attempts,
provide `reset(attempt_number)` to reload the same pinned build in a fresh session
before **every** attempt, including the first. With one attempt it is optional;
without it, the runner supplies an already fresh loaded adapter. No close/load
call is hidden inside scene preparation. The runner retains reset/adapter logs.

Setup steps run in order, followed by one neutral-input frame. All arrival checks
run against that fresh frame through `runtime.assertion`. `ready` requires every
check to pass. Results include the exact scene definition digest, case digest,
method/provenance, route flags, total attempted frames, elapsed time and ordered
attempts. Every attempt retains its latest returned `Frame`, completed check
results, status and reason, including failures preceding a successful retry.
Frames are Python objects; the result is **not** a JSON persistence record. Persist
captures through the artifact service and runner, retaining their associations.
The `handle` alone is JSON-compatible and contains no embedded image or path.

Missing capability/interface returns `unsupported`; incompatible checkpoint
identity/bytes returns `incompatible`; failed checks, adapter errors and budgets
return `failed`. Malformed definitions, wrong requested case/scope and unrequested
debug/checkpoint inputs raise `ContractError`. Unknown scene names raise
`KeyError`. Adapter exception classes are retained without copying potentially
private exception text into summaries; retain raw diagnostics privately.

The frame/time allowance is shared across all attempts, resets and hooks. An
attempted frame call is charged even if it fails. Elapsed time is checked around
operations, and a slow returned frame is retained. **Synchronous native calls
cannot be forcibly interrupted here.** Execute preparation inside the runner's
bounded worker, enforcing its hard process deadline and retaining timeout or
interruption diagnostics. A cooperative deadline is not a native-process sandbox.

## Exact checkpoint compatibility and regeneration

Before restoration, the supplied checkpoint bytes must match the evidence digest
and length. Its provenance method must match the selected adapter execution
method; synthetic checkpoints cannot become actual-emulator evidence. Existing
evidence metadata is preserved; byte verification does not rewrite the reference.

`checkpoint_changes(origin, current)` compares exact build ID, every artifact
digest, snapshot, scoped record revisions, adapter ID/version, emulator
ID/version/binary digest and configuration digest. Any difference rejects both
state and game-save reuse by default, before any adapter work. Thus text
relocation or another binary rebuild invalidates a state even if unserialization
would succeed. This v1 implementation provides no compatibility override.

Scenario, expectation and detector identities may differ between checkpoint
capture and consumption: they define the current test rather than the loaded
state's compatibility. The resulting handle retains the **current complete**
binding, and current arrival checks always run. Prior passes are never copied.
The preparation result separately pins the full scene definition digest; the
runner must retain it beside its encompassing scenario binding/report.

`library.regeneration(scene_id)` returns a plan; it executes nothing. Regeneration
references must exist, cannot be debug/state shortcuts and cannot form cycles.
After rejection, explicitly select the documented cold-boot route on the new
build, verify arrival, capture new bytes through the runner's existing save/state
interface and register a new definition with its exact binding. An in-game-save
route is suitable only after separate compatibility and real load-path testing;
this library conservatively checks its exact binding too. Preserve the old bytes,
binding and failed attempts. No state is overwritten or created automatically.

Legacy state metadata may identify the build and emulator without providing a
complete origin binding. Do not invent the missing fields to make restoration
eligible. Where retained input logs permit a cold-boot regeneration candidate,
splice each leg at the frame where its next checkpoint was actually captured,
not at the end of the earlier run. Preserve input durations and check held-button
boundaries. Capture filenames are labels; independently inspect the destination
and pin its arrival conditions. Even matching historical inputs and binaries do
not prove that continuous replay is equivalent to separate restored sessions.
Validate the new route in a bounded fresh run, retaining failure without silently
searching for a different frame, changing expectations or substituting a state.

## Debug routes and evidence limits

`debug_injection` additionally requires declared `debug_access`,
`isolated_test_session=True` and an explicit `debug_setup(adapter)` callback.
This hook may modify volatile emulator state only in the runner's isolated test
session. The module passes no ROM bytes or output destination to the hook and
provides no build/export path. It cannot sandbox arbitrary trusted Python: the
private adapter/runner must enforce volatile-only behavior, preserve immutable
build bytes and discard the isolated session. Never carry debug modifications
into a release build or reuse the session for ordinary gameplay evidence.

Debug results always retain `debug_assisted=True`, `normal_route=False` and
`reach_method=debug_injection`. Emulator-state results also have
`normal_route=False`. Cold-boot and game-save route labels describe preparation
only; the runtime contract still prevents synthetic results from satisfying
normal-gameplay coverage. Ready scenes are setup, not text-pass authority.

Synthetic conformance demonstrates repeatable orchestration, wrong-build/changed
revision rejection, failed-arrival retention and bounded retries. Real cold boot,
game-save load/persistence, state round trips and debug arrival must be tested as
separate scopes with pinned actual emulator captures. Before a private renderer
pilot relies on any scene, retain actual arrival evidence for that route and
build. No synthetic gate awards private checkpoint or release approval.

Run public synthetic checks with Python 3.10+:

```text
python -B -m unittest discover -s tests -p test_runtime_contracts.py -v
python -B -m unittest discover -s tests -p test_runtime_scenes.py -v
```
