# Quest Pixel provenance

Quest Pixel is an AI-assisted bitmap-font project created under human visual direction and review. Its reference and creator are credited in [ATTRIBUTION.md](ATTRIBUTION.md). Public project maintainer: **BrentW**.

## Artwork and approval

The unchanged approved master is `glyphs.json`: 112 explicit Unicode-indexed 7×8 drawings in 8×8 cells. Its SHA-256 is `e4d9b7b472c39e5d11eba154b5944008bca9a774c32256ab5b6864e09864f735`. `approval.json` records draft 1's approved appearance and pins the source and mapping. Historical review wording within the master remains intact to preserve its bytes; it is superseded for appearance status by the verified approval record.

Appearance approval does not validate any particular renderer, ROM allocation, save behavior or hardware integration. Character identifiers, profiles and measured advances are separate from game encodings and allocations.

## Recorded creation and differences

The retained development record describes grids entered for this project using the online reference. No third-party font file, font-program source, ROM glyph dump or reference preview raster is incorporated into the distributed font assets. The grid representation, rasterizer and layout implementation were developed in the project. A program that renders the grids is not evidence that their shapes were independently invented.

Verified differences include narrower proportions in many capitals, a different barred capital I, a descending j, footed l, slashed zero and additional punctuation/symbol coverage. M/W remain close to the reference. Lowercase y and period have matching ink silhouettes after repositioning within the cell; y's descender placement should not be described as an independently invented silhouette. A flagged numeral 1 was already present in the reference. Additional coverage is not claimed to be novel solely because it was absent from the compared preview.

The comparison used a public visual preview, not the reference's font-file character mapping, encoded advances or original ROM. Detailed comparison evidence remains outside the public distribution. No pixel-difference threshold establishes copyright clearance or independent authorship.

## Rights and license scope

Human direction and approval are documented; human authorship of every pixel is not asserted. For distribution, Quest Pixel is treated as an adaptation under [CC BY 3.0 Unported](LICENSE-CC-BY-3.0.txt), with applicable upstream terms retained and project contributions licensed only to the extent the contributors can grant rights. Ordinary letterform shapes, facts and purely AI-generated expression are not claimed as exclusive property merely through this notice.

This scope covers `glyphs.json`, `character-map.json`, `compact-profiles.json` and `compact-metrics.json`, plus applicable font material in their derivatives. Generic font-processing Python code and project-authored documentation use Apache-2.0. The generator's license does not override the font's license.

The reference's license listing does not itself establish rights in all underlying commercial-game material. No official affiliation or endorsement is implied. Future changes must preserve accurate source credit, identify actual changes and retain their license basis without silently replacing the approved master.
