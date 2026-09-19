---
name: install
description: Set up perdure in Claude Code. Adds the records directive to your
  ~/.claude/CLAUDE.md and runs a short preferences interview; every change is
  shown as a diff first and reversible via /perdure:uninstall. The plugin works
  without this — install makes the model reach for records on its own.
disable-model-invocation: true
---

# perdure: post-install setup

Edits `~/.claude/CLAUDE.md` and Claude Code's preferences file.

You help the user finish setting up the perdure records plugin by configuring
their personal files (which plugins can't touch directly).

**Scope note for Claude:** this skill only reads and writes files under
`~/.claude/`. Do not shell out to locate the plugin's install directory — you
don't need it here; plugin-owned files are referenced via `$CLAUDE_PLUGIN_ROOT`
when needed.

## Introduction

```
I'll help you finish setting up perdure. Two optional steps:
1. Add the records directive to ~/.claude/CLAUDE.md
2. A ~30-second preferences interview

Each step shows the exact changes before applying. You can skip any step.
Everything is reversible via /perdure:uninstall.

Ready to start?
```

Wait for confirmation.

## Step 1: CLAUDE.md directive

If `~/.claude/CLAUDE.md` already contains `<!-- perdure-records:begin -->`:
compare the block's content against the current template below. If it differs,
offer a refresh — the marker-bounded block is fully plugin-owned, so replacing
just that span is safe; show the diff, back up to `.bak`. If identical:
"Directive already installed. Skipping." Otherwise propose appending (create
the file if missing; back up to `.bak`; show the diff first):

```markdown

<!-- perdure-records:begin -->
# perdure records

Complex, multi-step, or multi-session work keeps one record per task under
perdure/workflows/ (convention: the perdure plugin's docs/RECORDS-CONVENTION.md).

- Open with /perdure:start <slug>; update at checkpoints, not every turn.
- Close with /perdure:close, which runs scripts/close-workflow.py. Never set
  completed or abandoned by editing the record: the closer sets the canonical
  status, stamps it, records the outcome or the conscious skip
  (--skip-review "<reason>"), and creates or refreshes perdure/HANDOFF.md.
  Never declare a workflow done with an empty # Review section, and treat
  rot-lint findings before a record goes terminal.
- Status vocabulary: in-progress (alias: active) | parked | completed |
  abandoned. Avoid "closed", "done", and "finished": they DO trip the close
  gate (the lint and the review gate run), but they sit outside the
  vocabulary, so the gate asks you to canonicalize them. Write a canonical
  terminal status, or let the deterministic closer set one for you.
- perdure/HANDOFF.md is DERIVED: only scripts/handoff.py (or /perdure:handoff)
  may write it. Never hand-write or hand-edit that page.

Don't use workflow files for typo fixes, obvious edits, or interactive
back-and-forth — the overhead outweighs the benefit.

## Autonomous flows (claude -p, cron, CI)
Resolve the plugin's scripts ONCE, from Claude Code's own install manifest —
it names the ACTIVE install. (A bare `find ... | head -1` returns whichever
path the filesystem yields first: the cache keeps every version ever
installed, so that can be an obsolete one.)
`PERDURE="$(python3 -c "import json,pathlib;d=json.loads((pathlib.Path.home()/'.claude/plugins/installed_plugins.json').read_text());p=d.get('plugins',d);print(next(v[0]['installPath'] for k,v in p.items() if k.split('@')[0]=='perdure'))")/scripts"`

When dispatching complex work autonomously AND preferences.workflow-files is
"always": create the workflow file BEFORE dispatching — run the plugin's
deterministic scaffolder (refuses to overwrite):
`python3 "$PERDURE/new-workflow.py" <slug> --goal "<goal>"`
or Write the file per the plugin's docs/RECORDS-CONVENTION.md. Pass the file
path into the dispatch prompt. Close autonomously the same way — the
deterministic closer refuses on an empty # Review (or records a conscious skip
with --skip-review), lints, sets the canonical status, and creates or
regenerates the HANDOFF page:
`python3 "$PERDURE/close-workflow.py" <slug> [--outcome "<text>"] [--skip-review "<reason>"]`
Note: a sandboxed `claude -p` child usually cannot read ~/.claude/plugins at
all. Inside one, write the record by hand per docs/RECORDS-CONVENTION.md and
leave it in-progress when you can; if it must go terminal there, say so in
# Outcome — that is the one hand-close the convention allows. The close-gate
hook runs host-side, names the hand-close and lints; the host then runs the
closer, which verifies the record and creates or refreshes the HANDOFF.
<!-- perdure-records:end -->
```

## Step 1b: AGENTS.md (offer, project root)

`Step 1` covers Claude Code. Nothing there reaches a different tool, so offer to
place the tool-agnostic counterpart at the **project root** as `AGENTS.md`:

- If no `AGENTS.md` exists: offer to write `templates/AGENTS.md` verbatim.
- If one exists and contains `<!-- perdure-records:begin -->`: compare the
  marker-bounded span against the template and offer a refresh if it differs.
  That span is plugin-owned, so replacing just it is safe.
- If one exists without the markers: offer to APPEND the marker block. Never
  rewrite a project's existing `AGENTS.md` outside the markers.

Show the diff first and back up to `.bak`, exactly as Step 1 does. Skip without
argument if declined; the file is a convenience, and the checks run without it.

Say plainly what it does and does not do: it tells another tool the convention
exists, which raises the chance a record gets written in the right shape. It
enforces nothing. The enforcement is the exit codes, and reaching a non-Claude
tool means calling them from CI or a pre-commit hook.

## Step 2: Preferences interview

If `~/.claude/perdure-preferences.json` exists: "Preferences already configured.
Run /perdure:health to review." and skip to Step 3. Otherwise ask (AskUserQuestion
where available):

1. **Workflow files** — for complex multi-step tasks, create persistent workflow
   files in `perdure/workflows/`? `always` (recommended for long-running
   projects) / `never` (TodoWrite only) / `ask` each time.
2. **Decision promotion** — at workflow close, how do decisions become ADRs?
   `none` (ask each time, default) / `tagged` (`{promote}` marks only —
   deterministic, automation-friendly) / `heuristic` (the inheritance test: promote
   what a task that never reads this record must still obey) / `all` (noisy).
3. **Auto-archive before /compact** — preserve the full transcript as portable
   markdown in `perdure/archives/` before every compaction? `true` (recommended;
   ~1 MB/session) / `false` (archive manually via /perdure:archive).
4. **Commit archives?** — workflow files and ADRs are committed by default (they
   are the context a checkout carries). Archives are gitignored by default because
   transcripts can contain pasted secrets and personal content. Commit archives
   too? `false` (default — scoped .gitignore keeps them personal) / `true`
   (team-shared history; do a redaction pass before pushing).
5. **Status verbosity** — `concise` (default) / `verbose`.

Write `~/.claude/perdure-preferences.json`:

```json
{
  "schema-version": 3,
  "interviewed": "<ISO-8601 timestamp>",
  "preferences": {
    "workflow-files": "always | never | ask",
    "auto-promote-decisions": "none | tagged | heuristic | all",
    "auto-archive-before-compact": true,
    "rot-lint-at-close": true,
    "handoff-regen-at-close": true,
    "commit-archives": false,
    "verbose-status": false
  },
  "known-config": {
    "claude-md-directive": true
  }
}
```

`rot-lint-at-close` (default `true`) gates the close-gate rot-lint
hook; not interviewed — silent when clean, set `false` to opt out.
`handoff-regen-at-close` (default `true`, under the master gate) lets that
hook regenerate a stale generator-stamped `perdure/HANDOFF.md` host-side
after a terminal record edit — its only write path, bounded to the derived
page; it never creates a page and never overwrites a hand-written one.
`known-config` records what Step 1 actually did (so `/perdure:health` can
report without re-deriving). Schema-version 3 dropped the
`headless-budget-usd` / `headless-result-inline-threshold` keys and the
`agent-permissions-approved` bookkeeping — they belong to whatever agent
tooling uses them, not to the records layer; leftover copies here are ignored,
no migration needed — as are the
schema-2 deprecated keys (`suggest-agent-skills`, `parallel-exploration`,
`orchestration-mode`, `auto-reindex`, `archive-location`).

Show the final JSON, confirm, then write.

## Step 3: Verification

```
✅ perdure configured

Files touched:
  - ~/.claude/CLAUDE.md (marker block; .bak saved)
  - ~/.claude/perdure-preferences.json
  - <project>/AGENTS.md (marker block; only when you accepted it in step 1b)

Try it: /perdure:start <slug> on your next multi-step task.
Check health anytime: /perdure:health
Reverse everything:   /perdure:uninstall
```

## Safety rules
- Always show diffs before writing; always back up modified files to `.bak`
- Idempotent: re-running never duplicates entries (check markers first)
- Never overwrite without confirmation; respect every skip
- This skill never touches settings.json permissions and never references
  other plugins' agents — perdure has no agent dependencies
