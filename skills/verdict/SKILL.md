---
name: verdict
description: Run the workflow's closing review gate — obtain an independent
  substantive review of a defined scope (a workflow's modified files, a path, or
  an explicit list) and append the verdict to the workflow file in the records
  convention's schema. Use after implementation is complete and before declaring
  a workflow done. Accepts any independent reviewer — a reviewer the user names,
  an installed review agent, a generic read-only subagent carrying the inline
  rubric below, or a human — returning APPROVE / APPROVE WITH IMPROVEMENTS /
  DENY with file:line evidence.
argument-hint: "[workflow-slug | path | --files <a,b,c>] [--depth quick|full|security]"
---

# The Review Gate

## Why this gate exists

Empirical finding (9+ dogfood cycles, May 2026): without an explicit gate, the
review step gets silently skipped — code ships on passing tests + clean
type-checks alone. When an independent reviewer IS engaged, it finds real bugs
the other signals miss: concurrency corruption, ADR violations, security gaps,
coverage theater.

**The gate checks the record, not the producer.** What must exist before a
workflow is `completed` is a verdict block in its `# Review` section, in the
schema below (canonical copy: `docs/RECORDS-CONVENTION.md`, also at
`references/RECORDS-CONVENTION.md` beside this SKILL.md in a skills-CLI install). Any independent
reviewer satisfies the gate — another plugin's review agent, a generic
subagent, a human — as long as its verdict lands in this schema. The reviewer
never writes the record; this skill (the parent session) appends it.

## Steps

### 1. Resolve the review scope — artifact-scoped by default

In priority order:
1. **`$1` as a path** that exists → review that file/directory.
2. **`$1` as a workflow slug** → `perdure/workflows/<date>-<slug>.md`'s
   `# Files modified` section is the scope.
3. **`--files a,b,c`** → explicit list.
4. **Sole in-progress workflow** → its `# Files modified`.
5. Otherwise ask.

**Scope to the artifact — the workflow's modified files or the diff — not the
whole repository.** Unscoped repo-wide reviews cost several times more for
little added signal on a bounded change; broaden deliberately only when the
change plausibly breaks distant code. Confirm the scope with the user before
dispatch: *"Reviewing N files: <list> — proceed?"*

### 2. Depth

`--depth quick` (bugs/security only) · `full` (default: correctness,
readability, architecture, security, performance) · `security`.

### 3. Obtain the independent review

Resolve the reviewer in this order — first match wins:

1. **A reviewer the user names** (an agent type, another plugin's review
   skill, or "I'll review it myself") always wins.
2. **A review-focused agent already installed** in this session's Agent tool
   roster (any plugin's reviewer or code-review agent). Dispatch it with the
   scope, depth, and the rubric below.
3. **A generic read-only subagent** (the built-in Agent tool, fresh context,
   no plugin required), carrying the full rubric below as its prompt.
4. **A human-authored verdict** pasted in the schema satisfies the gate with
   no dispatch at all.

Rubric — include it whatever the producer:

```
You are reviewing freshly-implemented code at <scope>.
[Context: what the code does, from the workflow file's Goal]

Sycophantic approval is the failure mode we detect for. If the code is good,
say so with evidence; if anything is questionable — security, race conditions,
hidden bugs, coverage gaps, ADR violations — surface it and push back. Do not
over-praise. Quantify concerns.

## Focus areas: [domain-specific, security-critical paths first]
## ADR alignment: [list perdure/decisions/ entries; verify adherence to each]
## Test coverage: adversarial or happy-path? coverage theater vs real validation?

## Output format
# Review summary
[APPROVE / APPROVE WITH IMPROVEMENTS REQUESTED / DENY]
# Critical findings (block ship) — finding + evidence <file>:<line> + fix
# Improvements requested (non-blocking)
# Observations
# What was good
```

Never simulate the review from this session — an independent pass is the point.
Never manipulate the reviewer's pushback.

### 4. Surface the verdict

Verdict prominently; critical findings as a numbered `file:line` list;
improvements collapsed if many; "what was good" for calibration.

### 5. Append the verdict block to the workflow file

```markdown
# Review

- **Verdict**: APPROVE WITH IMPROVEMENTS REQUESTED
- **Reviewer**: <agent type, tool, or person>
- **Reviewed at**: <ISO 8601>
- **Reviewed SHA**: <git rev-parse HEAD; UNVERSIONED if no repo>
- **Reviewed scope**: <files>
- **Critical findings**: <N, one line each>
- **Improvements requested**: <N, one line each>
- **Disposition**: addressed | deferred to follow-up | accepted as-is
```

Re-reviews APPEND a new block — never overwrite; every review cycle stays in the
record.

### 5b. Rot check before any close

(`${CLAUDE_PLUGIN_ROOT}` is the plugin directory, set by Claude Code. Without
it, the same scripts sit in the plugin checkout's root `scripts/` directory (a
Codex install keeps the whole checkout), in `scripts/` beside this SKILL.md (a
skills-CLI install), or in your clone of `github.com/arbelh/perdure`.)

Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rot-lint.py" <workflow-file>` and show
the user anything it flags (advisory — it prints contradicting lines side by
side; status-vs-git flags need a human eye since commits by other work on
shared files can trigger them). A workflow must not be marked `completed`
while its status header contradicts its own body or git. (The close-gate
hook re-runs this lint automatically whenever an edit lands on a
record that already carries a terminal status — treat anything it injects the
same way. This manual step still matters for records with freeform status
lines, which the hook's gate deliberately skips.)

### 6. Ask what's next

- **DENY**: fix and re-review / defer blockers to a follow-up workflow / user
  overrides (mark completed WITH the denial and an explicit override reason in
  the record — never silently).
- **APPROVE WITH IMPROVEMENTS**: fix now / defer (create the follow-up) / accept
  as known follow-ups.
- **APPROVE**: mark the workflow completed?

### 7. Headless behavior

No user to ask: end your output with a machine-parseable final line —
`VERDICT: APPROVE` / `VERDICT: APPROVE WITH IMPROVEMENTS` / `VERDICT: DENY` /
`VERDICT: ERROR — <reason>` — so a calling script can grep it (a skill cannot
set the CLI process's exit code). The verdict block is still appended; on DENY
the workflow stays `in-progress` for the caller.

## Anti-patterns

- Reviewing code you didn't change (scope to the artifact)
- Prompt-manipulating the reviewer into approval
- Marking a workflow completed after DENY without a recorded, explicit override

## Cost

Cost depends on the producer. A full artifact-scoped review by a strong-model
agent typically runs 30K–100K tokens (~$0.50–$3); the generic-subagent
fallback inherits the session model. Either way it is a fraction of an
unscoped repo-wide pass — scope to the artifact.
