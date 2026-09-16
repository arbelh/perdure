---
name: continue
description: Resume a previously started perdure workflow. Reads the workflow's
  persistent state file, re-injects its plan, findings, decisions, and current step
  into the conversation so the session can continue where it left off — even
  after compaction, /clear, or a new session. Use when coming back to a multi-step
  task that was paused.
disable-model-invocation: true
argument-hint: "[slug]"
---


# Resume a Workflow


You are restoring a workflow's state so work can continue.

## Arguments
- `$1` — the workflow slug (or partial match). Example: `add-jwt-refresh`
- If no argument, scan `perdure/workflows/*.md` for active workflows and ask which to resume.

## Steps

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

### 4. Re-inject state into conversation
Present to the user and load into context:

```
## Resuming workflow: <slug>

**Goal**: <goal>
**Started**: <started> · **Last updated**: <updated>

### Plan progress
<plan section, with checkboxes showing completion>

### Key findings so far
<findings section summary>

### Key decisions made
<decisions section summary>

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
  user explicitly chooses it)

### 6. Continue the work
After resumption, continue from `# Next step` however this session works —
inline, or through whatever agents the user has. Close through the gate when
done (`/perdure:verdict`, then `/perdure:close`).

## Safety rules

- **Never modify** content of Findings, Decisions, Files modified sections — those
  are historical record
- **Always show** the user what's being restored before injecting into context
- **Respect completed/abandoned status** — reopening requires explicit user confirmation
- **Graceful missing file**: if no workflow matches, say so clearly and suggest
  `/perdure:list` to list available ones
