---
name: health
description: Show perdure configuration health — the plugin-specific checks that
  first-party /doctor and /plugin list don't know about. Reports the CLAUDE.md
  marker block (or a records rule of your own), the block in Codex's
  AGENTS.md ($CODEX_HOME, else ~/.codex),
  preferences, records state, and whether the installed plugin version lags
  the source/marketplace. Read-only.
disable-model-invocation: true
disallowed-tools: Edit, Write, NotebookEdit
---

# perdure health check

READ-ONLY report on the plugin-specific configuration layer. First-party tools
already cover generic health (`/doctor`, `/plugin list`, `/agents`) — this skill
checks only what THEY can't see:

## Checks

### 1. Version lag (installed vs available)

Read the installed plugin's version (the `version` in
`~/.claude/plugins/**/perdure*/.claude-plugin/plugin.json`, or via `claude plugin list`)
and compare against the newest version available to this machine — the local
marketplace clone's copy (`~/.claude/plugins/marketplaces/*/`).

If the installed version is older, lead the report with the nudge:

```
⚠ Installed perdure v<X> lags available v<Y>.
  Update: claude plugin update perdure@<marketplace>   (then restart the session)
```

Silent version lag is a known failure mode (an earlier install once ran 3 months
stale) — this check exists so it can't happen quietly.

### 2. Personal configuration (~/.claude/, Codex's folder)

Codex's folder is `$CODEX_HOME` when that variable is set, else `~/.codex`
(`printenv CODEX_HOME` says which). Below, `~/.codex/AGENTS.md` means
`AGENTS.md` in that folder.

- `~/.claude/CLAUDE.md` contains the `<!-- perdure-records:begin -->` …
  `<!-- perdure-records:end -->` marker block. Without it, look for a records
  rule of the user's own (a line that names `/perdure:start` or
  `perdure/workflows/`): report it as found outside the markers, with its line
  numbers, not as missing. Both present: say so, since two rules can disagree.
- When Codex's folder exists: `~/.codex/AGENTS.md` contains the same marker
  block (Codex reads that file in every project). Missing → `✗` with the fix
  `/perdure:install`. A records rule of the user's own there is reported as in
  `~/.claude/CLAUDE.md`. When `AGENTS.override.md` sits in the same folder,
  say that Codex reads it instead of `AGENTS.md`, so the block is not read
  while the override exists. No Codex folder: skip this line.
- `~/.claude/perdure-preferences.json` exists. Show:
  - the active values. A key the file lacks takes the value the code reads
    while it is missing; say which keys, and that value:
    `auto-promote-decisions` heuristic, `auto-archive-before-compact` off (the
    hook archives only on an explicit `true`), `rot-lint-at-close` on,
    `handoff-regen-at-close` on, `commit-archives` off
  - the ones that differ from today's defaults, each with the default beside
    it. Defaults, as `/perdure:install` writes them:
    `auto-promote-decisions: heuristic`, `auto-archive-before-compact: true`,
    `rot-lint-at-close: true`, `handoff-regen-at-close: true`,
    `commit-archives: false`
  - keys the current schema ignores, listed by name (`workflow-files`,
    `verbose-status`, `parallel-exploration`, `orchestration-mode`,
    `suggest-agent-skills`, `auto-reindex`, `archive-location`,
    `headless-budget-usd`, `headless-result-inline-threshold`,
    `agent-permissions-approved`, or any other key the schema does not name)
  - its `schema-version`, against today's 4

  A value that differs is a choice, not a fault: mark it `○`. To move to the
  defaults, `/perdure:install` offers an update and keeps the file on enter.
  With no preferences file, every key takes its while-missing value: say that
  nothing is archived before compaction.

### 3. Current project records

If in a project directory:
- `perdure/workflows/` — count files by status (scan frontmatter; no index file exists)
- `perdure/decisions/` — count ADRs
- `perdure/archives/` — count archives; note whether `.gitignore` covers them and
  whether that matches the `commit-archives` preference

### 4. Report

Plain markdown, short sections, symbols `✓` configured / `✗` missing (with the fix
command) / `○` optional. End with either the prioritized fix list (what to run,
what it changes) or:

```
🎉 Fully configured — nothing to fix.
```

## Safety rules
- NEVER modify files; reading files, `printenv CODEX_HOME` and
  `claude plugin list` is the entire surface
- Missing/unreadable file → `✗`, not an error
- Show absolute paths so the user can investigate
- Outside a project directory, skip the project section
