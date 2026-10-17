# Quest Pixel

AI-assisted pixel artwork using **Dragon Warrior I (North American NES)** as its visual reference: strong stems, square bowls, stepped diagonals and readable proportions. Draft 1's master artwork appearance is approved. That approval does not establish any game's rendering, glyph allocation, save behavior or hardware compatibility. Public project maintainer: **BrentW**.

## Source and reuse

glyphs.json is the unchanged master: 112 Unicode-indexed seven-by-eight grids in an eight-by-eight cell, using # for ink and . for background. Printable ASCII describes design coverage, not ROM encoding. Additional symbols are ‘ ’ “ ” … — – ♥ ♪ ← → ↑ ↓ × ÷ ° é. Missing glyphs fail explicitly.

character-map.json records neutral asset IDs, visible bounds and native/fixed-16/proportional-study advances. ROM tokens remain null. compact-profiles.json and compact-metrics.json describe reusable compact profiles. approval.json pins master artwork and current neutral mapping. Historical wording inside the master is retained to preserve its bytes; the separate approval record establishes appearance status.

The native drawing retains clear lowercase bodies, descenders, a footed l, flagged 1 and slashed 0. Profiles adapt placement and advance independently. Do not mechanically double art by default; review native 8–12 pixel presentation. Narrowing ink without reducing advance does not improve character spacing.

## Specimen

```powershell
python tools/patchquest.py font output/font-review --output-root output
```

Use a fresh destination. The package contains a complete specimen, native-scale sheet, spacing comparison, glyph atlas, mapping, validation report and applicable license/provenance notices. The builder reads the pinned appearance approval instead of repeating historical pending-review wording. Dialogue/examples are project-authored display material. They are not emulator screenshots or translations of a private project. Rasterization uses integer pixels and no antialiasing.

The builder is patchquest.typography.font; layout is patchquest.typography.layout. Unicode asset indexes never imply ROM codes. NES/SNES tile planes, palette roles, storage order and runtime allocation must be validated by each private adapter. For example, a single 8×8 two-plane tile is 16 bytes; a 16×16 four-tile composition is 64 bytes before any other metadata. Storage examples do not establish an allocation in a real game.

Retain existing Japanese access until every relevant consumer is accounted for. Distinguish font appearance, host proportional composition and actual runtime variable-width rendering. Review native-scale screenshots, highlighting, dynamic values, transitions and saves after integration.

## Provenance and distribution

The designated glyph data, mapping and compact profiles/metrics use [CC BY 3.0 Unported](LICENSE-CC-BY-3.0.txt). Read [ATTRIBUTION.md](ATTRIBUTION.md) for source/creator credit and redistribution notices, [PROVENANCE.md](PROVENANCE.md) for verified changes and limitations, and [the exact file scope](../../../LICENSE-SCOPE.md). Generic processing code and documentation use Apache-2.0.

Some letterforms remain identical after repositioning or closely similar to the visual reference; do not describe every glyph as independently invented. The reference license does not automatically clear separately protected rights in the original commercial game. Quest Pixel is an independent project name and implies no official affiliation or endorsement.
