---
name: continue
description: Resume a previously started perdure workflow. Reads the workflow's
  persistent state file, re-injects its plan, findings, decisions, and current step
  into the conversation so the session can continue where it left off — even
  after compaction, /clear, or a new session. Use when coming back to a task
  that was paused.
disable-model-invocation: true
argument-hint: "[slug]"
---


# Resume a Workflow


You are restoring a workflow's state so work can continue.

## Arguments
- `$1` — the workflow slug (or partial match). Example: `add-jwt-refresh`
- If no argument, scan `perdure/workflows/*.md` for active workflows and ask which to resume.

## Steps

### 0. Check the HANDOFF page
- If `perdure/HANDOFF.md` holds merge-conflict markers (a line starting with
  `<<<<<<< `, then `=======` or `>>>>>>> `), read each side on its own: the
  lines outside the conflicts plus that side's half of each one.
- Regenerate the page only when every side carries the generator's stamp, as
  the close-gate hook does: the side starts with `# HANDOFF`, and one of its
  next four lines starts with `> Derived orientation page, generated`. Say so
  in one line: the page is derived, so a conflict is never resolved by hand.
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/handoff.py" .`
  (step 3b says where the scripts are without `${CLAUDE_PLUGIN_ROOT}`)
- When a side lacks the stamp, someone wrote it by hand. Leave the page as it
  is, say so in one line, and go on with the resume. Do not ask.

### 1. Locate the workflow file
- If `$1` provided: find `perdure/workflows/*<$1>*.md` that matches (also check `<YYYY>/` subdirectories for aged terminal files)
- If multiple match: show options and ask user to pick
- If none match: list the closest-named files and suggest alternatives

### 2. Read the workflow file
- Read the full workflow file (the schema is `docs/RECORDS-CONVENTION.md`, also at
  `references/RECORDS-CONVENTION.md` beside this SKILL.md in a skills-CLI install; real files may be
  freeform — read what's there)

### 3. Check status
- If `status: completed` or `status: abandoned`: warn the user and ask whether to
  reopen (changes status back to `in-progress`) or just display the state
- If `status: in-progress`: proceed with resumption

### 3b. Check the plan
- If `# Plan` still holds the scaffold placeholder or has no items, write the
  plan now from the goal, the diff and what is left, before continuing; say so
  in the resume message. The lint reports this as `placeholder`.
- To see it, run the lint on the record:
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rot-lint.py" <workflow-file>`
  (`${CLAUDE_PLUGIN_ROOT}` is the plugin directory, set by Claude Code. Without
  it, the same script sits in the plugin checkout's root `scripts/` directory,
  or in `scripts/` beside this SKILL.md in a skills-CLI install.)

### 4. Re-inject state into conversation
Present to the user and load into context. The first line is always the
resume line: the task in a few words (the slug, or the goal shortened) and
the record's `# Next step`:

```
Resumed from perdure: <task>, next: <next step>

## Resuming workflow: <slug>

**Goal**: <goal>
**Started**: <started> · **Last updated**: <updated>

### Plan progress
<plan section, with checkboxes showing completion>

### Key findings so far
<findings section summary>

### Key decisions made
<decisions section summary>
(Each holds as written. A later record that changed one names this record on
its line; if another record disagrees and neither names the other, hold both
as unresolved rather than picking by tone.)

### Files modified so far
<files modified section>

### Open questions
<open questions section>

### Next step
<next step from the file>

---
Ready to continue? I'll pick up from "<next step>".
```

### 5. Update metadata
- Update the `updated:` timestamp in the workflow file's frontmatter
- If status was changed from completed/abandoned → in-progress, note the reopen
  under `# Decisions` AND annotate the existing `# Review` verdict block as
  `(pre-reopen)` — re-completing this workflow requires a NEW verdict (or a new
  recorded skip) covering the post-reopen work, per docs/RECORDS-CONVENTION.md.
  (Terminal files are normally immutable — prefer a new file, adding a
  `continued-by:` link to the old one per the convention; reopen only when the
  user explicitly chooses it. The convention's other exception is a decision
  renumbering, in the decide skill's step 5.)

### 6. Continue the work
After resumption, continue from `# Next step` however this session works —
inline, or through whatever agents the user has. Do not start editing on a
placeholder plan: step 3b writes one first. Close through the gate when
done (`/perdure:verdict`, then `/perdure:close`).

## Safety rules

- **Never modify** content of Findings, Decisions, Files modified sections — those
  are historical record. Two exceptions: the close pass's append-only promotion
  annotations, and a decision renumbering after two branches took one number
  (the decide skill's step 5)
- **Always show** the user what's being restored before injecting into context
- **Respect completed/abandoned status** — reopening requires explicit user confirmation
- **Graceful missing file**: if no workflow matches, say so clearly and suggest
  `/perdure:list` to list available ones
