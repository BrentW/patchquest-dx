# Runtime review in Studio

The Runtime review view presents the existing
[catalog coverage receiver](runtime-catalog-coverage.md), original observations,
findings and private captures. It does not run an emulator, add a detector,
translate text or approve verification. Opening evidence never changes its result.

## Explicit server configuration

The local composition root creates `runtime_review.ReviewProvider` with an
explicit existing Store or ProjectContext, the same trusted group envelopes used
by `runtime_coverage.reconcile`, an independently reviewed admission callback and
the existing RuntimeArtifacts service. Register that provider through
`StudioServer(..., runtime_review_providers=[(manifest_path, provider)])`.
Registration is server configuration; browser input cannot select a path,
callback, producer receipt, project module or alternate database.

The optional provider uses the existing Studio token, origin checks and opaque
project selector. An unconfigured project shows an unavailable explanation. It
does not fall back to another project's provider. The server exposes two reads:

- `/api/runtime-review`: optional opaque group/build, disposition, method and
  purpose filters, with offset and limit. Limits are 1–200, default 50; Studio
  starts at 20. The provider copies the receiver's validated counts, denominators
  and per-case decisions. It supplies bounded gap and historical-context previews
  rather than repeating entire catalogs on every page.
- `/api/runtime-review-image`: exact evidence ID and SHA-256 only. The selected
  provider's evidence allowlist and immutable resolution determine availability.
  No filesystem path is accepted. The frontend fetches with project authentication
  and uses temporary blob URLs, revoking them on refresh or navigation.

`ReviewProvider.read` runs the existing reconciliation with server-owned inputs
and rechecks catalog freshness before returning. It retains exact binding groups,
tested revisions, current revisions, original observation/finding identities,
original captures and superseded observations. Raw admission references and input
paths are not copied into browser presentation. The original receiver result and
source bundles remain authoritative; presentation previews do not replace them.
Attempts not counted in the selected purpose/method remain visible in their own
detail section. Unadmitted captures cannot create a pass, and superseded evidence
is retained rather than silently removed.

Image reads are available after a successful project review read establishes the
allowlist. They reverify exact source bytes rather than trusting a cached image.
A missing, changed or unrelated image stays unavailable. Still images cannot
establish animation, timing, unseen glyphs or gameplay behavior.

## Separate views and historical evidence

Known-catalog translation progress comes from the existing progress API. Each
receiver binding group retains its own synthetic renderer, actual-renderer and
ordinary-gameplay sections, including denominators, all dispositions and unknown
extraction scope. No percentages are summed across groups. There is no whole-game
verified percentage or automatic record award.

Editorial review is labeled separately and links to the existing verification
views. A runtime report does not supply an invented aggregate language-review
rate. A renderer case reached by ordinary buttons remains renderer evidence
unless independently admitted for a complete gameplay purpose.

The historical case decision remains unchanged when a saved contributing record
changes. Current catalog contexts supplied by the receiver show the stale state;
the Needs recheck filter finds those contexts. Later wording is not copied into
old observations. A changed catalog receipt clears old comparison selections.

Historical investigation contexts are a separate bounded preview, with retained
legacy execution status and revision information. They are not executable
CaseSpecs, never enlarge the new case denominator and are not relabeled never run.
Full historical inventories remain in their existing private evidence records.

Select at most two case views for an explicit comparison. Exact binding,
CaseSpec, starting-state, reach-method and capture-frame differences are visible.
Missing starting-state metadata stays unknown; matching fields do not prove
interchangeable states or matching animation timing. Original full-size captures
remain available rather than being replaced by scaled review thumbnails.

Prepare issue creates an unsaved draft in the existing issue workflow. It carries
the tested build, exact contributing translation revisions, original observations,
capture hashes and finding IDs as evidence links. Current wording and structured
assessment bindings must still be inspected through the existing context API.
Historical references are never silently rebound to current revisions. A draft
does not save an issue or a proposal, change translations, or award verification.
Normal Studio unsaved-draft protection applies. Saved wording opens the existing
record editor, where protected human corrections retain their normal safeguards.

## Private contact-sheet preparation

`write_contact_sheets(items, resolve_evidence=..., artifacts=...,
destination=..., page_size=6)` creates one new private HTML package outside the
artifact directory. This is an explicit trusted preparation operation, never
performed by a browser GET. The caller selects a bounded receiver-derived set.
Source groups, builds, scenes, message/page order and frame order are retained.
The same capture selected for different purposes or methods retains each scope
association and its own disposition. Captions identify purpose and method;
`source_count` counts retained associations rather than unique PNG byte hashes.

Each image embeds exact verified original PNG bytes at native dimensions and
links to the original bytes. No pixels are synthesized or modified. The package
contains a provenance sidecar with original EvidenceRefs, run/observation/frame
associations, tested revisions, method, purpose and recorded disposition. HTML
pages and the sidecar are registered through the supplied RuntimeArtifacts graph.
Their producer method is static; a derived sheet is never emulator evidence.

The destination must be fresh and disjoint from artifact storage. Inputs are
verified before it is created. Bounds are 200 selected views/images, 32 MiB total
input PNG bytes and 1–12 images per page; the artifact service independently
enforces its admission budget. Existing outputs and originals are never replaced.
Partial failures remain for diagnosis and do not return successful completion.

An installed browser may render this private package for inspection. A derived
PNG preview can be explicitly registered and supplied as a prepared contact-sheet
reference, with its original HTML/provenance associations retained. Generating or
viewing it does not select screenshots for publication, alter captions/spoiler
metadata, mutate the catalog or refresh a shared Studio server.

The graph owner must provide the real complete reference graph for its dedicated
artifact store. The public tests' empty graph is only for their invented temporary
store, never a production fallback. No new authoritative state database is added.

## Validation and limits

Focused tests cover copied coverage decisions, stale contexts, missing purpose,
failed evidence, immutable PNG resolution, project isolation, refused filters,
bounded large inventories and exact contact-sheet bytes. The optional browser
check uses invented projects and installed browser software for pagination,
keyboard comparison, current/historical labels, issue-draft links, mobile layout,
cross-project isolation and absence of browser writes. It installs nothing.

Synthetic tests establish presentation and orchestration behavior. Actual private
sheet inspection is separate from those tests; it does not establish new native,
gameplay, hardware, language-review or checkpoint acceptance.

```text
python -B -m unittest discover -s tests -p test_runtime_review.py -v
node tools/runtime_review_browser_check.cjs
```

The browser check accepts existing `PYTHON`, `PLAYWRIGHT_MODULE` and
`BROWSER_EXECUTABLE` overrides and writes its evidence under
`RUNTIME_REVIEW_EVIDENCE` when supplied. It does not restart the shared Studio.

## Text coverage and discovery

Expand **Text coverage & discovery** within Runtime review to browse candidate
catalog gaps, known records without a captured context, ambiguous mappings,
preserved source text, graphics text and enumeration discoveries. Category
buttons and bounded pages keep this separate from the case/capture grid. The
selected build group applies to both; case disposition/method filters apply
only to cases, not these cross-method investigation leads.

**Create investigation issue** explicitly saves a lead into the existing Issues
workflow. Opening the view performs no writes. The server resolves the opaque
candidate against fresh trusted coverage; it accepts no browser reports, paths,
callbacks, source text or translation changes. Changed catalog/build inputs
reject the save. Repeated creation opens the original issue without overwriting
its notes, status or history. **Open linked issue** continues ordinary revisioned
triage. No verification or extraction-completeness claim follows.

The optional provider methods `gaps(store, params)` and
`gap_issue(store, params, actor=...)` share its project guard and serialized
evidence access. Existing read-only providers remain compatible; absent methods
produce an unconfigured view. Authenticated GET `runtime-gaps` and POST
`runtime-gap-issue` retain Studio's existing origin/token/project checks.
See [catalog coverage](runtime-catalog-coverage.md#discovery-review-and-issue-handoff)
for trusted composition and atomic issue admission.

`node tools/runtime_gaps_browser_check.cjs` verifies this flow against invented
projects. It uses the same installed-browser overrides and optionally
`RUNTIME_GAPS_EVIDENCE` for its private results.
