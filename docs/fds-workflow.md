# Famicom Disk System storage tools

FDS uses NES-family CPU/PPU hardware with disk-specific storage and BIOS behavior.
Use `patchquest.storage.fds` for its container layer; do not apply cartridge header,
mapper or checksum repair routines to a disk. Game encodings, fonts, script
structures, allocations, BIOS identities and runtime evidence remain private.

## Supported profile

`parse(data)` accepts the conventional contiguous-block representation with
65,500 bytes per side, optionally preceded by a 16-byte `FDS`/0x1a header.
The declared side count must exactly match the file extent. Reserved header
bytes are preserved. Raw images must contain an integral number of sides.
Truncation and mismatches fail rather than silently padding or dropping bytes.

Each side begins with its disk information/signature and file-count block.
Declared files have a 16-byte header, a data marker, and the stored little-endian
payload length. Names remain eight opaque bytes. Duplicate numbers, names and
IDs do not prevent ordinal selection. Zero-length payloads are retained. All
offsets are absolute container offsets; CPU/PPU load metadata is separate.

Only declared files are followed. Opaque side tails are preserved, with a warning
when nonzero; they may contain undeclared files or other structures. Neither zero
padding nor a successful parse establishes free space, CPU ownership or complete
file discovery. QD, CRC-bearing blocks, physical gaps and protection-specific
formats are outside this profile. Unknown file types are retained as integers.

`Image.reconstruct()` returns the immutable captured bytes without normalization.
`inventory(data)` adds JSON-compatible metadata and distinct container/file
payload SHA-256 identities. Reports can expose private names/data: keep them in
the explicitly selected private project.

```sh
python tools/patchquest.py fds-inspect /private/project/source.fds
```

This command reads only the named file. It does not scan folders, import private
runners, start an emulator, download firmware, infer an encoding or repair input.
The existing `inspect` command retains its cartridge behavior.

## Guarded payload edits

`patch_file(data, expected_sha256, side, ordinal, offset, expected, replacement)`
returns new bytes for one equal-length edit inside one explicitly selected stored
file. Selection uses zero-based side/ordinal, not ambiguous names or file IDs.
The complete source hash and original expected bytes must match. Boolean/negative
selectors, empty edits, length changes and cross-file writes fail. Reparsing must
preserve every structural observation. Headers and opaque tails are not editable
through this API; resizing needs a separately validated private serializer.

Read originals with `load_source` and write derivatives through an explicit
`OutputPolicy.write_new`, listing originals as protected inputs. Preserve archive,
member and payload hashes separately. BPS works on exact disk-container bytes;
verify reconstruction and wrong-source rejection. Storage tests cannot certify
BIOS loading, disk changes, saves, text rendering or physical hardware.

## Provenance and tests

This independent implementation uses public field definitions, checked against
the [Mesen FDS loader](https://github.com/SourMesen/Mesen2/blob/master/Core/NES/Loaders/FdsLoader.cpp),
its [side-capacity declarations](https://github.com/SourMesen/Mesen2/blob/master/Core/NES/Loaders/FdsLoader.h),
and the [FCEUX FDS loader](https://github.com/TASEmulators/fceux/blob/master/src/fds.cpp).
No emulator source is copied. Unlike permissive emulator loading, this inspection
profile rejects mismatched extents instead of resizing input. No game-derived
layout, byte pattern, text, fixture, firmware or screenshot is included.

`tests/test_fds.py` authors its own disk information, names and payloads. Tests
cover raw/headered multiple sides, duplicate identities, opaque tails, malformed
blocks/extents, immutable snapshots, guarded edits, exact BPS reconstruction,
exclusive output policy and the explicit CLI. They need no private media.
For actual projects, follow the [project contract](project-architecture.md) and
[runtime evidence workflow](runtime-evidence.md).
