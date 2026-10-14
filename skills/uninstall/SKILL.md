---
name: uninstall
description: Reverse the changes made by /perdure:install. Removes the perdure
  records directive from your CLAUDE.md, the marker block from the project's
  AGENTS.md and from Codex's AGENTS.md ($CODEX_HOME, else ~/.codex) when
  present, and deletes the
  preferences file (all backed up first). Does not uninstall the plugin itself —
  use /plugin uninstall for that.
disable-model-invocation: true
---

# perdure: uninstall personal config

Edits `~/.claude/CLAUDE.md`, Claude Code's preferences file and, when present,
the marker block in the project's `AGENTS.md` and in `~/.codex/AGENTS.md`.

You reverse changes made by `/perdure:install`. This does NOT uninstall
the plugin itself — it only removes the configuration additions.

**Codex's folder** is `$CODEX_HOME` when that variable is set, else `~/.codex`.
Below, `~/.codex/AGENTS.md` means `AGENTS.md` in that folder.

**Scope note for Claude:** this skill reads and writes files under `~/.claude/`,
the marker block of the project's `AGENTS.md` and the marker block of
`~/.codex/AGENTS.md`. Its shell-outs are `git rev-parse --show-toplevel`, to
find the project root, and `printenv CODEX_HOME`, to find Codex's folder. Do
not run `find` or shell out to locate the plugin's install directory — you do
not need it here.

## Introduction

```
I'll reverse the configuration added by /perdure:install:
1. Remove the perdure records directive from ~/.claude/CLAUDE.md
2. Remove the perdure marker block from this project's AGENTS.md, if present
3. Remove the perdure marker block from Codex's AGENTS.md, if present
4. Delete ~/.claude/perdure-preferences.json (backed up first)

Each step shows the diff before applying. Everything creates .bak files.

This does NOT uninstall the plugin. For that, run:
  $ claude plugin uninstall perdure

Ready to proceed?
```

## Step 1: Remove CLAUDE.md directive

### Detect
Look for the marker block in `~/.claude/CLAUDE.md`:
```
<!-- perdure-records:begin -->
...
<!-- perdure-records:end -->
```

### Apply
- If markers not found: "No perdure directive found, skipping."
- If found: back up to `.bak`, remove lines between markers (inclusive), save
- Show diff before writing

## Step 2: Remove the project AGENTS.md marker block

### Detect
- The project root is the one `/perdure:install` Step 1b uses: the path
  `git rev-parse --show-toplevel` prints, or else the current folder. When
  that root is the home folder or a folder of several projects, even when git
  names it as the root: "Not a project, skipping."
- Look for the `<!-- perdure-records:begin -->` …
  `<!-- perdure-records:end -->` block in `<project root>/AGENTS.md`

### Apply
- If the file or the markers are not found: "No perdure block in AGENTS.md,
  skipping."
- If found: back up to `.bak`, remove the lines between the markers (inclusive),
  save; if nothing but whitespace remains, say so and leave the file for the
  user to delete
- Show the diff before writing; never touch text outside the markers

## Step 3: Remove the Codex marker block

### Detect
Look for the `<!-- perdure-records:begin -->` …
`<!-- perdure-records:end -->` block in `~/.codex/AGENTS.md`. Leave
`AGENTS.override.md` alone; perdure never writes it.

### Apply
- If the file or the markers are not found: "No perdure block in
  ~/.codex/AGENTS.md, skipping."
- If found: back up to `.bak`, remove the lines between the markers
  (inclusive), save. Leave the file in place, even when nothing but whitespace
  remains, and say so.
- Show the diff before writing; never touch text outside the markers
- Either way, when perdure is installed in Codex, add: "In Codex, perdure's
  session-start hook still gives each session the records rule while the
  plugin is installed and that hook is trusted. To stop it, leave the hook
  untrusted in Codex's /hooks, or run `codex plugin remove perdure@perdure`."

## Step 4: Remove preferences file

### Detect
Does `~/.claude/perdure-preferences.json` exist?

### Apply
- If not found: "No preferences file found, skipping."
- If found: show content for confirmation, back up to `.bak`, then delete

## Step 5: Verification

```
✅ perdure personal config removed

Files modified:
  - ~/.claude/CLAUDE.md (backed up to .bak, markers removed)
  - <project root>/AGENTS.md (marker block removed, .bak saved; when present)
  - ~/.codex/AGENTS.md (marker block removed, .bak saved; when present)
  - ~/.claude/perdure-preferences.json (deleted, backup saved)

The plugin itself is still installed. To fully uninstall:
  $ claude plugin uninstall perdure@perdure
  $ claude plugin marketplace remove perdure   # drop the marketplace entry too

YOUR RECORDS STAY, and that is the point: perdure/ is plain markdown in your
own repo. Workflow records, ADRs, and the HANDOFF page remain readable and
useful with no plugin installed. Nothing in this uninstall deletes them —
delete them yourself if you want them gone. (perdure/HANDOFF.md is derived
and can no longer be regenerated once the plugin is gone; it stays valid as a
point-in-time page, and its own header says to re-derive before trusting it.)

To also clear Claude Code's OWN project-level state — transcripts, tasks, and
file history, NOT your perdure/ files — use the CLI:

  $ claude project purge .              # current project, with confirmation
  $ claude project purge . --dry-run    # preview without changes

`/perdure:uninstall` touches ~/.claude/ and the perdure marker blocks of the
project's AGENTS.md and ~/.codex/AGENTS.md, nothing else.
```

## Safety rules
- Only remove content bounded by markers — never remove user's additions
- Always create .bak before modifying
- Always show diffs before writing
- Never delete files without showing content first
- Idempotent: running twice when nothing is installed is a no-op
