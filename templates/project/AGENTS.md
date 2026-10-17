# Private translation project

This directory is private, including its title, source/output hashes, research,
code, translations, screenshots, checkpoints and test results. Do not copy its
contents into the platform repository or publish it without explicit approval.

Read the platform's AGENTS.md, localization/typography standards and SNES skill,
then this project's scope and evidence. Record the platform checkout in private
environment notes; invoke this runner with an explicit `--platform` path.
The platform never imports project code. Keep original ROMs immutable, build
from pinned originals, use fresh outputs, verify exact expected changes and
BPS reconstruction, and retain approved and rejected checkpoints separately.

Before using the template, copy project.example.json to project.json, replace
its all-zero hash with the verified original hash, and validate the encoding,
mapping, controls and recipe. An empty recipe fails closed. The generic runner
does not infer bank allocation, encoding or rendering. Extend it privately when
the project needs those capabilities. Do not claim emulator/hardware results
from automated tests alone.

Maintain `docs/` for durable research, `data/` for encodings/manifests/translations,
`tests/` for project regressions and `output/` for new derivatives. Keep private
tool/environment notes separately from reusable platform instructions. Promote
only independently generalized improvements with synthetic or licensed tests;
retain the original evidence and adaptation here. Stop and ask if an established
checkpoint cannot be reproduced during a migration.

Read the selected platform's LICENSE-SCOPE.md and docs/licensing.md. Its generic
code uses Apache-2.0; designated Quest Pixel font data use CC BY 3.0. Preserve
applicable credit, terms and provenance in font-derived packages. Private game
content is not licensed by copying this starter. Keep detailed rights research
private and promote only cleared reusable material. BrentW is the platform's
public maintainer identity, not a blanket ownership assertion.
