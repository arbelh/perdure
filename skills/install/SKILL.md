---
name: install
description: Set up perdure in Claude Code. Enter installs the recommended
  setup (the records directive in ~/.claude/CLAUDE.md, the project's AGENTS.md,
  the same directive in ~/.codex/AGENTS.md when Codex is installed, default
  preferences); "adjust" walks the options. Every change is shown as a diff
  first and reversible via /perdure:uninstall. The plugin works without this —
  install makes the model reach for records on its own.
disable-model-invocation: true
---

# perdure: post-install setup

Edits `~/.claude/CLAUDE.md`, Claude Code's preferences file, the marker block
in the project's `AGENTS.md` and, when Codex is installed, the marker block in
Codex's own `AGENTS.md`.

You help the user finish setting up the perdure records plugin by configuring
their personal files (which plugins can't touch directly).

**Codex's folder** is `$CODEX_HOME` when that variable is set, else `~/.codex`.
Below, `~/.codex/AGENTS.md` means `AGENTS.md` in that folder.

**Scope note for Claude:** this skill reads and writes files under `~/.claude/`,
the marker block of the project's `AGENTS.md` and the marker block of
`~/.codex/AGENTS.md`. Its shell-outs are `git rev-parse --show-toplevel`, to
find the project root, and `printenv CODEX_HOME`, to find Codex's folder. Do
not shell out to locate the plugin's install directory; plugin-owned files are
referenced via `$CLAUDE_PLUGIN_ROOT` when needed.

## Introduction

```
I'll finish setting up perdure. Enter installs the recommended setup:

- the records directive in ~/.claude/CLAUDE.md: any task that changes files
  or decides something keeps a record, opened with its plan
- AGENTS.md at this project's root, so the checkout carries the convention
  for other tools and other people
- the same directive in Codex's own AGENTS.md, which Codex reads in every
  project (only when Codex is installed)
- preferences: the session archived before compaction and kept local; lint
  and handoff at every close; decisions promoted to ADRs when marked, or when
  other tasks must obey them

Every change is shown as a diff first and is reversible via /perdure:uninstall.
Enter to install, "adjust" to go through the options, "no" to stop here.
```

Wait for the answer. On enter, or any yes: run Step 1, Step 1b, Step 1c when
Codex's folder exists, Step 2 (the defaults, or the report on an existing file),
then Step 3. On "adjust": run every step with its questions. On "no",
"cancel", "not now" or any decline: stop, write nothing, and say the command
runs again any time.

## Step 1: CLAUDE.md directive

If `~/.claude/CLAUDE.md` already contains `<!-- perdure-records:begin -->`:
compare the block's content against the current template below. If it differs,
offer a refresh — the marker-bounded block is fully plugin-owned, so replacing
just that span is safe; show the diff, back up to `.bak`. If identical:
"Directive already installed. Skipping."

If the file has no markers but already holds a records rule of its own (a line
outside perdure's markers that names `/perdure:start` or `perdure/workflows/`),
do not append a second rule. Report where it is: "Your CLAUDE.md already has a
records rule (lines N-M). Enter keeps yours; "add" appends perdure's block
anyway." When the markers are there too, refresh the block as above and name
the lines outside it, since two rules can disagree; never edit the user's lines.

Otherwise propose appending (create the file if missing; back up to `.bak`;
show the diff first; enter applies):

```markdown

<!-- perdure-records:begin -->
# perdure records

Any task that changes files or decides something keeps one record under
perdure/workflows/, opened before the first edit or as soon as planning or a
review reaches a decision; the work that follows continues in the same record.
The convention is the perdure plugin's docs/RECORDS-CONVENTION.md.

- Open with /perdure:start <slug>, with the plan and decisions written;
  update at checkpoints, not every turn.
- When a record opens, say so in one passing line; never ask whether to keep
  one.
- A dispatched agent works under the record of the session that dispatched it
  and opens none.
- When you pick a task back up from its record, say so first, in one line:
  `Resumed from perdure: <task>, next: <next step>`
- Close with /perdure:close, which runs scripts/close-workflow.py. Never set
  completed or abandoned by editing the record: the closer sets the canonical
  status, stamps it, records the outcome or the conscious skip
  (--skip-review "<reason>"), and creates or refreshes perdure/HANDOFF.md.
  Never declare a workflow done with an empty # Review section, and treat
  rot-lint findings before a record goes terminal.
- A plan that is dropped is closed as abandoned, with one line on why.
- Status vocabulary: in-progress (alias: active) | parked | completed |
  abandoned. Avoid "closed", "done", and "finished": they DO trip the close
  gate (the lint and the review gate run), but they sit outside the
  vocabulary, so the gate asks you to canonicalize them. Write a canonical
  terminal status, or let the deterministic closer set one for you.
- perdure/HANDOFF.md is DERIVED: only scripts/handoff.py (or /perdure:handoff)
  may write it. Never hand-write or hand-edit that page.
- With someone who does not code, call the record a note and say "where we
  left off". At the first note in a folder outside a repository, add: "These
  notes are plain files in this folder; anyone who can open it can read them.
  Tell me what is confidential and I'll leave it out."
- In the home folder, keep the notes in ~/perdure and say so.

Skip the record only when the whole task is one line in one file (a typo, a
one-line fix), or a question or brainstorm that decides nothing.

## Autonomous flows (claude -p, cron, CI)
Resolve the plugin's scripts ONCE, from Claude Code's own install manifest —
it names the ACTIVE install. (A bare `find ... | head -1` returns whichever
path the filesystem yields first: the cache keeps every version ever
installed, so that can be an obsolete one.)
`PERDURE="$(python3 -c "import json,pathlib;d=json.loads((pathlib.Path.home()/'.claude/plugins/installed_plugins.json').read_text());p=d.get('plugins',d);print(next(v[0]['installPath'] for k,v in p.items() if k.split('@')[0]=='perdure'))")/scripts"`

When dispatching autonomous work that needs a record (it changes files or
decides something), create the workflow file BEFORE dispatching, with its
plan and decisions — run the plugin's deterministic scaffolder (refuses to
overwrite):
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
the tool-agnostic counterpart as `AGENTS.md` at the **project root**:

- When `git rev-parse --show-toplevel` succeeds, the root is the path it
  prints: the repository root, which is not always the current directory.
- Otherwise the root is the current folder.

Refuse the home folder, and a folder holding several projects (two or more
subfolders that each hold `.git` or `perdure/`), even when git names it as the
root: dotfiles kept in `~/.git` make the home folder a repository. Skip, and
say why and what to do: "This is your home folder (or: a folder of N
projects), not a project, so AGENTS.md was not added here. Run
/perdure:install inside a project to add it there."

Default yes. Then:

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

## Step 1c: Codex (~/.codex/AGENTS.md)

Codex reads `AGENTS.md` in its folder (`$CODEX_HOME`, else `~/.codex`) in
every project, as Claude Code reads `~/.claude/CLAUDE.md`. When that folder
exists, place the block from `templates/AGENTS.user.md` there; when it does
not, skip without asking.

- If `~/.codex/AGENTS.md` does not exist: create it with the block.
- If it contains `<!-- perdure-records:begin -->`: compare the marker-bounded
  span against the template and refresh it if it differs; if identical,
  "Codex directive already installed. Skipping."
- If the file has no markers but already holds a records rule of its own (a line
  outside perdure's markers that names `/perdure:start` or
  `perdure/workflows/`), do not append a second rule. Report where it is: "Your Codex AGENTS.md already
  has a records rule (lines N-M). Enter keeps yours; "add" appends perdure's
  block anyway." When the markers are there too, refresh the block as above
  and name the lines outside it, since two rules can disagree.
- Otherwise append the block.

Never edit the user's lines outside the markers. Show the diff first and back
up to `.bak`, exactly as Step 1 does; enter applies, a decline is honoured
without argument. `/perdure:uninstall` removes the marker block again.

When `AGENTS.override.md` sits in the same folder, say so: "Codex reads
AGENTS.override.md instead of AGENTS.md while it exists, so this block is not
read until you move it there or remove the override." Never edit the override
file.

## Step 2: Preferences

If `~/.claude/perdure-preferences.json` exists, never rewrite it silently.
Compare it with the defaults below and report:

- values that differ from today's defaults (the key, your value, the default)
- keys the current schema ignores (the dropped keys listed below, or any other
  key it does not name)
- keys the file lacks, each with the value it takes while missing (below)
- its `schema-version`, against today's 4

A missing key takes the value the code reads, which is not always the default
this step writes:

| Key | Written by install | While missing |
|---|---|---|
| `auto-promote-decisions` | `heuristic` | `heuristic` |
| `auto-archive-before-compact` | `true` | off: the hook archives only on an explicit `true` |
| `rot-lint-at-close` | `true` | on |
| `handoff-regen-at-close` | `true` | on |
| `commit-archives` | `false` | off: archives stay gitignored |

So a file without `auto-archive-before-compact` archives nothing before
compaction; say so when you report that key.

If nothing differs: "Preferences match today's defaults." and go to Step 3.
Otherwise: "Enter keeps your file exactly as it is; "update" writes today's
defaults (your file is saved to .bak)." On "update", show the JSON, back up to
`.bak`, then write. Then Step 3.

With no preferences file: on enter, write the defaults below without asking.
On "adjust", ask (AskUserQuestion where available), each question with its
default marked:

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
report without re-deriving): `claude-md-directive` is `false` when Step 1 kept
the user's own rule or was declined. Other accepted values: `auto-promote-decisions`
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
  - ~/.claude/CLAUDE.md (marker block; .bak saved; or your own rule, kept)
  - ~/.claude/perdure-preferences.json (written, or kept as it was)
  - <project root>/AGENTS.md (marker block; .bak saved; unless skipped or
    declined)
  - <Codex's folder>/AGENTS.md (marker block; .bak saved; when Codex is
    installed and you did not decline it)

Start your next task normally: the record opens itself, plan first.
Or open one by hand: /perdure:start <slug>
Check health anytime: /perdure:health
Reverse everything:   /perdure:uninstall
```

## Safety rules
- Always show diffs before writing; always back up modified files to `.bak`
- Idempotent: re-running never duplicates entries (check the markers, and a
  records rule outside them, first)
- Never overwrite without confirmation; respect every skip
- This skill never touches settings.json permissions and never references
  other plugins' agents — perdure has no agent dependencies
