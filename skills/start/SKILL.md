---
name: start
description: Start a new perdure workflow with a persistent state file. Writes
  the plan and the decisions before the first edit, then creates
  perdure/workflows/YYYY-MM-DD-<slug>.md per the records convention and prepares
  the state structure to be updated at each checkpoint. Use at the start of any
  complex multi-step task that should survive compaction, /clear, or be resumable
  later — this is the entry point of the golden loop (start → work → review gate
  → close/archive).
argument-hint: "[slug]"
---

# Start a New Workflow


You are creating a persistent workflow state file. This file survives compaction,
session ends, and `/clear` — the work can always be resumed from it, by you, a
teammate, or a fresh agent reading the repo.

**The loop this starts:** `start` → the work (done however you work
by judgment; the main session always has the Agent tool) → **review gate**
(`/perdure:verdict`) → close/archive. One loop, every task shape.

> **Not a Dynamic Workflow.** Claude Code's built-in Dynamic Workflows (`ultracode`)
> are ephemeral in-session scripts; this skill creates a **durable state file** that
> persists across sessions. The two compose — a Dynamic Workflow can be the execution
> engine inside a tracked workflow.

## Arguments
- `$1` — the workflow slug (lowercase, hyphens). Example: `add-jwt-refresh-tokens`.
- If absent, derive one from the task in context or ask the user.

## Steps

### 1. Write the plan and the decisions before touching code

From the request as it stands, draft three things:

- **The plan**, as checkboxes: the deliverables the user named, one per line,
  including the tests and the docs when the request asks for them.
- **The decisions** the request already settles: the constraints it fixes, the
  approaches it rules out, and why.
- **The first next step** — the resume point a fresh session would start from.

Do this before reading or editing any project file. If you cannot plan yet, the
first item is the exploration itself and the second is "write the plan from what
exploration shows". Never leave the scaffold placeholder lines: a placeholder
plan is a lint finding (`placeholder`) and the closer refuses to close over it.

A record whose plan was never written exists but carries nothing: a session
resuming from it reads a goal and starts over.

### 2. Create the workflow file

The canonical schema (frontmatter keys, recommended sections, statuses, commit
policy) is `docs/RECORDS-CONVENTION.md` in this plugin, also at
`references/RECORDS-CONVENTION.md` beside this SKILL.md in a skills-CLI install — defer to it. Concretely:

```bash
mkdir -p perdure/workflows
```

Write `perdure/workflows/<YYYY-MM-DD>-<slug>.md`:

```markdown
---
workflow: <slug>
status: in-progress
started: <ISO 8601>
updated: <ISO 8601>
---

# Goal
<1-3 sentences — ask the user if not clear from context>

# Plan
- [ ] <the plan items from step 1 — never the scaffold placeholder>

# Findings

# Decisions
- <the decisions from step 1, if the request settles any>

# Files modified

# Open questions

# Next step
<the first next step from step 1>

# Review
<empty until the review gate runs>

# Outcome
```

If the file already exists, STOP and suggest `/perdure:continue <slug>` or a
different slug. Never overwrite.

These sections are the recommended shape, not a validation gate — real workflow
files are freeform markdown, and that's fine. Update at checkpoints, not every turn.

Workflow files are **committed by default** — they are the context a checkout
carries for whoever picks the work up next. (Archives are the opt-in privacy
layer, not these.)

### 3. Report

```
✅ Workflow started: <date>-<slug>
Location: perdure/workflows/<date>-<slug>.md

Update it at each checkpoint. Resume anytime: /perdure:continue <slug>
List workflows: /perdure:list
```

Then surface the **gate reminder**:

```
Loop closure: when implementation is complete, run /perdure:verdict <slug>
before declaring the workflow done. Tests + type-checks are necessary but not
sufficient; the reviewer catches what they miss. The verdict is appended to
this file's # Review section — an empty # Review on a completed workflow is a
gate violation. To skip consciously, record "Review: skipped — <reason>" in
its place; the skip itself becomes part of the record.
```

## Autonomous / zero-turn creation

For `claude -p`, cron, or CI flows where the file should exist deterministically
before any model turn:

(`${CLAUDE_PLUGIN_ROOT}` is the plugin directory, set by Claude Code. Without
it, the same scripts sit in the plugin checkout's root `scripts/` directory (a
Codex install keeps the whole checkout), in `scripts/` beside this SKILL.md (a
skills-CLI install), or in your clone of `github.com/arbelh/perdure`.)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/new-workflow.py" <slug> --goal "<goal>" \
  --plan "<item>" --plan "<item>" --decision "<text>" --next "<first step>"
```

Same schema, no model involvement, refuses to overwrite (exit 2 if exists).
`--plan` and `--decision` repeat. Left out, `--plan` keeps the placeholder line
and the script says so on stderr — the lint then reports it as `placeholder`.

## Safety rules

- **Never overwrite** an existing workflow file
- **Single writer** during active work; updates at checkpoints, concise entries
- **Idempotent**: same slug twice → detect and refuse
