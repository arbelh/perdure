#!/usr/bin/env python3
"""PreCompact hook — auto-archive the current session before compaction.

Gated by the user preference `auto-archive-before-compact` in
~/.claude/perdure-preferences.json (default: false).

Design:
- If the preference is false or missing, this hook exits 0 immediately (no-op).
- If the preference is true, this hook identifies the compacting session from the
  hook event JSON on stdin (session_id / transcript_path — authoritative), falling
  back to the most-recently-modified JSONL in ~/.claude/projects/<cwd-slug>/ only
  when the event carries neither (mtime guessing is unreliable when background
  sessions run concurrently), and invokes scripts/export-session.py to write a
  markdown archive.
- Failures are logged to stderr but the hook always exits 0 — never block /compact.
- Idempotent with the manual archive skill: the same archive filename scheme is used,
  and re-invocation just regenerates the file.

Stdin: Claude Code passes the hook event JSON; used to identify the session.
Environment: uses $PWD for project dir; no other env vars required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PREFS_PATH = Path.home() / ".claude" / "perdure-preferences.json"
PROJECTS_ROOT = Path.home() / ".claude" / "projects"
PREF_KEY = "auto-archive-before-compact"


def log(msg: str) -> None:
    """Write to stderr; hook stdout may be consumed by the host."""
    print(f"[perdure:pre-compact] {msg}", file=sys.stderr)


def preference_enabled() -> bool:
    """Return True only if the preference is explicitly set to true."""
    if not PREFS_PATH.exists():
        return False
    try:
        data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        log(f"could not read preferences ({e}); skipping")
        return False
    prefs = data.get("preferences", {}) or {}
    val = prefs.get(PREF_KEY, False)
    return val is True  # strict: no truthy coercion


def project_slug(cwd: Path) -> str:
    return str(cwd).replace("/", "-")


def find_current_session_jsonl(cwd: Path) -> Path | None:
    """Return the most-recently-modified JSONL for this cwd, or None."""
    project_dir = PROJECTS_ROOT / project_slug(cwd)
    if not project_dir.is_dir():
        return None
    jsonls = sorted(
        project_dir.glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return jsonls[0] if jsonls else None


def locate_export_script() -> Path | None:
    """Find scripts/export-session.py relative to this hook's plugin root."""
    # ${CLAUDE_PLUGIN_ROOT} when invoked by Claude Code; fallback to __file__ parent
    plugin_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin_root:
        candidate = Path(plugin_root) / "scripts" / "export-session.py"
        if candidate.exists():
            return candidate
    # Fallback: walk up from this file's location
    here = Path(__file__).resolve()
    candidate = here.parent.parent / "scripts" / "export-session.py"
    if candidate.exists():
        return candidate
    return None


def session_from_event() -> str | None:
    """Read the hook event JSON from stdin; return the compacting session's id."""
    try:
        if sys.stdin.isatty():
            return None
        raw = sys.stdin.read()
        if not raw.strip():
            return None
        event = json.loads(raw)
    except Exception:
        return None
    sid = event.get("session_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    tp = event.get("transcript_path")
    if isinstance(tp, str) and tp.endswith(".jsonl"):
        return Path(tp).stem
    return None


def main() -> int:
    # The event JSON on stdin identifies WHICH session is compacting —
    # authoritative when present (mtime guessing misfires with concurrent
    # background sessions).
    session_id = session_from_event()

    if not preference_enabled():
        # Silent no-op — the common case when preference is false/missing
        return 0

    cwd = Path.cwd()
    if session_id is None:
        jsonl = find_current_session_jsonl(cwd)
        if jsonl is None:
            log(f"no JSONL found for cwd {cwd}; skipping")
            return 0
        session_id = jsonl.stem  # filename without .jsonl
        log("event JSON carried no session id; fell back to newest JSONL by mtime")

    script = locate_export_script()
    if script is None:
        log("could not locate scripts/export-session.py; skipping")
        return 0

    cmd = [
        sys.executable,
        str(script),
        "--session-id", session_id,
        "--project-dir", str(cwd),
        "--format", "medium",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if result.returncode == 0:
            # Extract archive path from script output for user feedback
            output = result.stdout.strip() or "(no output)"
            log(f"archived before /compact: {output}")
        else:
            log(f"archive exit {result.returncode}; stderr: {result.stderr.strip()[:200]}")
    except subprocess.TimeoutExpired:
        log("archive timed out after 60s; skipping")
    except Exception as e:
        log(f"archive raised {type(e).__name__}: {e}")

    # ALWAYS exit 0 — archival failure must never block /compact
    return 0


if __name__ == "__main__":
    sys.exit(main())
