---
name: close
description: Close a workflow record properly — rot-lint it, verify the review
  gate, run the promotion pass, name any earlier decision this record changes,
  then run the closer, which sets the terminal status and creates or regenerates
  the HANDOFF page. Use when work on a workflow is finished (or
  abandoned) and its record should go terminal without lying.
argument-hint: "[workflow-slug] [--abandon <reason>] [--skip-review <reason>]"
---

# Close a Workflow Record

Resolve the record: `$1` as a slug → `perdure/workflows/<date>-<slug>.md`;
no argument → the sole `in-progress` workflow, else ask.

**The closer sets the status, in every mode.** Steps 1 to 5 prepare the record;
step 6 runs `close-workflow.py`, which flips the status. Never set `completed`
or `abandoned` by editing the frontmatter: a hand-set status skips the
canonical status and `updated:` stamp, the recorded skip or Outcome line, and
the page a project gets at its first close. Measured 2026-09-17: three of five
headless closes were hand edits, and each left those behind. The close-gate
hook names a hand-close when it sees one and sends you here.

(`${CLAUDE_PLUGIN_ROOT}` is the plugin directory, set by Claude Code. Without
it, the same scripts sit in the plugin checkout's root `scripts/` directory (a
Codex install keeps the whole checkout), in `scripts/` beside this SKILL.md (a
skills-CLI install), or in your clone of `github.com/arbelh/perdure`.)

### 1. Rot lint first

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rot-lint.py" <workflow-file>
```

Reconcile anything it prints before proceeding (advisory output — contradicting
lines side by side; status-vs-git flags need a human eye). Corrections follow
the convention's *Correcting a record* rules: fix status headers in place with
a short dated note; paraphrase retracted claims, never re-quote them; time-scope
surviving negatives. A record must not go terminal while its status lies.

### 2. Verify the review gate

The `# Review` section must carry a verdict block (schema in
`docs/RECORDS-CONVENTION.md`, also at `references/RECORDS-CONVENTION.md`
beside this SKILL.md in a skills-CLI install) or an explicitly recorded skip
with a reason. Offer `/perdure:verdict <slug>` before closing. With no reviewer
available, the closer's `--skip-review "<reason>"` writes the convention's
recorded skip and closes on it; the skip becomes part of the record.

### 3. Decisions that change an earlier record

For each line under `# Decisions`: does it change a decision recorded in an
earlier record? If so, name that record's date-slug on the line and say why
(`changes 2026-05-12-cache-warmup: TTL 300 → 60, because …`). If the earlier
decision is an ADR, supersede it with `/perdure:decide` instead. Two records
that disagree and name neither are unresolved for every later reader; naming
is what makes the change as loud as the original.

### 4. Promotion pass

Promote a decision when a task that never reads this record must still obey
it — a default, a name, a boundary, a rule — and it can be stated in one
sentence without this task's filenames. Size does not matter: a one-line
default other tasks inherit qualifies; a ten-file refactor's local choices do
not. Apply the `auto-promote-decisions` preference (`none` lists and asks,
`tagged` takes `{promote}` marks, `heuristic` applies this test, `all`
promotes everything). Two homes: an ADR via `/perdure:decide <slug>` when the
why and the alternatives matter, marking the decision `[promoted → #NNN]`; or,
when only the rule matters, propose a one-line addition to the project's
instruction file (`CLAUDE.md` or `AGENTS.md`) for the user to place — perdure
never writes outside `perdure/`.

### 5. Fill `# Outcome`

One short paragraph: what shipped or changed, where it landed (commits, tags,
deploys), and a one-line cost estimate when known
(`Cost: ~$X, ~N dispatches (estimate)`). The closer can append it for you
with `--outcome "<text>"`.

### 6. Run the closer

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/close-workflow.py" <slug> [--abandon "<reason>"] [--skip-review "<reason>"] [--outcome "<text>"]
```

It refuses on an empty `# Review` (exit 4) unless `--skip-review` records the
skip, refuses on lint findings (exit 3; `--force-lint` overrides, record why),
sets the canonical terminal status, stamps `updated:`, appends the abandon
reason or outcome, and creates the HANDOFF page at a project's first close or
regenerates it after. On a record that is already terminal it verifies (lint,
`# Review` present) and creates or refreshes the page, exit 0; with `# Review`
empty it refuses on the lint's finding (exit 3), with the section absent on the
gate (exit 4), in both cases unless `--skip-review` records the skip, the one
write it makes to a terminal record; `--outcome` is ignored there. Projects that do
not want the page set `handoff-regen-at-close: false` in
`~/.claude/perdure-preferences.json`. Never hand-edit the page.

### 7. Report

One line to the user: record path, final status, verdict or recorded skip,
anything withheld or deferred, and the follow-up workflow slug if blockers
were deferred.

## Safety rules

- Never set a terminal status by editing the record; the closer sets it.
- Never close over unreconciled lint findings without the user's explicit
  say-so (record the override if they insist).
- Terminal records are immutable except `supersedes:`/`continued-by:` links —
  continuing work gets a NEW record.
- This skill edits only the workflow record and the derived HANDOFF page.
