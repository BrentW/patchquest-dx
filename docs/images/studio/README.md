# Studio screenshot provenance

These are actual browser captures of Patch Quest DX's unmodified Studio UI,
using an isolated, wholly fictional **Lantern Harbor** documentation project.
They are public documentation assets under the repository's Apache-2.0 scope.
No commercial game's text, ROM graphics, personal paths or launch credentials
appear in them. They contain system-rendered UI text, not bundled font software.

These captures come from the development workspace. The README identifies
runtime inspection and narrative context as previews: their implementation is
awaiting separate code review and publication. The screenshots document that
development state, not a guarantee that every shown control is in this checkout.

## Images

| File | What is shown |
|---|---|
| `studio-overview.png` | Catalogue/progress views and a protected revision in synthetic state |
| `translation-memory.png` | Current/historical translations, human correction precedence and glossary suggestions |
| `browser-builds.png` | A completed real Studio job using an explicit synthetic callback |
| `screenshot-issues.png` | Fictional issues and an uploaded screenshot of the same invented Studio project |
| `runtime-reports.png` | A synthetic grid run through the runtime/report APIs, with assertions and registered captures |
| `agent-collaboration.png` | Coordination records for synthetic clients: a completed handoff, leased work and a dependency |

The build callback validates a snapshot and pixel layout, generates invented
binary bytes and verifies a BPS roundtrip. **It produces no playable ROM.**
“Test ROM ready” is the application's normal validated-job label, not a claim
that this demonstration creates a game. The runtime adapter identifies itself
as **synthetic**. No emulator or AI provider ran for this capture, and the
synthetic client sessions were closed afterward.

The fixture extends the newly authored data in
[`examples/studio-demo.py`](../../../examples/studio-demo.py) with invented
greetings, a lantern workshop, a garden prompt, glossary entries and issue/task
records. The Japanese and English examples were authored for this demonstration;
they were not copied, extracted or anonymized from a private translation project.
The quick-start example does not automatically populate this larger tour or start
its demonstration worker.

## Capture and maintenance

Captured on 2026-10-17 with an already-installed Edge 155 browser and Playwright,
at a 1440 × 1040 CSS-pixel viewport, scale 1, UTC timezone. Browser sandboxing was
enabled. The overview is a viewport capture; other images capture a UI section,
panel or visible build controls. Normal scrolling and expanding details were
used; no application text, CSS or pixels were substituted. The fixture stayed
on loopback and made no external requests.

For future updates:

1. Use a fresh synthetic workspace and current public Studio code. Extend the
   supplied demo with only newly authored fictional records through the supported
   state APIs. Keep the fixture database and capture logs ignored.
2. Exercise the actual documented actions: browse memory, upload a synthetic
   screenshot, queue a bounded synthetic build, register synthetic runtime
   evidence, and create/finish scoped demonstration tasks. Never label synthetic
   output as game/emulator evidence or actual provider execution.
3. Capture the page or relevant element with an already-installed browser.
   Exclude browser chrome, launch URLs, file dialogs and personal paths.
   Preserve readable labels and clearly identify the invented project.
4. Inspect every image and its metadata. Include only the intended PNGs and public
   provenance, never the database, logs, snapshots or session URL.
5. Verify README links, image loading and captions against the implementation.
   Keep Apache documentation and separately scoped Quest Pixel artwork licensing
   distinct if future images include font artwork.

Screenshots demonstrate the UI at capture time. They do not replace regressions,
independent expectations, gameplay checks or human approval.
