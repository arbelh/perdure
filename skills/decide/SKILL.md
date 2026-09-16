---
name: decide
description: Create a new Architecture Decision Record (ADR) in perdure/decisions/.
  Use for significant architectural, technological, or design choices that should be
  traceable months or years from now. Not for trivial decisions — those stay in
  workflow files.
argument-hint: "[slug] [title]"
---

# Create an Architecture Decision Record


You are creating a new ADR — a structured, immutable record of a significant
architectural or design decision. ADRs live in `perdure/decisions/` and survive
workflows, sessions, and time.

## When to use this skill

Create an ADR for decisions that:
- Affect architecture, data model, or system boundaries
- Have trade-offs worth documenting (chose X over Y because Z)
- Future engineers (or you in 6 months) will ask "why did we do this?"
- Cross multiple workflows or live beyond a single feature

**Don't create an ADR for**:
- Trivial implementation details (indentation, variable names)
- Single-file bug fixes
- Anything reversible with a one-line change

If unsure, ask the user: "Is this an architectural decision or an implementation detail?"

## Steps

### 1. Verify the directory
If `perdure/decisions/` doesn't exist, create it.
If `perdure/decisions/INDEX.md` doesn't exist, create it with the skeleton (see step 5).

### 2. Resolve slug, ID, and filename

**Slug**: from `$1` or ask the user (kebab-case, e.g., `sqlite-over-redis`).

**ID**: next available 3-digit number based on existing ADRs:
```
ls perdure/decisions/*.md | grep -oE '[0-9]{3}' | sort -n | tail -1
```
Increment by 1. Pad to 3 digits (001, 002, ..., 100, 101).

**Filename**: `YYYY-MM-DD-<id>-<slug>.md`
Example: `2026-05-10-005-sqlite-over-redis.md`

### 3. Gather information

Ask the user (or infer from context) for:
- **Title** (one line, plain English)
- **Context** — what's the situation that required this decision?
- **Decision** — what was chosen?
- **Alternatives considered** — what other options were weighed and why rejected?
- **Consequences** — positive and negative outcomes
- **Tags** — categorization keywords (e.g., `auth`, `cost`, `agent-config`)
- **Related workflow(s)** — slug(s) of workflow(s) this decision came from (optional)
- **Implementing commits** — git SHAs if applicable (optional; can backfill later)

When promoting an existing workflow decision, pre-fill these from the workflow file.

### 4. Create the ADR file

Write the file with this exact schema:

```markdown
---
id: <3-digit ID>
title: <title>
status: accepted
date: <YYYY-MM-DD>

# Linkage
supersedes: []
superseded-by: []
related-decisions: []
related-workflows: [<slug> or empty]

# Implementation tracking
implementing-commits: []
implementing-files: []

# Discoverability
tags: []
---

# Context

<what situation required this decision>

# Decision

<what was chosen and the core reasoning>

# Alternatives considered

- **<Alternative 1>**: <why rejected>
- **<Alternative 2>**: <why rejected>

# Consequences

**Positive**:
- <benefit 1>
- <benefit 2>

**Negative**:
- <trade-off 1>

**Neutral**:
- <side effect>

# References

- Workflow: <link to workflow file if any>
- Related commits: <SHAs if known>
```

### 5. Update INDEX.md

If INDEX.md doesn't exist, create with this skeleton:

```markdown
---
type: orchestrator-decisions-index
updated: <ISO-8601 timestamp>
schema-version: 1
---

# Decisions Index

## Active — currently in force

| ID | Title | Accepted | Tags |
|----|-------|----------|------|

## Superseded

| ID | Title | Superseded by | Date |
|----|-------|---------------|------|

## Deprecated

| ID | Title | Deprecated | Reason |
|----|-------|------------|--------|

## Rejected

| ID | Title | Date | Reason |
|----|-------|------|--------|
```

Add the new ADR to the **Active** section:
```
| <id> | [<title>](<filename>) | <date> | <tags> |
```

Update the `updated:` frontmatter timestamp.

### 6. Check .gitignore

Ask the user: "Commit `perdure/decisions/` to git?"
- **Recommended: yes** (ADRs are team-facing, long-term team context)
- If they say no, add `perdure/decisions/` to `.gitignore`

Same default as workflow files — both are committed by default (docs/RECORDS-CONVENTION.md, also at
references/RECORDS-CONVENTION.md beside this SKILL.md in a skills-CLI install); archives remain the gitignored privacy layer. Note: records carry no `authors` frontmatter by design — git already carries authorship once, and records document work, not workers.

### 7. Report

```
✅ ADR created: #<id> <title>

File: perdure/decisions/<filename>
Status: accepted
Added to INDEX.md Active section

Next steps:
  - Review the ADR and edit any section that needs more detail
  - Commit if your team shares ADRs
  - View all: /perdure:decisions
```

## Safety rules

- Never overwrite an existing ADR file
- Always increment ID atomically (check existing files first)
- Never set `status: superseded` on creation (that's only set later)
- Keep ADR files immutable after `status: accepted` except:
  - Adding `superseded-by` when a new ADR supersedes this
  - Updating status to `deprecated` with reason
  - Backfilling `implementing-commits` after code ships
- Always update INDEX.md in the same operation as ADR file creation
