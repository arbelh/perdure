# Contributing

perdure is small on purpose: fourteen skills, eight stdlib Python scripts, two
hooks, one convention. Changes that keep it small are the easiest to land.

## Before you open a pull request

- **Check what you can locally.** `claude plugin validate .` for the manifests,
  `python3 -m py_compile scripts/*.py hooks/*.py` for the scripts, and the
  model-free loop in a scratch project: `new-workflow.py`, `rot-lint.py --strict`,
  `handoff.py --check`, `close-workflow.py`. Every script answers `--help`.
- **The full gate runs before merge.** The eval suite lives in the maintainer's
  development repository and runs on every change before export. A pull request
  is merged only after it passes there; a change in behaviour is merged with a
  case that fails without it.
- **One version everywhere.** `.claude-plugin/plugin.json`, `.codex-plugin/plugin.json`,
  `.agents/plugins/marketplace.json` carry the same version.

## Shape of a change

- **A skill** is one folder with one `SKILL.md` and a name that is not a Claude
  Code built-in; it registers `/perdure:<name>` by itself, and the plugin ships no
  command files, since a command under a skill's name would shadow the skill for
  the model. A skill that runs a script names
  the plugin-root path first and carries a `scripts` link beside it
  (`ln -s ../../scripts skills/<name>/scripts`), so the skills CLI ships the
  checks with the skill.
- **A tool adapter** follows the Codex pair: mirror the Claude Code manifest in
  the tool's own format, point it at the same `skills/` directory, add nothing
  the tool does not read.
- **Scripts** stay stdlib Python 3 and report what they could not check
  alongside what they found.
- **Docs** use short sentences and plain words, state what was measured, and say
  what a thing does rather than what another tool does not.
- **Release notes are history.** Each release carries its note on the releases
  page; never rewrite an old one.
- **Commit messages** are plain and carry no attribution trailers.

## Reporting a defect

Paste the script's output. The lint ends every run with a coverage table that
says which checks ran and why the rest did not; that table is the report.

## Unlikely to land

A dependency outside the standard library. A second records format. A feature
that works in one tool when a tool-neutral shape exists.

Contributions are accepted under the MIT license, the same as the project.
