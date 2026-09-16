---
name: archive
description: Export Claude Code session JSONLs to portable, human-readable markdown
  archives. Preserves raw dialogue, summarizes tool calls, strips operational noise.
  Archive the current session, a specific session id, or pass "all" to sweep every
  un-archived session in the project. Use at the end of a significant session,
  before /compact, before upgrading Claude Code, or when returning to a project
  after a gap.
argument-hint: "[session-id | current | all]"
---

# Archive Claude Code Sessions

Exports Claude Code's session transcripts from `~/.claude/projects/`.

You are exporting session JSONL transcripts to self-contained markdown files under
`perdure/archives/`. Archives survive JSONL pruning, work without Claude Code, and
are readable by anyone with a text editor.

## Arguments

- `$1` — session UUID, `current` (or empty: auto-detect the current session), or
  **`all`** — sweep mode: archive every session in this project that doesn't have
  an archive yet.
- `--format brief|medium|verbose` — verbosity (default: `medium`)
- `--output <path>` — override the default archive path (single-session only)
- `--force` — re-archive even if the archive file already exists

## Steps

### 1. Locate the export script

Use `${CLAUDE_PLUGIN_ROOT}/scripts/export-session.py` if the env var is set; else
the plugin checkout's root `scripts/export-session.py` (Codex keeps the whole
checkout) or `scripts/export-session.py` beside this SKILL.md (skills CLI); else:

```bash
# Claude Code's install manifest names the ACTIVE install. A bare
# `find ... | head -1` returns whichever path the filesystem yields first, and
# the plugin cache keeps every version ever installed — that can be an old one.
python3 -c "import json,pathlib;d=json.loads((pathlib.Path.home()/'.claude/plugins/installed_plugins.json').read_text());p=d.get('plugins',d);print(next(v[0]['installPath'] for k,v in p.items() if k.split('@')[0]=='perdure'))"
```

If not found, STOP and tell the user the plugin is not properly installed.

### 2a. Single session (default)

Determine the session id:
- `$1` is a UUID (36 chars with dashes) → use it.
- Empty or `current` → most recently modified JSONL in
  `~/.claude/projects/<cwd-slug>/` (cwd-slug = `$PWD` with `/` → `-`); its filename
  stem is the id. If its mtime is within the last 60s, note the session is still
  active and the archive reflects current state.

Run:

```bash
python3 "$SCRIPT_PATH" --session-id "$SESSION_ID" --project-dir "$PWD" --format "${FORMAT:-medium}"
```

Add `--output "$OUTPUT"` / `--force` when the user passed them. If the archive
already exists without `--force`, the script stops — relay its message (re-run with
`--force` to regenerate, or `--output` for a different path).

### 2b. Sweep mode (`$1` = `all`)

```bash
python3 "$SCRIPT_PATH" --sweep --project-dir "$PWD" --format "${FORMAT:-medium}" ${FORCE:+--force}
```

The script enumerates the project's JSONLs, skips ones already archived (matched by
the 8-char UUID suffix), archives the rest, and prints one line each. Good moments
to sweep: returning to a project after a gap, before upgrading Claude Code, before
cold-storing a project. Not needed right after archiving the current session.

### 3. Report

```
✅ Archived
Path(s):  perdure/archives/session-<date>-<slug>-<short-id>.md  (one line per file in sweep mode)
Format:   <brief|medium|verbose>
Source:   ~/.claude/projects/<slug>/*.jsonl
```

## Commit policy

Archives are **gitignored by default** (the exporter scaffolds the scoped
`.gitignore` per the `commit-archives` preference) — transcripts can contain pasted
secrets and personal content, so committing them is an explicit opt-in with a
redaction pass. See `docs/RECORDS-CONVENTION.md` (also at
`references/RECORDS-CONVENTION.md` beside this SKILL.md in a skills-CLI install). Workflow files and ADRs are the
committed-by-default layer; archives are the privacy layer.

## Reference

| Format | Contents |
|--------|----------|
| `brief` | Dialogue prose only; tool calls elided |
| `medium` *(default)* | Dialogue + one-line tool summaries |
| `verbose` | Dialogue + tool summaries + truncated outputs |

Naming: `perdure/archives/session-<YYYY-MM-DD>-<slug>-<short-uuid>.md` (first
message date, session slug, first 8 UUID chars for collision safety).

Semantics: idempotent within a session (re-run regenerates from the larger JSONL);
per-session filenames never collide; the archive stands alone once written; the
JSONL remains the source of truth while it exists. Corrupt JSONLs are skipped with
a stderr log, never fatal.

The `auto-archive-before-compact` preference runs this automatically via the
PreCompact hook.
