# D88 disk containers

For Famicom Disk System containers, use the separate
[FDS storage workflow](fds-workflow.md). Disk formats have distinct structures;
neither tool selects a game or infers its text encoding.

`patchquest.storage.d88` provides lossless inspection and equal-length guarded
sector-payload edits. It does not select a machine, boot a disk, discover a
collection, decode text, or infer a filesystem. Private runners import this
module and own the source identity, disk selection and game-specific consumers.

## Supported profile and preservation

`parse(data)` accepts bytes-like data and returns an immutable `Image` containing
`Disk` and `Sector` observations. The supported profile has a 0x2b0-byte header,
164 little-endian track offsets, and 16-byte sector headers. Concatenated disks
are walked using each declared disk size. Offsets in returned observations are
absolute positions in the original container; track offsets in its headers are
relative to the containing disk. Disk index, track slot and sector ordinal are
zero-based. Track slots do not imply verified physical geometry.

Sector data length comes from its stored 16-bit length, independently of CHRN's
nominal size. Size disagreement produces a warning. Zero-length payloads,
duplicate sector IDs, sparse or physically reordered tracks, status flags,
reserved bytes and opaque track tails are preserved. `Image.reconstruct()`
returns the captured original bytes, without regeneration or normalization.

Truncated headers, invalid disk extents, aliased/out-of-bounds track offsets,
inconsistent or impossible sector counts, and sectors crossing track boundaries
raise `ValueError`. Trailing bytes that cannot form another supported disk are
rejected. Older shorter track tables and converter-specific repair conventions
are unsupported. No fallback guesses a different size or fixes an original.
Structurally accepted data is not proof of valid geometry or successful boot.

The implementation was independently written using container field definitions
and the [MAME D88 loader](https://github.com/mamedev/mame/blob/master/src/lib/formats/d88_dsk.cpp)
as a behavioral reference; no emulator source or third-party disk bytes are
included. In particular, MAME consumes the stored sector length. The
[secondary format description](https://www.pc98.org/project/doc/d88.html)
documents contradictory size conventions seen in images. Preserve disagreements
for investigation; a repair policy needs separate source and runtime evidence.

## Guarded edits and output

`patch_sector(data, expected_sha256, disk_index, track_slot, ordinal, offset,
expected, replacement)` returns new immutable bytes. It checks the complete
source SHA-256, explicit nonnegative integer selection, nonempty expected bytes,
equal replacement length and containment in one stored payload. Ordinal selection
avoids ambiguity when multiple sectors have identical CHRN values. The result is
reparsed and all parsed structure must remain equal. The function does not write
files or modify header protection flags. It does not establish ownership of a
sector's contents: private adapters must verify that separately.

Read an explicitly selected source with `patchquest.core.edits.load_source` and
save derivatives through `patchquest.core.context.OutputPolicy.write_new` in a
fresh output destination, declaring originals as protected inputs. Preserve
archives and individual image hashes separately. Multiple edits must retain
original expected-byte evidence and reject conflicting ranges in the private
recipe; this API intentionally performs one edit per call.

The generic BPS implementation can reconstruct exact disk-container bytes as
well as cartridge bytes. Synthetic tests verify deterministic reconstruction,
wrong-source rejection and corrupt-patch rejection. That does not establish
independent patch-tool interoperability, emulator acceptance, disk-protection
fidelity or distribution rights. Do not apply cartridge checksum/header repair
to a disk image. Keep derivative disks and patches private under the
[project contract](project-architecture.md).

## Validation scope

`tests/test_d88.py` uses independently invented byte fixtures, including malformed
containers, duplicate sector IDs, concatenated disks, physical track ordering and
exclusive output checks. It needs no commercial media, firmware or emulator.

Real projects must additionally pin machine variant, boot mode, emulator binary
and configuration, firmware and each source disk; protect originals from disk
writes; capture actual cold boot and text/input evidence; and test disk changes,
saves and progression. Follow [runtime evidence](runtime-evidence.md). A parser
round trip or synthetic patch test is not gameplay verification. Filesystem,
loader, encoding, font, compression and text-control discoveries remain private
unless independently generalized and tested.
