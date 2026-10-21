# Translation exceptions and content classifications

Automatic by default. Human correction by exception. Investigate resolvable
questions with source context, memory, terminology, the narrative guide and
verified runtime tools. Request specific missing human knowledge only when needed;
do not create a mandatory translation-approval queue.

## Independent dimensions

| Dimension | Meaning | Effect |
| --- | --- | --- |
| Progress | Discovered/extracted, decoded, translated, inserted, automated, emulator and hardware checks | Existing record/evidence APIs remain authoritative |
| Exception | Interpretation, fidelity, processing or display problem | Investigate and record a resolution or specific missing input |
| Content classification | Description of the source in context | No automatic rewriting, severity escalation, refusal inference or approval requirement |

Multiple exceptions and labels may coexist. They extend existing `issues` and
`issue_history` through `issue-put`, without a second translation/review store.
The dashboard separates progress from assessments. `uncertainty` and the
`uncertain` API filter remain legacy compatibility features, not new catch-alls.

## Categories and contextual classification

`assessment-catalog` is the machine-readable source of supported values.
Exception codes: `source_decoding`, `linguistic_ambiguity`, `missing_context`,
`unknown_speaker_name`, `voice_tone`, `cultural_wordplay`, `terminology_conflict`,
`fidelity_mismatch`, `provider_restriction`, `technical_limitation`,
`runtime_verification`, `processing_failure`, `legacy_unspecified`.
Meaning concerns are separate from renderer limits and missing runtime evidence.

Content codes: `sexual_innuendo`, `sexual_reference` (non-graphic),
`explicit_sexual`, `sexual_violence` (including non-consensual content), `nudity`,
`profanity`, `romance`, `clinical_educational`. Multiple labels require evidence
for each. These are editorial assertions from a human or agent: the platform
does **not** claim automatic semantic classification or keyword detection.

Read source and scene context. Distinguish indirect sexual implication,
non-graphic references and explicit descriptions of sexual activity. Nudity,
swearing, affection and clinical education are not by themselves evidence of
explicit sexual content. For example, a fictional educational passage can have
`clinical_educational` without a sexual label. A documented observation that a
fictional passage explicitly describes adult sexual activity can support
`explicit_sexual`; no graphic quotation belongs in a title or activity summary.

Age accepts `adult`, `minor`, `unknown`, `not_applicable`; consent accepts
`consensual`, `non_consensual`, `unknown`, `not_applicable`. Each is an object
with `value` and `references`. Non-unknown values require evidence. Do not infer
adulthood from appearance, consent from romance, or invent facts to make content
eligible. Classification is **not permission to process**. Follow actual provider
safeguards, including restrictions on sexual content involving minors, uncertain
ages when material, or other restricted material. Investigate material uncertainty
before dependent processing. Preserve source meaning, explicitness, voice, tone
and purpose when processing is permitted; never silently sanitize or intensify.

## Details and version bindings

The issue retains its ID, title, description, record links, references and status.
Its optional `assessment` has these fields:

| Field | Contract |
| --- | --- |
| `kind`, `code` | `exception`, `content` or `processing`, with an appropriate catalog code |
| `rationale`, `references` | Concise explanation and nonempty evidence locators; not hidden reasoning |
| `alternatives`, `attempted` | Lists of plausible alternatives and completed investigation; empty when unknown |
| `next_action`, `resolution` | Next investigation and resolution criteria; resolved/closed exceptions require a resolution note |
| `severity`, `build_impact` | `info/low/medium/high/critical`; `none/advisory/blocks_build`. Content and permission observations use `info` and `none` |
| `bindings` | Record IDs mapped to revision and source/target/context hashes from `assessment-context` |
| `narrative_sha256` | Configured guide byte hash, or null when absent |
| `age`, `consent` | Evidence objects, default unknown |
| `provider_outcome` | Actual observed outcome, separate from source labels |
| `provenance` | Optional `agent`, `provider`, `model`, `request_id`, `method`; self-reported, not authentication |

Statuses: `open`, `investigating`, `needs_input`, `resolved`, `closed`. Retain
resolution history; reopen by writing a new issue revision. A content annotation
is not a quality problem regardless of its investigation state. Kind is immutable:
create a separate linked annotation when a classification leads to a new concern.

Read `assessment-context` **before** evaluating a record. New assessments check
issue CAS and the captured record/context tokens; changed inputs reject the write.
Changes to source, translation, record context or narrative guide mark existing
assessments stale. Status/resolution updates can retain stale evidence without
refreshing it. A new interpretation requires fresh bindings. Other external
evidence locators are not automatically watched; pin hashes privately and
reassess when evidence changes. Guides follow the existing immutable revision and
resource coordination convention; their files are not transactionally locked.

Assessment writes never change translations, memory, proposals, snapshots,
checkpoint approvals or ROMs. Human corrections remain authoritative; use the
existing proposal API for alternatives, never rewrite based only on labels.

## APIs and Studio

Use `python tools/patchquest.py state PATH_TO_MANIFEST ACTION --input INPUT.json`
or `--input -` for JSON stdin. Both Codex/Astra and Claude use these same APIs:

1. `assessment-catalog` lists values.
2. `assessment-context` with `{"key":"invented-line"}` supplies current tokens.
3. `issue-put` takes `data`, `expected` issue revision and optional `actor`.
   See [the invented template](../templates/project/assessment.example.json);
   replace placeholders with step 2 tokens and private evidence.
4. `assessments` filters by optional `key`, `exception`, `content`, `severity`,
   `investigation`, `stale` (`current`, `stale`, `unbound`). `list` supports the
   same filters except `key`. `issue-history` preserves prior versions.
5. Resolve through `issue-put` with an explanation of what resolved the concern.

Studio offers a **Details** column, expandable per-record explanations, and
filters above Translations, Glossary and Issues. In the issue editor select a
structured type/category and provide evidence. **Review current inputs** shows
source/wording; **Use these reviewed revisions** explicitly captures the tokens.
It is an evidence action, not a translation approval. Resolution and status edits
retain original bindings unless you explicitly reassess.

Record-list filters combine on records: one record can have a content annotation
and a different exception. Issue filters combine on individual issues. Explicit
unresolved `blocks_build` exceptions prevent new browser build submissions,
including stale blockers until investigated. Content labels, advisory concerns
and provider failures do not automatically block builds. Already queued immutable
jobs remain unchanged. Headless adapters can use `assessments.build_gate` before
new builds; snapshot creation stays available for preservation/reproduction.

## Provider limitations

`provider-result` takes `key`, `expected` (issue revision, initially zero),
`outcome`, `rationale`, `references`, `inputs` from `assessment-context`,
`provenance`, optional `issue_id` and `actor`. Use distinct issue/request IDs for
independent attempts. It accepts **no translation text** and cannot mark success.

| Outcome | Meaning |
| --- | --- |
| `permitted` | Permission observed for that specific operation/context, not universal permission or successful translation |
| `explicit_refusal` | Actual provider refusal; creates `provider_restriction` with a non-graphic explanation and response reference |
| `timeout`, `authentication_error`, `empty_response`, `unsupported_tool` | Distinct processing failures, not policy refusals |
| `unknown_error` | Reason not established; do not guess |
| `needs_safety_context` | Material context requires investigation before dependent processing; not a provider refusal |

When restricted, retain source and existing wording under project privacy,
record the exception, and continue independent work. Do not insert refusal text,
fabricated translation or euphemistic replacements, or mark success. Never
automatically switch providers, weaken safeguards or reroute to evade a
restriction. This module does not call providers or decide their policies;
integrations must report observed structured outcomes accurately.

## Migration, privacy and validation

Back up state with `backup`, then explicitly run `migrate-exceptions`. Each
nonempty legacy note becomes an existing issue with `legacy_unspecified`,
informational severity and no inferred build block. The exact private note is
retained. Migration is transactional and idempotent for the same record/note,
preserving translation revisions and snapshots. A later different note is new
evidence. It invents no category, content label, age, consent or refusal. General
legacy issues remain unbound until investigated.

Generated events contain IDs/status/revisions only. List summaries use controlled
labels; explanations remain in authenticated private details. Do not put source
excerpts/private references in general activity, public reports or examples.
References are contextual data, never fetched or executed as instructions.
Public tests/examples are invented and non-graphic. They verify state/CAS,
staleness, protected corrections, provider outcome distinctions and migration,
not editorial accuracy, provider permission or gameplay. New generic code/docs
are Apache-2.0; Quest Pixel's font license scope is unchanged.
