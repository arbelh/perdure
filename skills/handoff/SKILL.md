---
name: handoff
description: Generate (or freshness-check) the HANDOFF page — a
  derived one-page orientation view at perdure/HANDOFF.md built only from
  records that pass the record-rot lint. Use before handing work off, after
  closing a workflow, or when someone asks "where do we stand?". Pass
  --check to verify the committed page still matches the records.
---

# HANDOFF — derived orientation page

Run the deterministic generator (never hand-write this page):

(`${CLAUDE_PLUGIN_ROOT}` is the plugin directory, set by Claude Code. Without
it, the same scripts sit in the plugin checkout's root `scripts/` directory (a
Codex install keeps the whole checkout), in `scripts/` beside this SKILL.md (a
skills-CLI install), or in your clone of `github.com/arbelh/perdure`.)

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/handoff.py" .
```

With `--check` as the argument, run integrity-check mode instead — it
regenerates the page in memory and compares it to the committed one, with or
without git, so it catches both a stale page and a hand-edited one. Two
fragments are normalized before comparing and are therefore NOT covered: the
sha/timestamp stamp, and the advisory `⚠` staleness annotations (whose commit
counts move on their own). Everything else must match the records exactly:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/handoff.py" . --check
```

Then:

1. **Report the generator's summary line** (N records, M withheld for
   reconciliation).
2. **If records were withheld**, list them and offer to reconcile: those
   records contradict themselves or git, and the page deliberately carries
   none of their claims. Fix them per the convention's *Correcting a record*
   rules (correct headers in place with a dated note; paraphrase retractions,
   never re-quote), then regenerate.
3. **Show the user the page path** (`perdure/HANDOFF.md`) and, on first
   generation in a repo, a one-line explanation: derived, regenerated, never
   edited; every status is a claim as of the stamped commit.

## Why the lint gate is non-negotiable

A naive derived summary strips the context that lets a reader catch a stale
claim, then presents the stale claim with the summary's authority. The generator therefore withholds all state claims from any record
the rot lint flags. Do not paste record content into the page by hand around
that gate; reconcile the record instead.

## What the page does NOT claim

A lint-clean record can still be semantically stale, and external systems
(experiments, deployments, tickets) are never checked. The page says this in
its own header and footer — leave those disclaimers intact.

## When to regenerate

- At workflow close (after the record goes terminal and lint-clean) — the
  close creates the page if the project has none, and the close-gate hook
  regenerates a generator-stamped page on its own (opt-out for both:
  `handoff-regen-at-close: false`)
- Before a handoff, a long pause, or archiving a session
- Whenever `--check` reports the page no longer matches the records
