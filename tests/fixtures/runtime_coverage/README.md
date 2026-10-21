# Runtime contract conformance fixtures

`conformance.json` was independently invented for this platform contract. It uses
no game text, ROM bytes, addresses, artwork, real screenshots, private hashes or
runtime traces. IDs and text are fictional. Hashes were computed from invented
labels or the literal synthetic capture payload below.

The capture payload is `Invented capture bytes. Not an emulator frame.` encoded
as ASCII, with no trailing newline. Its media type is `application/octet-stream`;
it is deliberately not presented as an image or actual emulator output.

The `connectors` object supplies one normalized example of each v1 record.
`observations` supplies success, failure, partial, unsupported and stale cases.
Every example uses synthetic provenance. Tests may alter declarations to check
that cross-record validation rejects invalid promotions; such declarations are
not actual execution evidence.

Consumers can copy the values in memory and validate them with
`patchquest.runtime_contracts.validate`. Keep the shared fixture baseline stable;
new fields or interpretations require compatibility tests and coordinated schema
changes. Private adapter cases must never be added to this directory.

These original fixtures and documentation are covered by the repository's
Apache-2.0 platform license.
