---
name: decisions
description: List architectural decision records (ADRs). Shows active decisions by
  default; --all adds every status plus decisions recorded inside workflow files;
  --reindex rebuilds perdure/decisions/INDEX.md from the ADR files' frontmatter.
disable-model-invocation: true
argument-hint: "[--all] [--reindex] [--tag <tag>] [--workflow <slug>] [--status <status>]"
---

# List Architecture Decision Records

Read-only by default; `--reindex` is the one action that writes (it rebuilds
INDEX.md only — never the ADR files themselves). The ADR schema is defined in
`docs/RECORDS-CONVENTION.md` (also at `references/RECORDS-CONVENTION.md` beside this SKILL.md in a skills-CLI install).

## Arguments

| Flag | Effect |
|------|--------|
| (none) | Show Active ADRs (what's in force now) |
| `--all` | Show every status section, PLUS decisions recorded in workflow files' `# Decisions` sections (with `{promote}` candidates flagged) |
| `--reindex` | Rebuild `perdure/decisions/INDEX.md` from the ADR files' frontmatter |
| `--tag <name>` / `--workflow <slug>` / `--status <name>` | Filters |

## Steps

### 1. Verify prerequisites

ADRs live at `perdure/decisions/`. If no ADR directory exists, report "No decisions recorded yet. Create one:
`/perdure:decide <slug>`" and exit gracefully.

### 2. Read

Read `perdure/decisions/INDEX.md` and parse its status sections. If the INDEX is
missing, or an ADR you touch contradicts its INDEX section, say so and offer
`--reindex` (don't rebuild without being asked).

### 3. `--reindex` (when requested)

1. Scan every `perdure/decisions/*.md` except INDEX.md; parse frontmatter
   (`id`, `title`, `status`, `date`, `tags`, `superseded-by`).
2. Validate: 3-digit `id`, status ∈ proposed/accepted/superseded/deprecated/rejected,
   non-empty title. Report malformed files; skip them.
3. Rewrite INDEX.md grouped by status (Active = proposed+accepted), newest first,
   one table row per ADR linking to its file. Show the diff before writing.

### 4. `--all` — include workflow decisions

Scan `perdure/workflows/*.md` files' `# Decisions` sections. Show them grouped by
workflow with status, after the ADR sections. Flag entries marked `{promote}` as
promotion candidates (`/perdure:decide <slug>` promotes; `/perdure:close`
also offers promotion at close per the `auto-promote-decisions` preference).
Skip entries already marked `[promoted → #NNN]`.

### 5. Output

Plain markdown tables — ID, title, date, tags per row — one section per status
shown, then a one-line total (`N active, N superseded, …`). To read a specific
ADR: `cat perdure/decisions/<filename>`.

## Safety rules

- Never modify ADR files; `--reindex` rewrites INDEX.md only, diff shown first
- Never suppress a detected INDEX/file mismatch
- Work offline — no network calls
- If an ADR can't be read, log and continue
