# Publication readiness

The publication unit is the reviewed, game-agnostic platform source. Private projects, .local/, originals, artifacts and the Git object database are never included automatically.

Before any authorized commit or release:

1. Run public tests and the independently authored synthetic example from a clean candidate export with no private registry or projects. Review imports, source/asset paths and command examples.
2. Audit exact working candidates and staged blobs, including tracked ignored files. Use local privacy terms/fingerprints and inspect distinctive code/fixture provenance manually; names alone are insufficient.
3. Inspect all Git refs and objects, including internal tree snapshots and unreachable blobs. Zero commits and an empty index do not establish clean history. Preserve useful objects privately; do not erase them to silence warnings.
4. Export only allowlisted reviewed source files, compare an exact export manifest and rerun tests. Exclude .git, .local, private projects, generated outputs and binaries. Do not use filesystem copies of .git or mirror pushes.
5. Verify [the approved license boundaries](../LICENSE-SCOPE.md): Apache-2.0 platform, CC BY 3.0 Quest Pixel and BrentW maintainer credit. Check full license texts, attribution, provenance and generated package notices. Preserve source-reference credit; appearance approval is not rights clearance. Do not invent ownership or a personal email; Git commit email awaits a verified GitHub noreply address.
6. Obtain explicit approval for commits, remotes, pushes or publication. Preparation and passing tests do not authorize those actions.

Use `python tools/patchquest.py audit --history --report .local/logs/review.json` with a fresh private report path. Findings identify locations/categories rather than printing matched secrets; filenames and object IDs are themselves private report data. Scanning is heuristic, does not decode every archive or prove absence of secrets, and never rewrites Git.

Documentation screenshots are a deliberate, reviewed exception to excluding
generated binaries. Use independently authored synthetic content, inspect every
image and its metadata, retain public provenance, and include only exact reviewed
paths/hashes in the export manifest. The auditor still flags PNGs as restricted
binary content; record the review disposition instead of suppressing that check
or allowing an entire image directory automatically. Never apply this exception
to game frames, private evidence, ROM assets or capture logs. See the
[Studio screenshot provenance](images/studio/README.md) for the current examples.

If the local repository has private objects, a fresh publication checkout made from the reviewed source export is preferable for a later authorized release. Preserve the working repository and its private history separately. Do not create a public commit merely to test this workflow.

The platform has no bundled game ROMs, private translation recipes or guarantee of any game's playability. Public tests establish generic behavior only. Independent BPS interoperability, individual-game emulator checks and hardware validation remain separate project/distribution responsibilities.
