# Synthetic project

This example is independently authored demonstration data. It contains no commercial ROM, extracted text, game font, original pointer table, private hash or renderer hook. It is **not playable**.

A deterministic 32 KiB image uses standard SNES header definitions, an invented one-byte alphabet, one toy file-offset pointer and two arbitrary framing bytes. The demonstration changes LANTERN to BEACON!, recalculates the checksum, verifies allowed changes and BPS reconstruction, and lays out independently authored text with Quest Pixel.

```powershell
python examples/synthetic-project/project.py --platform . --workspace .local/projects/synthetic-demo
```

Use a fresh workspace. It also works outside the checkout and from another current directory when explicit paths are supplied. Tests exercise both placements, including spaces in paths. Generated files remain private/ignored; do not use this toy format as evidence about a real game's encoding or mapping.

The example code and invented data use Apache-2.0. Its Quest Pixel preview has the separately scoped CC BY 3.0 font treatment. Generated outputs include both license texts, font credit/provenance and an explicit output scope; retain the applicable notices when redistributing any part.
