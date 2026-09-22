---
name: install
description: Set up perdure in Claude Code. Enter installs the recommended
  setup (the records directive in ~/.claude/CLAUDE.md, the project's AGENTS.md
  when the directory is a git repository, default preferences); "adjust" walks
  the options. Every change is shown as a diff first and reversible via
  /perdure:uninstall. The plugin works without this — install makes the model
  reach for records on its own.
disable-model-invocation: true
---

# perdure: post-install setup

Edits `~/.claude/CLAUDE.md`, Claude Code's preferences file and, when the
directory is a git repository, the marker block in the project's `AGENTS.md`.

You help the user finish setting up the perdure records plugin by configuring
their personal files (which plugins can't touch directly).

**Scope note for Claude:** this skill reads and writes files under `~/.claude/`
and the marker block of the project's `AGENTS.md`. Its one shell-out is
`git rev-parse --show-toplevel`, to find the project root; do not shell out to
locate the plugin's install directory — plugin-owned files are referenced via
`$CLAUDE_PLUGIN_ROOT` when needed.

## Introduction

```
I'll finish setting up perdure. Enter installs the recommended setup:

- the records directive in ~/.claude/CLAUDE.md: a record, with its plan,
  opens before the first edit of every multi-step task
- AGENTS.md at this project's root, so the checkout carries the convention
  for other tools and other people (only when this directory is a git
  repository)
- preferences: the session archived before compaction and kept local; lint
  and handoff at every close; decisions promoted to ADRs when marked, or when
  other tasks must obey them

Every change is shown as a diff first and is reversible via /perdure:uninstall.
Enter to install, "adjust" to go through the options, "no" to stop here.
```

Wait for the answer. On enter, or any yes: run Step 1, Step 1b when the
directory is a git repository, write Step 2's defaults, then Step 3. On
"adjust": run every step with its questions. On "no", "cancel", "not now" or
any decline: stop, write nothing, and say the command runs again any time.

## Step 1: CLAUDE.md directive

If `~/.claude/CLAUDE.md` already contains `<!-- perdure-records:begin -->`:
compare the block's content against the current template below. If it differs,
offer a refresh — the marker-bounded block is fully plugin-owned, so replacing
just that span is safe; show the diff, back up to `.bak`. If identical:
"Directive already installed. Skipping." Otherwise propose appending (create
the file if missing; back up to `.bak`; show the diff first; enter applies):

```markdown

<!-- perdure-records:begin -->
# perdure records

Complex, multi-step, or multi-session work keeps one record per task under
perdure/workflows/ (convention: the perdure plugin's docs/RECORDS-CONVENTION.md).

- Open with /perdure:start <slug> before the first edit, with the plan and
  decisions written; update at checkpoints, not every turn.
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

When dispatching complex work autonomously, create the workflow file BEFORE
dispatching, with its plan and decisions — run the plugin's deterministic
scaffolder (refuses to overwrite):
`python3 "$PERDURE/new-workflow.py" <slug> --goal "<goal>" --plan "<item>" --decision "<text>" --next "<step>"`
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

## Step 1b: AGENTS.md (project root)

`Step 1` covers Claude Code. Nothing there reaches a different tool, so place
the tool-agnostic counterpart as `AGENTS.md` at the **repository root**, the
path `git rev-parse --show-toplevel` prints, which is not always the current
directory. Default yes when that command succeeds; when it fails, skip
automatically and say so:

- If no `AGENTS.md` exists: write `templates/AGENTS.md` verbatim.
- If one exists and contains `<!-- perdure-records:begin -->`: compare the
  marker-bounded span against the template and refresh it if it differs. That
  span is plugin-owned, so replacing just it is safe.
- If one exists without the markers: APPEND the marker block. Never rewrite a
  project's existing `AGENTS.md` outside the markers.

Show the diff first and back up to `.bak`, exactly as Step 1 does; enter
applies, a decline is honoured without argument; the checks run without the
file. `/perdure:uninstall` removes the marker block again.

Say plainly what it does and does not do: it tells another tool the convention
exists, which raises the chance a record gets written in the right shape. It
enforces nothing. The enforcement is the exit codes, and reaching a non-Claude
tool means calling them from CI or a pre-commit hook.

## Step 2: Preferences interview

If `~/.claude/perdure-preferences.json` exists: "Preferences already configured.
Run /perdure:health to review." and skip to Step 3. On enter, write the defaults
below without asking. On "adjust", ask (AskUserQuestion where available), each
question with its default marked:

1. **Decision promotion** — at workflow close, how do decisions become ADRs?
   `heuristic` (default: every decision marked `{promote}`, plus any unmarked
   one that a task which never reads this record must still obey — a default, a
   name, a boundary; a mark always wins over the test) / `tagged` (`{promote}`
   marks only — deterministic, automation-friendly) / `none` (list and ask each
   time) / `all` (noisy).
2. **Auto-archive before /compact** — preserve the full transcript as portable
   markdown in `perdure/archives/` before every compaction? `true` (default;
   ~1 MB/session, kept local) / `false` (archive manually via /perdure:archive).
3. **Commit archives?** — workflow files and ADRs are committed by default (they
   are the context a checkout carries). Archives are gitignored by default because
   transcripts can contain pasted secrets and personal content. Commit archives
   too? `false` (default — scoped .gitignore keeps them personal) / `true`
   (team-shared history; do a redaction pass before pushing).

Write `~/.claude/perdure-preferences.json` (the defaults, as written on enter):

```json
{
  "schema-version": 4,
  "interviewed": "<ISO-8601 timestamp>",
  "preferences": {
    "auto-promote-decisions": "heuristic",
    "auto-archive-before-compact": true,
    "rot-lint-at-close": true,
    "handoff-regen-at-close": true,
    "commit-archives": false
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
report without re-deriving). Other accepted values: `auto-promote-decisions`
`none | tagged | heuristic | all`; each boolean flipped. Schema-version 4
dropped `workflow-files` and `verbose-status`: nothing read them, and the
directive decides when a record opens. Schema-version 3 dropped the
`headless-budget-usd` / `headless-result-inline-threshold` keys and the
`agent-permissions-approved` bookkeeping — they belong to whatever agent
tooling uses them, not to the records layer. Leftover copies of any dropped key
are ignored, no migration needed — as are the schema-2 deprecated keys
(`suggest-agent-skills`, `parallel-exploration`, `orchestration-mode`,
`auto-reindex`, `archive-location`).

Show the final JSON. On the enter path it is written as shown, no question; on
"adjust" confirm after the questions, then write.

## Step 3: Verification

```
✅ perdure configured

Files touched:
  - ~/.claude/CLAUDE.md (marker block; .bak saved)
  - ~/.claude/perdure-preferences.json
  - <repository root>/AGENTS.md (marker block; .bak saved; when the directory
    is inside a git repository and you did not decline it)

Start your next multi-step task normally: the record opens itself, plan first.
Or open one by hand: /perdure:start <slug>
Check health anytime: /perdure:health
Reverse everything:   /perdure:uninstall
```

## Safety rules
- Always show diffs before writing; always back up modified files to `.bak`
- Idempotent: re-running never duplicates entries (check markers first)
- Never overwrite without confirmation; respect every skip
- This skill never touches settings.json permissions and never references
  other plugins' agents — perdure has no agent dependencies
