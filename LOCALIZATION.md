# Localization standards

Use [translation exceptions and content classifications](docs/translation-exceptions.md)
for evidence-backed uncertainty, fidelity concerns and mature-content handling.
Classification is descriptive, separate from progress and provider permission;
preserve permitted meaning and explicitness without silent sanitization. Follow
applicable safeguards and record restrictions accurately without rewriting saved
corrections or creating an approval queue.

Permanent policy for every current and future game in this repository, established by the user on 2026-10-16. **Localize the language, not the culture.** Aim for polished, natural English that preserves the original storytelling, characters, humor, emotional impact and Japanese cultural identity. This policy does not itself authorize a new translation phase or require rebuilding accepted checkpoints; follow the separately authorized scope.

## Capitalization

Prefer natural mixed-case English across all projects. Use Title Case for menu choices, keeping short connecting words lowercase where appropriate; use sentence case for dialogue, exposition, narration and prompts. Headings may use Title Case or sentence case according to context. Preserve standard proper-noun capitalization, established terminology and meaningful source emphasis. ALL CAPS is appropriate for deliberate stylistic emphasis, acronyms, warnings or intentionally uppercase interfaces, rather than as a space-saving or renderer default.

Apply this editorially, not with a blanket `title()` or `upper()` transformation. Acronyms, names, hyphenated words and context require review. Case conversion must not change meaning, character voice, register, cultural specificity or intentional emotional intensity. Keep the reviewed spelling in translation records; rendering adapters must preserve it. If a renderer cannot support it safely, document that limitation instead of silently uppercasing.

## Tone, voice and meaning

Use the [Narrative Tone, Character Voice, and Emotional Context framework](docs/narrative-context.md) before translating at scale. Its canonical method separates work-level tonal identity, scene mood/trajectory, stable character voice/persona, and a line's emotion, relationship and communicative intent. Evidence-backed private guides are revisable; they are not stereotypes or rules to make every scene match the dominant mood. Shared agent discovery exposes the same guide and revision-bound review notes without changing saved wording.

Preserve humor, seriousness, sarcasm, tension, affection, awkwardness and emotional weight. Respect the source's level of maturity: do not sanitize, exaggerate, modernize, or introduce humor, profanity, romance or sexual implications absent from the Japanese. Preserve subtext, deliberate ambiguity, distinct personalities, speech patterns, relationships and levels of formality. Do not flatten everyone into contemporary American teenage speech or add unsupported information, motivations or emotions.

Translate intended meaning in context rather than words mechanically. Use natural English equivalents for idioms when they preserve meaning and tone. Preserve jokes where possible without replacing Japanese references with Western ones. If wordplay cannot be reproduced faithfully, record the original meaning and the localization choice. Isolated strings do not justify certainty about speaker, referent or intent.

## Cultural specificity

Retain Japanese names, settings, customs, references and meaningful forms of address. Preserve specific terminology for items, equipment, clothing, food, buildings, locations, transportation, festivals, traditions and social relationships. Familiarity to an English-speaking player is not sufficient reason to replace a Japanese concept.

| Source concept | Preferred contextual term | Avoid flattening into |
|---|---|---|
| 着物 | Kimono | Dress or generic robe |
| 刀 | Katana | Generic sword |
| 浴衣 | Yukata | Generic kimono or robe |
| 温泉 | Onsen | Bathhouse |
| 銭湯 | Sento | Onsen |
| たい焼き | Taiyaki | Fish-shaped pastry |
| ラーメン | Ramen | Noodle soup |
| おにぎり | Onigiri | Sandwich |
| 新幹線 | Shinkansen | Generic train |

These are contextual examples, not automatic substitutions. Preserve the source's specificity in both directions: a generic sword is not automatically a katana, and a generic train is not a shinkansen. Use established romanization where meaningful; do not force Japanese terminology where it adds no meaning. Keep related concepts distinct, such as onsen and sento.

Where clarification is necessary, prefer natural context, brief item descriptions or existing dialogue opportunities. Do not invent exposition, add lengthy explanations or insert translator commentary into dialogue. Preserve cultural identity without overexplaining it.

## Glossaries and uncertainty

Maintain [the shared contextual glossary](localization/glossary.json) and a separate glossary inside each private project for game-specific terms. Each entry retains Japanese, romanization when useful, approved/preferred English, useful literal meaning, context, decision notes and review status. Shared examples are not proof that a term occurs in any game. Apply consistent terminology across dialogue, menus, inventories, equipment descriptions and other text; document contextual exceptions privately rather than changing terms silently.

For ambiguity, retain the original Japanese and source location, record available scene/speaker evidence, list plausible readings, recommend a rendering with a confidence assessment, and flag significant questions for review. Unknown context leaves a translation provisional. Never invent certainty to increase coverage. Unresolved entries may remain Japanese in a test build while independent work proceeds elsewhere.

## Interfaces and technical constraints

Menus, status, inventory, combat commands and mechanical descriptions should be clear, brief and consistent. Use recognizable English RPG terminology when it matches the game. Avoid confusing literal labels, retain culturally specific item/equipment names, and keep interface terminology consistent with narrative translation.

Fidelity takes priority over matching the original byte count. A storage limit and visual crowding are different constraints: validate relocation or expanded storage with verified ownership/pointer reachability when required, without using byte count to excuse meaning loss.

For visible interface crowding, follow the permanent [UI Typography, Alignment, and Layout Quality Standard](AGENTS.md#ui-typography-alignment-and-layout-quality-standard) and [compact typography priority](TYPOGRAPHY.md): first positioning/padding, then a shorter natural equivalent with no meaning loss, then improved compact advances and text-block layout, then safe box expansion/repositioning when still necessary, then deeper renderer changes. Do not silently truncate or remove characterization, cultural distinctions or important information for convenience.

Technical changes still require the project's bounds, control, reproducibility and runtime checks. A phrase that fits is not necessarily a faithful translation. Conversely, a storage obstacle must be documented rather than resolved by speculative ROM edits. Previously accepted short prototype labels remain historical checkpoints; review release wording in its actual context.

## Translation traceability and review

Keep translation content separate from ROM encoding/insertion code. For every translated record retain:

- Stable ID, original Japanese, source revision/location and original encoded bytes or a lossless extraction reference.
- English text, speaker/scene/function when known, cultural context and glossary decisions.
- Control codes, runtime substitutions and their order/meaning; unknown controls remain explicit.
- Translation confidence, unresolved readings and significant localization decisions.
- Separate identification, translation, implementation and runtime-test statuses. Appearance approval is not proof of save persistence or complete gameplay coverage.

Editable translation records can reference a private engineering manifest for offsets, pointer formats, tile rectangles and constraints. Revision of English must not require repeating discovery. All game-specific scripts, graphics, translations, manifests, notes and evidence stay in the private project, regardless of size. Before an integrated test, review consistency, source fidelity, UI fit, controls and unresolved entries. Preserve a private audit trail when context changes a decision; promote only independent general techniques to the public platform.

The finished work should feel like a professionally localized Japanese game: **translate idioms by meaning, preserve culturally specific names and concepts, maintain voices and tone, and never invent meaning to fill gaps in context.**
