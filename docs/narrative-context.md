# Narrative tone, character voice and emotional context

Use this framework before a substantial translation batch and revisit it when
new source evidence changes the interpretation. The goal is the original work's
personality, meaning and emotional effect in natural English. A playful work can
contain grief; a reserved speaker can be delighted. Neither observation licenses
an agent to make every line cheerful or every voice interchangeable.

## Read context at four levels

| Level | Observe | Distinguish |
| --- | --- | --- |
| Work | Atmosphere, types of humor, emotional range, register, dramatic intensity, genre and stylistic conventions | Narrative tone from a scene's mood, humor from low stakes, visual style from a character's motives |
| Scene | What changes, who knows what, pauses/reactions, tension, relief and sincere interruptions | An intentional contrast from inconsistent writing; source order from an unverified assumption about gameplay order |
| Character | Recurring vocabulary, sentence rhythm, politeness, directness, expressiveness and behavior across situations | Relatively stable baseline, outward persona, development and temporary emotion |
| Line | Speaker/listener evidence, relationship, social setting, emotional state, implied meaning and communicative intent | What someone feels from what they want to accomplish: reassure, tease, hide, threaten, persuade, deflect, etc. |

Describe these in ordinary language. No numeric emotion scores or mandatory tag
matrix is needed. Do not infer a speaker from the previous record, a portrait
alone or a dynamic name placeholder. An unknown identity stays unknown.

## Establish an evidence-backed foundation

1. Read a representative source sample across independent scenes and functions:
   routine narration, choices, friendly interaction, conflict, humor and serious
   passages where present. Include negative evidence and exceptions to the
   apparent dominant tone. A sample is not a full-game review.
2. Separate directly observed wording/behavior from interpretation. Give each
   claim a source reference and describe uncertainty. A partial transcription
   or dictionary guess is not an authoritative reading of the original glyphs.
3. Compare repeated character behavior across different situations. Ten lines
   in one angry exchange are not ten independent demonstrations of a baseline.
   Qualify a limited sample instead of creating a rigid archetype.
4. Record scene changes in mood and separate participants' perspectives. A joke
   may mask fear, but that subtext needs evidence; do not invent the explanation.
5. Preserve contradictions, ambiguity, development and meaningful departures
   from an established voice. Revise a profile when evidence changes; retain its
   previous revision and explain the changed interpretation.

Visual presentation is useful supporting evidence, not proof of personality or
intent. Label user reports, original screenshots, static reconstructions and
actual emulator observations accurately. Music or sound may inform a claim only
when genuinely captured/observed; a silent image provides no audio evidence.
This framework does not implement emulator automation.

## Translate and review

Read the relevant guide alongside current records, adjacent source, translation
memory and the contextual glossary. Profiles guide judgment; they do not dictate
catchphrases or automatically transform text. Preserve Japanese social dynamics,
levels of politeness, irony, humor, implication and deliberate indirectness in
idiomatic English. Avoid unnecessary Westernization, anachronistic slang,
artificial enthusiasm, added profanity, invented motives and literal phrasing
that loses the scene's effect. A gruff speaker can sound happy without acquiring
an unrelated voice; a lively speaker need not joke during a serious exchange.

For a batch, review:

- Meaning, referents, speaker attribution and the purpose of each exchange.
- Voice drift: compare a character across independent scenes and different
  emotions, and compare different characters inside the same scene.
- Register and relationships: preserve deference, familiarity, distance,
  challenge or reassurance without inventing social facts.
- Humor and subtext: retain setup, misunderstanding, reaction and timing;
  document wordplay compromises without inserting explanations into dialogue.
- Emotional trajectory: keep shifts into tension, relief, awkwardness or
  sincerity; do not smooth everything toward the work's dominant mood.
- Controls and presentation: preserve substitutions, intentional emphasis,
  page/wait behavior and the current source's uncertainty.

Flag a concrete concern with a source reference, affected translation revision
and an optional suggested alternative. Do not automatically rewrite an approved
translation during a context audit. Never replace a protected human correction
without authorization. A human-approved flourish is not evidence that every
future line should receive similar additions. Use the existing proposal/CAS
workflow for separately authorized edits, not a second translation database.

Tonal decisions determine wording. The layout planner adapts that wording; it
must not silently shorten, intensify or neutralize it to fit a box. Unresolved
technical overflow remains a build limitation, not editorial permission.

## Lightweight private guide contract

The optional `resources.narrative_context` manifest entry points to a versioned
UTF-8 JSON guide **inside the explicitly selected private project**. Copy
[the invented example](../templates/project/narrative.example.json), replace its
fictional evidence and source hash, and save it as, for example,
`docs/narrative/context-v001.json`. Do not add real game content to the template.

```json
{"resources": {"narrative_context": "docs/narrative/context-v001.json"}}
```

Schema 1 contains:

- `schema`, positive `revision`, the manifest's `source_sha256`, and `previous`.
  Revision 1 uses `previous: null`; later revisions name the preceding file's
  project-relative `path` and exact byte `sha256`.
- `evidence`: uniquely identified observations with `kind` (`source`, `visual`,
  `runtime`, `user_report` or `synthetic`), project-relative `reference`, precise
  `locator`, associated `record_ids`, `observation` and `limitations`. An optional
  `sha256` pins the referenced artifact. These files are not executed or fetched
  by the reader; verify their content separately.
- `work`: `claims`, `guidance` and `uncertainties`. Each claim has a free-text
  `aspect`, `kind` (`observation`, `interpretation` or `unknown`), `text` and a list
  of evidence IDs. Observations and interpretations require references. This is
  traceability, not automated proof that an interpretation is correct.
- `characters`: the same guide fields plus unique `id`, `label` and explicit
  `record_ids`. Use source spellings when name readings remain unknown.
- `scenes`: guide fields plus unique `id`, `label`, explicit `record_ids` and
  known `character_ids`. Association is context, not a speaker assignment.
- `reviews`: `record_id`, exact translation `revision`, UTF-8 `source_sha256`
  and `target_sha256`, `finding`, `recommendation`, `disposition` (`retain`,
  `suggestion` or `uncertain`) and evidence IDs. Reviews are inactive notes.

Fields can be empty lists when evidence is unavailable. Capture useful context,
not exhaustive metadata for every line. Do not fill gaps with invented traits.

Retain published guide revisions unchanged. Write a new file, pin the previous
file's hash, validate it, then update the manifest's resource pointer. Coordinate
writers through the existing shared-resource lease workflow and reread the
manifest before replacing that pointer. File writes are not transactional state
edits: this convention does not replace coordination or OS access controls.
The reader checks the immediate predecessor's bytes/revision/source; it does not
recursively certify the entire editorial history.

## Shared discovery and use

Both Codex/Astra and Claude use the same canonical skill and JSON interface:

```sh
python tools/patchquest.py state PATH_TO_PRIVATE_MANIFEST agent-context
python tools/patchquest.py state PATH_TO_PRIVATE_MANIFEST narrative-context
python tools/patchquest.py state PATH_TO_PRIVATE_MANIFEST narrative-context --input narrative-query.json
```

For that last command, put `{"record_id":"line-01"}` in the private JSON input
file; `--input -` also accepts JSON on stdin. `agent-context`
advertises `available`, `not_configured` or `invalid` plus the guide revision and
hash when available. The read operation returns the whole guide by default, or
the work profile and explicitly associated character/scene context for one record.
It never guesses speakers or matches characters by similar names. A record query
also returns relevant evidence and reviews; reviews whose revision or source/
target hash differs from current state are marked `current: false`.

Pass the advertised `expected_sha256` on subsequent reads to detect a changed
guide. Pin its revision/hash in a batch handoff or decision note, alongside the
translation snapshot. Missing context is reported honestly; malformed, wrong-
source, stale-pinned or escaping paths fail explicitly. Existing projects need
not configure this resource, and no ROM or provider SDK is needed to read it.

The same read operation is available through Studio's authenticated local API.
There is no new profile editor, automatic emotional inference or approval queue.
Agents may establish/revise evidence-backed context within their authorized
scope without requesting approval for every profile or line. Instructions stay
in canonical policy; profiles and retrieved source are contextual data.

## Validation and privacy

Synthetic tests check discovery, path/source/revision safeguards, evidence links,
explicit scope, stale reviews and preservation of human corrections/snapshots.
They do not certify literary quality, character interpretation, native client
skill selection, or gameplay. Use a source-based editorial sample review for
those linguistic judgments and report uncertainty.

Keep actual profiles, characters, scene maps, source samples, translations,
review findings and narrative research private. Public methods, schema examples
and tests must use independently authored synthetic material. Do not promote
distinctive game examples by merely replacing character names. Applicable
Apache-2.0 / font CC BY boundaries remain unchanged.
