# Private-project starter

For structured exceptions and source classifications, see
[the assessment workflow](../../docs/translation-exceptions.md) and
`assessment.example.json`. Replace illustrative hash placeholders using the
selected project's `assessment-context` API. Actual labels/evidence stay private.

For optional emulator checks, see [runtime evidence](../../docs/runtime-evidence.md)
and `runtime-scenario.example.json`. Its values are fictional; replace them privately
after investigating the installed emulator and game.

Copy this directory to an external private workspace, or to ignored .local/projects/. Do not build an actual translation inside templates/.

Copy project.example.json to project.json. Replace its placeholder hash with the verified original SHA-256 and set the source path; external originals are supported as read-only inputs. Supply validated expected-byte edits in data/recipe.json. An empty recipe fails closed. Only set a SNES header offset/copier-header policy after validating mapping.

From the platform checkout, use the path to the copied runner:

```powershell
python ../private-workspace/projects/example/project.py --platform . --name experiment-001
```

From another working directory, pass the absolute path to the copied `project.py` and the absolute platform checkout path through `--platform`; neither path is inferred from this copied directory.

The runner uses public byte-edit/checksum/BPS APIs and writes fresh output files. It does not infer encoding, repoint strings or install renderer hooks. Extend those privately, with private research and tests. Keep approved/rejected checkpoints and local environment notes. Read `docs/project-architecture.md` **inside the platform checkout selected by `--platform`**, and the copied [AGENTS.md](AGENTS.md). The architecture guide is not copied with this starter, so a relative link from this external directory would be invalid.

The starter code/documentation is Apache-2.0; consult `LICENSE-SCOPE.md` and `docs/licensing.md` in the selected platform before redistributing font data or borrowed material. Copying the starter does not assign a license to private game content.

Optional Studio: when the installation already has a shared Studio, follow
`docs/translation-studio.md#shared-studio-setup` inside the selected platform.
Coordinate adding this explicit manifest to the existing shared local registry
and refreshing its established launcher. Keep this project's authoritative state
in place. Use the platform's `tools/patchquest.py studio` for initial setup or an
explicit isolated-session need. An empty project has no translation records until
its private extractor imports them. Implement snapshot consumption in the private
runner before claiming that editor changes affect builds; the starter recipe does
not infer text bindings. Registration alone does not configure a build worker.

For narrative work, adapt [narrative.example.json](narrative.example.json) into a
versioned file in this private project. Replace its invented evidence and source
hash, then add its relative path under `resources.narrative_context`. Read
`docs/narrative-context.md` in the selected platform for the schema, shared
discovery/read API, versioning and editorial workflow. The resource is optional;
do not treat the fictional guide as knowledge about an actual game.
