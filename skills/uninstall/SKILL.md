---
name: uninstall
description: Reverse the changes made by /perdure:install. Removes the perdure
  records directive from your CLAUDE.md and deletes the preferences file (all
  backed up first). Does not uninstall the plugin itself — use /plugin uninstall
  for that.
disable-model-invocation: true
---

# perdure: uninstall personal config

Edits `~/.claude/CLAUDE.md` and Claude Code's preferences file.

You reverse changes made by `/perdure:install`. This does NOT uninstall
the plugin itself — it only removes the personal configuration additions.

**Scope note for Claude:** This skill only reads and writes files under `~/.claude/`.
Do not run `find` or shell out to locate the plugin's install directory — you do
not need it here. If a future step ever requires plugin-owned files, reference
them via `$CLAUDE_PLUGIN_ROOT` (Claude Code sets this automatically when plugin
code runs).

## Introduction

```
I'll reverse the configuration added by /perdure:install:
1. Remove the perdure records directive from ~/.claude/CLAUDE.md
2. Delete ~/.claude/perdure-preferences.json (backed up first)

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

## Step 2: Remove preferences file

### Detect
Does `~/.claude/perdure-preferences.json` exist?

### Apply
- If not found: "No preferences file found, skipping."
- If found: show content for confirmation, back up to `.bak`, then delete

## Step 3: Verification

```
✅ perdure personal config removed

Files modified:
  - ~/.claude/CLAUDE.md (backed up to .bak, markers removed)
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

`/perdure:uninstall` only touches user-global config under ~/.claude/.
```

## Safety rules
- Only remove content bounded by markers — never remove user's additions
- Always create .bak before modifying
- Always show diffs before writing
- Never delete files without showing content first
- Idempotent: running twice when nothing is installed is a no-op
