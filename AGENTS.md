# AGENTS.md

This repository is the **perdure** plugin: one markdown record per task,
committed and checked. Any tool that can read a repository can follow the
convention below, and any tool that can run `python3` can run the checks from
this checkout — `scripts/rot-lint.py .` and `scripts/handoff.py . --check`.

The stanza between the markers is what `/perdure:install` offers to add to a
project's own AGENTS.md. It applies here as well: work on this repository keeps
its records under `perdure/`.

<!-- perdure-records:begin -->
## Records

This project keeps a decision trail under `perdure/`. It is kept with the
project (committed, when the project is a repository), and it is checked. Any
tool that can read the project's files can read it, and any tool that can run
`python3` can run the verification.

Four rules, then the detail:

- Any task that changes files or decides something keeps one record under
  perdure/workflows/, opened before the first edit or as soon as planning or a
  review reaches a decision; the work that follows continues in the same record.
- A record closes only with a review verdict, or a recorded reason for skipping one.
- `perdure/HANDOFF.md` is generated from the records, never edited by hand.
- A record is closed by `close-workflow.py` (the `close` skill runs it), never by
  editing its status: the closer stamps it, records the outcome or the skip, and
  creates or refreshes the page.

### Before you start

Read `perdure/HANDOFF.md`. It is generated from the records, never
hand-written, and it names what is currently in force, what is still open, and
which records are flagged as unreliable. A record listed under *Needs
reconciliation* contradicts itself somewhere, so do not build on it without
reading it first.

When you pick a task back up from its record, say so first, in one line:
`Resumed from perdure: <task>, next: <next step>`.

### With the perdure skills installed

Any tool that carries the plugin's skills has one for each stage. Use it rather
than working by hand:

- Starting a task → `start`
- Picking work back up → `continue`
- Finished, before declaring done → `verdict`, then `close`
- Asking where things stand → `handoff`
- A decision that should outlive the task → `decide`

Under Claude Code these are `/perdure:<name>`. Without the skills, the sections
below are the same contract, followed by hand.

### Writing a record

When a record opens, say so in one passing line; never ask whether to keep
one. A dispatched agent works under the record of the session that dispatched
it and opens none.

Open the record at `perdure/workflows/YYYY-MM-DD-slug.md` with its plan and
decisions written, and keep it current at each checkpoint:

```markdown
---
workflow: slug
status: in-progress
started: 2026-01-01T09:00:00-07:00
updated: 2026-01-01T09:00:00-07:00
---

# Goal
# Plan
# Findings
# Decisions
# Files modified
# Open questions
# Next step
# Review
# Outcome
```

Three fields carry weight beyond documentation:

- **`status`** must be one of `in-progress`, `parked`, `completed`, `abandoned`.
  Two checks key on this vocabulary and skip a record whose status they cannot
  classify, so `in progress` with a space silently disables them.
- **`# Review`** must hold a verdict, or a recorded reason for skipping one,
  before the status goes terminal.
- A decision under **`# Decisions`** that changes a decision recorded in an
  earlier record names that record on its line and says why.

A plan that is dropped is closed as abandoned, with one line on why.

Skip the record only when the whole task is one line in one file (a typo, a
one-line fix), or a question or brainstorm that decides nothing.

Write it anyway when you notice yourself thinking:

- "I'll write the record after." The record is where decisions go as they are
  made; afterwards they are already gone.
- "The commit message covers it." A commit says what changed, not what was
  rejected or what is still open.
- "Tests passed; the review is a formality." Tests are necessary and not
  sufficient; the verdict is what the closer checks for.

### Do not

- Hand-edit `perdure/HANDOFF.md`. It is regenerated, and a hand edit is
  detected rather than merged.
- Resolve a merge conflict in `perdure/HANDOFF.md` by hand. Regenerate it from
  the merged records (`handoff.py .`) and commit the result.
- Re-quote a claim a record has retracted. Paraphrase it instead, so the
  retracted wording does not read as current.
- Mark a record terminal to tidy it up. `parked` and `abandoned` exist.

### The trail is checked

The verification lives in the perdure plugin's `scripts/` directory, or beside
any installed skill that runs it. Three commands take the project root and exit
non-zero on a real problem, so they run in CI or a pre-commit hook regardless of
which tool did the work:

```
rot-lint.py --strict .      # a record contradicts itself, or two decisions share a number
handoff.py . --check        # the generated page no longer matches its sources
close-workflow.py <slug>    # refuses a close with no review verdict (--skip-review "<reason>" records a conscious skip)
```

If this repository defines a local entry point for these, prefer it. Under
Claude Code a hook re-runs the lint on its own when a record closes; in any
tool, the `close` skill runs it, and CI can run it too.

The full record format and the complete list of checks are in the plugin's
`docs/RECORDS-CONVENTION.md`, and `docs/THREE-LAYERS.md` explains why the trail
is split into what was asserted, what was observed, and what a script can
confirm.
<!-- perdure-records:end -->
