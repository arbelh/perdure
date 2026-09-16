---
name: coverage
description: Check the records against the population of sessions — how much of
  the work that ran is linked to a written record. Use when asked "how many
  sessions produced records?", "is anything undocumented?", or before trusting a
  project's records as a complete account. Reports; never accuses.
---

# Coverage — records checked against what actually ran

Reads the session index that `raw` builds.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage.py" --root .
```

Without `${CLAUDE_PLUGIN_ROOT}`, the script sits in the plugin checkout's root
`scripts/` directory (Codex keeps the whole checkout), or in `scripts/`
beside this SKILL.md (skills CLI).

Requires the session index (`/perdure:raw` first). Three buckets, in
descending strength of evidence:

- **CITED** — a record's *frontmatter* names the session id. Checkable.
  Deliberately not "a UUID appears somewhere in the record": that counted a
  quoted log line, and a sentence *declining* to record a session, as evidence.
- **WEAK** — a body mention, or a record whose window intersects the session's.
  Correlation, not evidence — say so when you report it.
- **UNEXPLAINED** — neither.
- **UNEVALUABLE** — no usable timestamps, so no check was possible. Report this
  separately: "I could not check" is not "I found nothing".

## How to report it

1. **Never call an unexplained session a violation.** The convention says not to
   open records for typo fixes, obvious edits, or interactive back-and-forth, so
   most sessions in a healthy project legitimately have no record. This tool
   cannot know which; that judgement is the reader's.
2. **Say which numbers are checkable.** CITED is evidence. OVERLAPPING is a
   hint, and must be described as one.
3. **Read records-without-sessions carefully.** The population is keyed by
   working directory, but records describe a *repository*, and one session
   routinely edits a repo other than its cwd. Work done from elsewhere is
   invisible here. Coverage is a per-directory measure, not a per-repo one — say
   so rather than implying records are missing.
4. **To make coverage checkable**, add the session id to a record's frontmatter:
   `sessions: <id>`. Until records cite sessions, only the heuristic is
   available and the honest answer is "not established".

`--strict --min-prompts N` exits 1 on unexplained sessions with at least N
prompts, for CI. The bar is explicit on purpose: there is no defensible
universal threshold for "this should have been recorded".
