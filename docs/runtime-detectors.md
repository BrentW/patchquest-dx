# Runtime text detectors

## Scoped bitmap comparison

`image_region` version `1` requires capture capability only. It compares exact
decoded RGB bytes inside an independently specified native-pixel rectangle with
a pinned SHA-256 and an explicit expected-match boolean. For example, this
independently invented 2-by-1 region contains two RGB pixels:

```python
import hashlib

check = {
    "id": "invented-panel",
    "kind": "image_region",
    "rect": [1, 2, 2, 1],  # x, y, width, height in native pixels
    "rgb_sha256": hashlib.sha256(bytes([8, 16, 24, 32, 40, 48])).hexdigest(),
    "expected_match": True,
}
```

Use this check in the existing expectation document and pin the complete
expectation digest and detector version before execution. The independent basis
must explain the reference and rectangle, rather than deriving expected pixels
from the output being tested. `expected_match=False` asserts only nonidentity
with that one pinned region, not that the image has any particular alternative
content. Dimensions and rectangle position also belong to the bound check.

This is scoped image evidence, not OCR, language identification, glyph identity,
native text bounds, overflow classification or page/wait/scroll instrumentation.
An independently identified source-text bitmap can be used as a scoped positive
control, but matching or not matching it does not establish language correctness
elsewhere. An image mismatch alone does not identify its cause. Existing native
glyph and control checks still require their original instrumentation.

The final-frame EvidenceRef must have `media_type="image/png"`; its bytes and
length are independently checked through the existing resolver. Multiple final
captures must agree on the encoded byte digest, otherwise the image result is
unknown. Earlier captures cannot substitute. Current/completed execution,
capability, independent actual-emulator basis and expectation/version pins remain
required, just as for other checks. No observation assertion or provenance is
rewritten. Findings use the existing deterministic ID and shared plan helpers.

The deliberately narrow decoder supports only 8-bit RGB, noninterlaced PNG with
IHDR, contiguous IDAT chunks and IEND, CRC validation and standard row filters
0–4. Palette, alpha, ancillary/profile chunks and other formats yield unknown;
they are not treated as a visual nonmatch. It accepts at most 4 MiB encoded bytes,
4,096 chunks, dimensions up to 4,096 on either axis and 1,048,576 pixels total.
Inflation is limited to the exact expected scanline size plus one detection byte;
truncated, excess, concatenated or trailing compressed streams fail closed.
For plan schema `1`, only one unambiguous final image is decoded per detector call. Region comparisons
share a 4,194,304-pixel work allowance; later image checks beyond it yield unknown
without hiding unrelated checks. Invalid/out-of-frame geometry, unavailable bytes
and unsupported/malformed images cannot pass even an expected-nonmatch check.

The diagnostic measurement is `scoped_captured_rgb_region`, with observed region
digest and match boolean when measurable. A failed finding includes the precise
region and expected/observed identity. Approved exact revision-bound exceptions
retain the existing exception semantics; an unknown image cannot be waived into
a pass. Decoding success does not certify actual emulator execution: native
calibration still requires genuine core output, retained positive/negative/fault
evidence and separate review. Synthetic PNG controls remain synthetic.

For an omitted-input control, first establish the same independently checked
arrival in both cases. Preserve all frame durations and capture points, replacing
only the intended button press with neutral input. Both cases must test the same
intended destination: the normal case should pass and the omission should fail.
A separate check that the omission retained the previous screen is useful
diagnostic evidence; its pass cannot replace the intended-destination failure.
If both cases produce the same intended result, retain the control as ineffective
rather than claiming fault sensitivity. Input callbacks show delivery to the
adapter, not that the game accepted the input. Visible transitions and holds
remain image evidence and must not populate unobserved native control signals.

### Exact capture selection (plan schema 2)

Plan schema `2` adds an explicit selector to every `image_region` check:

```python
check = {
    "id": "invented-middle-panel",
    "kind": "image_region",
    "capture": {"frame": 5},
    "rect": [0, 0, 2, 1],
    "rgb_sha256": hashlib.sha256(bytes([8, 16, 24, 32, 40, 48])).hexdigest(),
    "expected_match": True,
}
```

The selector has exactly one field, `frame`, an integer from zero through
`2**63 - 1`; booleans are invalid. It selects the original observation's capture
at that exact frame. Missing, beyond-observed, or duplicate capture entries yield
unknown, even when duplicate entries reference identical bytes. Never substitute
the final image or a nearby frame. A valid selector does not manufacture a capture.
An earlier selected image can be checked without a final-frame capture; all other
detectors retain their final-frame requirements.

Schema `2` image checks require `RunBinding.detectors["image_region"] == "2"`.
Other detector algorithms remain version `1`. `DETECTOR_VERSIONS` retains its
legacy version-`1` defaults; explicitly pin image version `2` and the entire new
expectation digest before execution. Do not rebind a historical observation to
apply a new selector. Plan schema `1` and image algorithm `1` retain their original
digests, finding identities and final-image behavior, including same-byte duplicate
final entries. The unchanged schema-`1` `RuntimeExpectationManifest` envelope may
contain both plan versions. Each original observation must pin the algorithm its
selected plan requires; a mixed envelope does not override that binding.

A schema-`2` image finding identifies only the uniquely selected capture's evidence
ID, or an empty list when no unique selection exists. Its measurement and any
image defect include the capture frame; the selector is part of the expectation
digest and an exception cannot silently migrate an image defect to another frame.
The observation, run ID, record revisions and provenance remain unchanged. All
original capture bytes are still checked; changed or unavailable unselected bytes
also prevent a definite result. Selected evidence must be a verified RGB PNG with
the same decoder limits described above. A nonmatch check cannot pass unavailable,
ambiguous, malformed or out-of-frame evidence.

Multiple selected images share a 4,194,304 decoded-pixel allowance per call, in
addition to the existing 4,194,304 compared-region-pixel allowance. Each attempted
image reserves its advertised pixel footprint after its header dimensions and
RGB format are validated, before pixel allocation or inflation. The reservation
remains charged if later parsing, inflation or row reconstruction fails. Successful
images and failed decode outcomes are cached by checked PNG byte digest after
unique entry selection; identical bytes do not spend the decode allowance again.
This never deduplicates ambiguous capture entries. A budget-exhausted check stays unknown,
without suppressing another check's confirmed failure. Synthetic controls remain
synthetic; selecting a native capture does not establish page/wait/scroll/termination
signals, glyph telemetry, broader text coverage or checkpoint approval.

`patchquest.runtime_detectors` consumes contract-v1 cases, observations, capability
declarations and independently justified expectations. It returns DetectorFinding
records without changing its inputs, resolving translations, controlling an
emulator or approving a checkpoint. The independently authored code, guide and
invented controls use the repository Apache-2.0 scope.

## Consumer interface

```python
from patchquest.runtime_detectors import detect, expectation_digest, expectation_manifest

# Build the complete plan before executing any case.
expectations = expectation_manifest(all_case_expectations)
# Pin expectation_digest(expectations) in the run's RunBinding before execution.
# Pin DETECTOR_VERSIONS defaults for v1; schema-2 image checks explicitly need "2".
findings = detect(case, observation, capabilities, expectations,
                  artifacts.resolve, expected_binding=current_binding)
```

Each definite result requires a completed current observation, compatible case
and expectation digests, the declared detector version, verified capture bytes
and a capture at the plan's required frame (final frame except schema-2 image
selectors). The resolver normally is
RuntimeArtifacts.resolve; the detector independently rechecks its returned bytes
against EvidenceRef SHA-256 and length. A verified label alone is insufficient.
Missing/changed captures yield unknown; no resolver or detector can silently drop
required evidence. Findings retain evidence IDs and bound run/case/revision data.
A per-check pass does not override a failed observation or certify other checks.
Synthetic provenance stays synthetic, regardless of the expectation basis.

Supported checks and required instrumentation:

| Kind / version | Check | Additional capability |
| --- | --- | --- |
| image_region / 1 | Exact independently pinned RGB rectangle identity or nonidentity | None beyond capture_frames |
| image_region / 2 | The same RGB comparison at one exact original capture frame | None beyond capture_frames |
| bounds / 1 | Final glyph rectangles against explicit interior, padding and tolerance | observe_glyphs, page_advance |
| overlap / 1 | Pairwise final glyph rectangle intersection above explicit pixel area | observe_glyphs, page_advance |
| glyphs / 1 | Exact final glyph-ID sequence, including missing/wrong/reordered glyphs | observe_glyphs, page_advance |
| source_language / 1 | Explicit independently mapped source-language glyph IDs | observe_glyphs, page_advance |
| completion / 1 | Explicit final page_complete signal | page_advance |
| controls / 1 | Specified paging/scrolling/input-wait/termination booleans | page_advance, native_scroll or input as applicable |
| resources / 1 | Explicit observed metric maxima | observe_resources |

All require capture_frames. Absent capability is unsupported; advertised but
missing observations are unknown. False differs from unobserved/null. A known
control/resource violation remains failed if another metric is unknown, and the
unknown detail is retained. In-progress/failed/interrupted execution cannot
become a completed detector pass. Glyph geometry/sequence checks require explicit
page_complete true to avoid treating animated partial rendering as final clipping;
a completed run with page_complete false fails completion but leaves final geometry
unknown. Checks only inspect glyph observations at the final frame. Empty streams
cannot vacuously pass visual/language checks; an explicit expected glyph sequence
can detect an empty actual stream as missing glyphs.

No OCR or language inference is provided by capture capability. A bitmap-only
adapter without glyph instrumentation cannot use these glyph/language checks.
Known source-language detection requires an independently verified mapping; a
glyph ID or its spelling alone does not establish that its displayed image is
Japanese or any other language.

## Expectation schemas 1 and 2

`expectation_data` validates a strict local expectation dictionary with exactly:

- schema_version: 1 or 2; expectation_id; case_sha256 (normalized CaseSpec digest).
- basis: method (independent_inspection or synthetic_control), reference_sha256,
  and a substantive reason recording independent inspection/calibration.
- checks: nonempty bounded array, each with unique id and known kind.
- exceptions: bounded array, possibly empty, as described below.

Each check has exactly id, kind and the following fields:

| Kind | Fields |
| --- | --- |
| bounds | rect: [x,y,width,height], padding: integer pixels, tolerance: integer pixels |
| overlap | maximum_overlap_pixels: integer intersection area |
| glyphs | glyph_ids: ordered array; duplicate glyphs are meaningful |
| source_language | source_glyph_ids: explicit IDs, mapping_sha256: independent mapping identity |
| completion | No additional fields |
| controls | expected: boolean map of page_complete, line_advanced, scrolled, input_wait and/or terminated |
| resources | limits: metric-to-maximum-integer map |
| image_region | rect: [x,y,width,height], rgb_sha256: decoded region digest, expected_match: boolean |

Schema `2` image checks additionally require `capture: {"frame": integer}`.
Schema `1` checks and all nonimage checks forbid that field. No other check
parameters change between these plan versions.

Expectations, mappings, baseline identities and rationales stay private for real
projects. The reference hash and method are provenance declarations, not proof
that independent inspection occurred. Do not generate an unquestioned reference
from the output under test. Review actual native-scale captures and animation
states independently; retain baseline bytes and rationale with the exact content,
configuration and instrument versions. Synthetic basis cannot calibrate an
actual_emulator observation: the result remains unknown. Actual controls must
establish detector sensitivity and instrument reliability for their precise scope.

`expectation_digest` covers the full normalized expectation, thresholds, mapping
identity, rationale and exceptions. RunBinding.expectation_sha256 must match.
Unknown versions/kinds/fields, incompatible case definitions and missing or
incompatible detector-version pins fail explicitly. Threshold/meaning changes
need an updated expectation digest; algorithm changes require a detector version.
Never rewrite an immutable old observation to inherit new semantics. Reanalysis
must retain old results and clearly bind new results to their actual inputs.

## Exact, revision-bound exceptions

An exception has check_id, defect_sha256, content_binding_sha256 and a reason.
Use defect_digest on the exact independently reviewed diagnostic defect, and
exception_binding(binding, case_sha256) on its RunBinding and case definition.
The latter covers content/configuration/context,
versions and annotations while excluding only expectation_sha256 to avoid a
circular hash. Any changed content/revision/configuration invalidates it. Stale
exceptions yield unknown rather than being silently ignored or inherited.

Only an exact matched defect for that check is excepted. Other defects still
fail, and missing observations remain unknown even when all known defects are
excepted. Reasons, exact diagnostics and applied exception data remain in the
finding's namespaced patchquest:detector extension. That extension also records
unobserved details and that measurements are adapter-reported. It is diagnostic
provenance, not an alternate assertion or approval axis.

## Measurement and false-positive limits

These algorithms check reported glyph identities, rectangles, control signals
and resource counts. Checked captures bind the report to retained bytes; they do
not prove that an adapter's claimed glyph geometry corresponds to those pixels.
Validate ink bounds independently rather than using character cells as a claim
of visible clipping. Bounding rectangles can intersect even when glyph ink does
not, and animation, accents or deliberate typography can create legitimate
intersections. Independently measured tolerances or exact exceptions are required.

Wrong pixels paired with a falsely correct glyph ID can be a false negative.
Unexpected source glyphs outside the independently mapped set are also not
recognized. Controls require trustworthy observed native behavior, not merely
the runner sending a button; resource maxima require independently justified
capacity limits. Timed/nonblocking windows need appropriate explicit expectations,
not an assumed input wait. No detector certifies meaning, translation voice,
whole-game coverage, audio, save persistence, hardware or flawless visual design.

To bound comparison work, final streams over 4096 glyphs and overlap streams over
256 glyphs yield explicit unknown. Narrow the declared case; no glyph is silently
dropped. Expectation/check/exception collections are bounded. Native-run deadlines
and memory/disk admission remain the runner/artifact owners' responsibilities.

## Controls and pending actual acceptance

The public synthetic suite independently invents geometry, glyph streams, solid
PNG captures, resource counts and control signals. Positive fault controls inject
horizontal/vertical overflow, collisions, missing/wrong glyphs, known source-glyph
markers, incomplete rendering, skipped page advancement, absent input waits,
broken scrolling/termination and resource overflow. Negative controls pass only
within that invented scope. Tests also cover missing instrumentation/captures,
stale inputs, changed thresholds/versions, exact exceptions and retained unknowns.

```text
python -B -m unittest discover -s tests -p test_runtime_detectors.py -v
```

These tests do not publish detector-controls-ready. Actual calibration requires
an accepted phase-A runner, an explicitly claimed isolated private fixture,
independently inspected positive/negative baselines and relevant deliberate-fault
sensitivity with retained failed findings. Fault variants stay disposable private
inputs and cannot become approved checkpoints or release artifacts. A broader
source-language acceptance claim still requires known Japanese in the original
private baseline and a known translated negative; a calibrated source-template
comparison satisfies only its explicitly limited template scope. Broader unchecked
criteria remain open rather than being relabeled complete.

### Explicit acceptance scope

A detector-control handoff must name its detector kinds/versions, capabilities,
observable claims, independent reference basis, actual positive/negative/fault
controls, false-positive limits and excluded or unknown signals. The integration
owner may accept a limited image-based scope for a correspondingly declared pilot
without waiting for optional instrumentation that its adapter does not supply.
That acceptance does not close a broader detector issue or satisfy a broader
required-check plan. Never remove unsupported checks from an existing denominator
to manufacture readiness; retain that plan and declare a separate narrower pilot.

For a capture/input adapter, calibrated image-region checks can support exact
source-template recognition, expected translated regions, visible fragment/border
changes and input-dependent destination/held-page images. Source-template
nonidentity is not general source-language absence. Pixel mismatch alone is not
a diagnosis of missing glyphs, clipping, resource exhaustion or a broken renderer.
A visible page hold/transition is not a native wait/scroll/termination signal.

Absent glyph/page/scroll/resource capabilities make their dependent checks
unsupported. Input capability alone does not observe input_wait: an absent
input_wait signal is unknown. Terminated has no additional capability gate, but
an absent terminated signal is likewise unknown. False is an observed boolean,
not a replacement for missing data. Retain all outcomes in a mixed plan: a passed
image finding cannot make required unsupported/unknown native checks pass.

Exact images have no fuzzy animation tolerance. For animated or dynamic content,
independently specify the frame/state/value and rectangle; isolate changing
surroundings only when the retained claim genuinely excludes them. A completed
runner is not proof that a text animation finished. An unmatched stable image
expectation reports nonidentity, not final clipping; an uncertain checkpoint or
unavailable independent reference remains an unresolved case, not a diagnosis.
Do not select a convenient captured frame or derive its reference after the run.
Native geometry checks still require explicit page_complete true.

The smallest missing control is determined by the declared claim. Repeating an
already calibrated input/page image pair is unnecessary merely because optional
native signals are unavailable. A new image-based case still needs independent
reference provenance and a compatible route; a new semantic wait, scroll or
termination claim needs trustworthy observations and a relevant effective fault
control. Retain earlier ineffective/failed controls with their original results.

Keep whole-record/catalog coverage, normal gameplay, cold boot/save persistence,
hardware, audio and human checkpoint acceptance separate from detector calibration.
Do not wait for #5 closure to hand off an accepted limited detector scope, and do
not infer downstream coverage readiness from that handoff alone.

## Multi-case manifests and coverage handoff

`expectation_manifest(sequence)` builds the agreed container from a nonempty list
or tuple of complete single-case schema-1 expectation documents:

```text
{
  schema_version: 1,
  kind: "RuntimeExpectationManifest",
  finding_id_algorithm: "patchquest-detector-v1",
  cases: {CaseSpec_digest: complete_single_case_plan, ...}
}
```

The entire canonical sorted-key UTF-8 document is pinned by expectation_digest in
RunBinding.expectation_sha256. Sequence/map insertion order does not affect that
pin; ordered checks and every baseline, threshold, mapping, exception and reason
inside each plan remain significant. Changing even a nonselected case changes
the pin. The builder rejects duplicate case digests and returns detached data.
Up to 10,000 cases are supported, matching the shared envelope budget. Empty manifests, unknown fields/schema/ID
algorithms, mismatched case keys and invalid inner plans fail closed. The detector delegates envelope validation to the canonical
expectation_manifest_data helper and uses its FINDING_ID_ALGORITHM constant.
Every inner plan is additionally detector-validated before selection, including
unselected cases.

`detect` selects exactly the current CaseSpec digest from that validated manifest,
while preserving the full-manifest pin in the immutable observation binding and
all returned findings. A missing case cannot inherit another case's checks.
Explicit legacy single-case documents remain supported with their original digest;
use them only when that is the document actually pinned for the capture. Do not
rewrite an existing captured binding to switch documents or pass a digest check.

The declared patchquest-detector-v1 finding ID is detector- followed by SHA-256 of
canonical JSON `[observation_id, check_id, pinned_expectation_digest]`. This keeps
checks distinguishable even when several use the same detector kind or expectation
label. Detector IDs/versions and the selected expectation ID must also match the
full required plan. Namespaced diagnostic check_id remains an annotation; it is
not permission to infer completeness from an arbitrary supplied subset.

The shared contract owner provides expectation_manifest_data,
required_finding_plan(observation, expectations), and the additive coverage opt-in:

```python
from patchquest.runtime_contracts import check_coverage_runtime_links

checked = check_coverage_runtime_links(report, observations, findings,
                                       expectations=expectations)
```

Use these helpers from the same coordinated platform foundation. The common
validator checks the envelope/check identities without importing detector code;
this detector additionally validates every check's parameters. The pipeline
regressions compare actual detector finding IDs and semantic metadata against
the complete required_finding_plan, rather than trusting diagnostic annotations.

Completed/current captures retain assertion not_assessed. With the opt-in full
plan, all required current findings must be present exactly once and passing for
a passed case; a confirmed current required failure can support failed while
missing/unknown checks remain visible. Unsupported, absent or stale results cannot
produce a complete pass. Native execution failures, current binding identity,
provenance, reach-method restrictions and the full declared denominator remain
separate requirements. Legacy coverage calls without expectations retain their
prior rules. The link checker establishes consistency, not actual byte integrity:
resolve and independently verify capture bytes when detecting/reconciling evidence.

The focused tests/test_runtime_pipeline.py uses the actual spawned invented
runner, RuntimeArtifacts/ArtifactState, detector selection and Store/build CAS.
It retains the original regression expectations for distinct case plans and for
passed/failed findings alongside unchanged capture assertions. It also checks
full required IDs, subset/duplicate/cross-case rejection, stale revisions, version
pins and changed bytes. Synthetic subprocess execution is not actual-emulator
control acceptance; the private detector-controls-ready gate remains separate.

Finding persistence uses the supported explicit composition-root Store.build CAS
API: validate each finding against its retained observation, then store findings
separately (for example validation.runtime_findings) alongside unchanged
validation.runtime_cases. The runner does not publish detector outcomes or rewrite
observations automatically. ArtifactState conservatively retains unknown validation
extensions; a new field does not grant evidence deletion. Publication conflicts must
be reconciled without overwriting newer reports. This tested composition is not an
advertised automatic record_findings method.
