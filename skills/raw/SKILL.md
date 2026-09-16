---
name: raw
description: Sweep or verify the session index at perdure/raw/INDEX.jsonl
  — one committed line per session recording identifiers, timestamps, counts and
  content digests, with no transcript text. Use to establish the population of
  sessions behind a project's records, to check the index still matches the
  transcript store, or when asked "how many sessions produced these records?".
---

# The session index

Reads Claude Code's session store under `~/.claude/projects/`.

`perdure/raw/INDEX.jsonl` is the *population*: one line per session that ran in
this project. It is the only artifact here derived from what actually happened
rather than from what someone chose to write down.

Run the sweep (safe, idempotent, additive):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/raw-index.py" --root .
```

Without `${CLAUDE_PLUGIN_ROOT}`, the script sits in the plugin checkout's root
`scripts/` directory (Codex keeps the whole checkout), or in `scripts/`
beside this SKILL.md (skills CLI).

Other modes:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/raw-index.py" --root . --summary   # print the population, write nothing
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/raw-index.py" --root . --verify    # re-derive and compare; exit 1 on mismatch
```

Then:

1. **Report the population**, not just the file count — sessions present,
   sessions pruned, prompts, subagent transcripts.
2. **If any session is marked `pruned`**, say so plainly. Its transcript is gone
   from the local store; the entry and its digest remain, so a record can still
   cite it, but the payload cannot be re-read. An honest gap is a record.
3. **Never edit this file by hand.** It is swept, and `--verify` will fail on a
   hand edit.

## What it deliberately does not contain

No transcript text, no file paths, no prose — only ids, counts, hashes,
timestamps and low-cardinality labels (branch, tool version, entrypoint, model).
That is why it is committed while the transcripts it points at are not: the
safety is a property of the schema, not of a scan that might miss something. The
sweep refuses to write an entry that would violate it.

## What it is for

The 2026-08-31 lifecycle dry run produced four workflow records for five units of
work, and nothing in the system could tell — perdure knew only about records
someone chose to write. This index is what makes that kind of gap countable: it
gives the denominator. It does **not** decide whether a session should have
produced a record; that judgement belongs to whatever reads this file.
