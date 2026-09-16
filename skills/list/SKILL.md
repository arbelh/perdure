---
name: list
description: List all perdure workflows in the current project. Scans
  perdure/workflows/*.md directly and shows active, parked, completed, and
  abandoned workflows. Use to see what's in progress, what's done, and what to
  resume.
disable-model-invocation: true
disallowed-tools: Edit, Write, NotebookEdit
---

# List Workflows

> **Not the same as Claude Code's built-in `/workflows`.** That lists Dynamic
> Workflow runs (ephemeral in-session scripts). This lists the perdure plugin's
> **durable, cross-session workflow state files** under `perdure/workflows/`.

## Steps

### 1. Scan the files directly

List `perdure/workflows/*.md` (and `perdure/workflows/*/*.md` — terminal files
may be aged into `<YYYY>/` subdirectories). **Skip `INDEX.md` if present** — it's
a legacy artifact, not a workflow file. There is no index file to maintain or
trust: the files ARE the source of truth. For each file, read just enough to get
its status and current step — the frontmatter block when present (`workflow:`,
`status:`, `updated:`), else the first heading lines. Real files are freeform
markdown; missing frontmatter means "read the first ~20 lines and infer".

If the directory doesn't exist or is empty: say
"No workflows yet. Start one with `/perdure:start <slug>`" and exit.

### 2. Display

```
## Active workflows (2)

| Slug | Goal | Next step | Updated |
|------|------|-----------|---------|
| add-jwt-refresh-tokens | Add JWT refresh flow | Implement refresh endpoint | 2026-04-17 |
| migrate-auth-db | Move auth to separate DB | Blocked on infra | 2026-04-16 |

Completed: 3 · Parked: 1 · Abandoned: 1  (ask to see details)

Resume: /perdure:continue <slug> · New: /perdure:start <slug>
```

### 3. Staleness hint (soft)

Flag active workflows not updated in >7 days as "stale — resume, park, or close?".
Never block or fail — a gentle hint only.

## Safety rules

- **Read-only** — never modify files
- **Graceful when empty**
- **Always offer the next action** (resume / start)
