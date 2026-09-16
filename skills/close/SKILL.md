---
name: close
description: Close a workflow record properly — rot-lint it, verify the review
  gate, set the terminal status, fill the Outcome, run the ADR promotion pass,
  and regenerate the HANDOFF page. Use when work on a workflow is finished (or
  abandoned) and its record should go terminal without lying.
argument-hint: "[workflow-slug] [--abandon <reason>]"
---

# Close a Workflow Record

Resolve the record: `$1` as a slug → `perdure/workflows/<date>-<slug>.md`;
no argument → the sole `in-progress` workflow, else ask.

**Deterministic path (preferred — and the ONLY path in headless flows):** after
you have made sure `# Review` carries its verdict (step 2) and `# Outcome` its
prose (step 4), run

(`${CLAUDE_PLUGIN_ROOT}` is the plugin directory, set by Claude Code. Without
it, the same scripts sit in the plugin checkout's root `scripts/` directory (a
Codex install keeps the whole checkout), in `scripts/` beside this SKILL.md (a
skills-CLI install), or in your clone of `github.com/arbelh/perdure`.)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/close-workflow.py" <slug> [--abandon "<reason>"]
```

It performs steps 1, 3, and 6 mechanically — refuses on an empty `# Review`
(exit 4), refuses on lint findings (exit 3; `--force-lint` overrides, record
why), sets the canonical terminal status, bumps `updated:`, and regenerates the
HANDOFF page when one exists. Then finish with steps 5 and 7. The manual order below is the same
contract, spelled out:

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
beside this SKILL.md in a skills-CLI install) or an explicitly recorded skip with a reason.
Empty `# Review` on a completed workflow is a convention violation — offer
`/perdure:verdict <slug>` before closing, or record the conscious skip.

### 3. Set the terminal status

Frontmatter `status: completed` (or `abandoned`, appending the reason to the
record), and refresh `updated:`. The close-gate hook will re-lint automatically
on any later edit to this record — treat anything it injects.

### 4. Fill `# Outcome`

One short paragraph: what shipped/changed, where it landed (commits, tags,
deploys), and a one-line cost estimate when known
(`Cost: ~$X, ~N dispatches (estimate)`).

### 5. ADR promotion pass

Apply the `auto-promote-decisions` preference (modes and the scoring heuristic
are defined in the convention's *Operating the record* section). To promote:
`/perdure:decide <slug>`, then mark the workflow decision `[promoted → #NNN]`.

### 6. Regenerate the HANDOFF page

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/handoff.py" .
```

Never hand-edit the page. If `perdure/HANDOFF.md` does not exist yet, this
first close creates it: the page is derived from the records and can be
regenerated at any time. Projects that do not want the page set
`handoff-regen-at-close: false` in `~/.claude/perdure-preferences.json`.

### 7. Report

One line to the user: record path, final status, verdict, anything withheld or
deferred, and the follow-up workflow slug if blockers were deferred.

## Safety rules

- Never close over unreconciled lint findings without the user's explicit say-so
  (record the override if they insist).
- Terminal records are immutable except `supersedes:`/`continued-by:` links —
  continuing work gets a NEW record.
- This skill edits only the workflow record and the derived HANDOFF page.
