---
name: health
description: Show perdure configuration health — the plugin-specific checks that
  first-party /doctor and /plugin list don't know about. Reports the CLAUDE.md
  marker block, preferences, records state, and whether the installed plugin
  version lags the source/marketplace. Read-only.
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

### 2. Personal configuration (~/.claude/)

- `~/.claude/CLAUDE.md` contains the `<!-- perdure-records:begin -->` …
  `<!-- perdure-records:end -->` marker block
- `~/.claude/perdure-preferences.json` exists; show the active preference values. Ignore
  deprecated keys and keys owned by other tooling (`parallel-exploration`, `orchestration-mode`,
  `suggest-agent-skills`, `auto-reindex`, `archive-location`,
  `headless-budget-usd`, `headless-result-inline-threshold`) silently.

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
- NEVER modify files; reading files and `claude plugin list` is the entire surface
- Missing/unreadable file → `✗`, not an error
- Show absolute paths so the user can investigate
- Outside a project directory, skip the project section
