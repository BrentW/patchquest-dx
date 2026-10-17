# Intelligent dialogue layout

`patchquest.typography.planning` measures native pixels and selects a presentation
supported by an explicit window policy. It produces a build artifact, not ROM
bytecode or an edited translation. Private adapters own encodings, renderer hooks,
caller geometry, buffers, allocation, timing and game evidence. Historical
`typography.layout` APIs remain unchanged.

## Verify capabilities

Record visible line capacity, ink/advances, line step, controls, dynamic value
limits, termination, input behavior and surrounding graphics. Newline acceptance
does **not** prove scrolling: the cursor might simply move outside the window.
Wait-and-clear pagination also differs from scrolling.

Verify actual scrolling, boundary triggers, retained lines, cursor, controls,
input and termination. For pagination, check clearing, held-button behavior,
allocation reuse and final exit. Do not introduce waits into timed notifications
or nonblocking scripts without a validated timing policy. Geometry changes need
checks of neighboring graphics, borders, cursors, highlights and restoration.

Policies require private evidence references for enabled capabilities. References
are adapter assertions, not independent proof: static traces, emulator screenshots
and hardware tests remain separate evidence levels. Scope policies to verified
callers; the same text ID can appear in different windows.

## Decisions and thresholds

The planner tries these presentations in order:

1. **original**: all explicit lines/pages fit.
2. **adjusted**: small overflow fits a verified padding/position alternative.
3. **wrapped**: logical lines fit the original visible capacity.
4. **scrolled**: verified native scrolling handles additional lines without
   expanding the window or inserting unnecessary page waits.
5. **resized**: an explicitly verified alternate region fits.
6. **paginated**: verified page advancement displays the remaining lines.
7. **unresolved**: no supported strategy displays everything within bounds.

Default heuristics call overflow small at up to 4 pixels **or** 4% of available
width/height, moderate through 25%, and large beyond that. Both axes are measured.
Thresholds are configurable hints, never permission to clip. Larger overflow
bypasses minor adjustments and favors logical flow. Artwork and glyph advances
are not silently shrunk; compact spacing needs an explicit adapter.

Dialogue and notification policies can opt into supported flow. Menu, HUD and
fixed policies reject automatic scrolling, pagination and resizing. Wrapped menu
labels still need verified capacity inside their own selection area. Specialized
UI geometry changes require a separate validated adapter.

Soft wrapping minimizes line count, then balances lengths without splitting words
or atoms. Explicit line/page breaks and opaque event order survive. Soft-wrap
separator spaces become layout separators; stored wording, revision and
human-correction status remain unchanged.

## API example: invented renderer

```python
from patchquest.typography.layout import Font
from patchquest.typography.planning import Region, WindowPolicy, plan_layout, text_runs

font = Font()
policy = WindowPolicy(
    'invented-conversation', Region(136, 40),
    line_height=font.height, line_step=font.line_step,
    wrap=True, paginate=True,
    evidence={'wrap': 'synthetic line test', 'paginate': 'synthetic page test'},
)
plan = plan_layout(font, text_runs('Bring a lantern to the garden gate.'), policy)
plan.require_resolved()  # Before encoding or writing a successful build.
report = plan.report()
```

Replace invented evidence with verified private profiles for real projects.
`Region` describes the interior, padding and optional coordinates. `adjustments`
retain its dimensions; `resized_regions` declare alternate geometry. The adapter
must apply selected geometry; returning a plan alone does not change a game.

Semantic `Run` kinds are `text`, `line`, `page`, measured `atom` substitutions and
validated layout-inert `control` events. Unknown game controls fail closed or must
be resolved privately. Font/position-changing controls are not layout-inert.
Resolve dynamic values or reserve verified maximum widths before planning; check
vertical fit privately. The planner never guesses game escape syntax.

Default measurement separates visible bounds and advances. A custom
`measure(runs, left_padding)` can account for segment rounding or tile packing;
return an occupied right edge in pixels. Independently validate encoded pixels,
transfers and buffers against the plan. Plans do not prove resource capacity or
hardware compatibility.

Planning budgets: 4,096 runs, 32,768 value characters and 512 tokens per paragraph;
`max_lines` and `max_pages` further constrain flow. Unsupported glyphs, unknown
controls, exhausted budgets and unresolved overflow are explicit errors, never
grounds for shortening a saved correction.

## Builds and Studio

Freeze saved revisions through the state API. Plan/encode supported variants and
validate controls, resources and renderer behavior before reporting successful
ROM/BPS artifacts. Failures retain corrections and snapshots, identify the
record/context and leave the job failed. Use fresh output paths, repeat builds
exactly and verify patch reconstruction.

Private pipelines can include a compact summary in `validation.layout`:

```json
{"schema":1,"counts":{"paginated":1},"records":{
  "invented-note":{"revision":3,"variants":{
    "small-panel":{"decision":"paginated","pages":2,"lines":2,
                   "width_px":120,"limit_px":128}
  }}
}}
```

Keep full plans private and state reports below their 250,000-character limit.
The read-only `layout-reports` operation returns entries only when their revision
matches the build's frozen snapshot. Studio shows decisions and marks older
revisions stale. Builds summarizes counts across window contexts; those counts
need not equal distinct-message counts. The endpoint never opens report-supplied
paths. Reports concern saved build inputs, not unsaved drafts.

Review real screenshots and gameplay for margins, balance, cadence, held/released
input, clearing/restoration, adjacent graphics and continuation. Specimens and
modeled CPU traces cannot approve an interface. Preserve approved checkpoints
until the owner reviews the new build.
