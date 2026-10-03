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
- The archive lands in the PROJECT ROOT of the event's `cwd` (4.3.0), not in the
  hook process's own folder: the nearest folder at or above cwd holding
  perdure/, never crossing a folder that holds .git; else the repo top; else cwd
  itself. A session working in a subfolder therefore leaves no stray perdure/
  there. When that root would be the home folder and home holds no perdure/,
  nothing is archived and a log line says so. The rule, and the transcript-
  folder slug the fallback uses, live in scripts/_paths.py, shared with
  export-session.py and raw-index.py (the hook's own copy of the slug had
  replaced "/" only, so the fallback missed every path holding "_" or ".").
- Failures are logged to stderr but the hook always exits 0 — never block /compact.
- Idempotent with the manual archive skill: the same archive filename scheme is used,
  and re-invocation rewrites the session's existing archive (export-session.py
  keeps one file per session id).

Stdin: Claude Code passes the hook event JSON; used to identify the session and
its working folder (`cwd`; the hook process's own folder only when absent).
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


def load_paths():
    """Import scripts/_paths.py (CLAUDE_PLUGIN_ROOT first, then this file's
    plugin root) — the ONE definition of the transcript-folder slug and the
    archive root. None when unlocatable; the caller skips (fail open)."""
    import importlib.util
    for base in (os.environ.get("CLAUDE_PLUGIN_ROOT"),
                 Path(__file__).resolve().parent.parent):
        if not base:
            continue
        cand = Path(base) / "scripts" / "_paths.py"
        if cand.exists():
            spec = importlib.util.spec_from_file_location("_paths", cand)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
    return None


def project_slug(cwd: Path) -> str:
    """Claude Code's transcript-folder name for a working folder: the scripts'
    rule (every character outside [A-Za-z0-9] becomes "-"), from _paths.py."""
    pa = load_paths()
    if pa is None:
        raise RuntimeError("scripts/_paths.py not found")
    return pa.project_slug(cwd)


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


def read_event() -> dict:
    """The hook event JSON from stdin, or {} when absent or unparseable."""
    try:
        if sys.stdin.isatty():
            return {}
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        event = json.loads(raw)
    except Exception:
        return {}
    return event if isinstance(event, dict) else {}


def event_cwd(event: dict) -> Path:
    """The session's working folder from the event; this process's own folder
    only when the event carries no usable absolute one."""
    cwd = event.get("cwd")
    if isinstance(cwd, str) and cwd.strip() and os.path.isabs(cwd):
        p = Path(os.path.normpath(cwd))
        if p.is_dir():
            return p
    return Path.cwd()


def session_from_event(event: dict) -> str | None:
    """Return the compacting session's id from the hook event."""
    sid = event.get("session_id")
    if isinstance(sid, str) and sid.strip():
        return sid.strip()
    tp = event.get("transcript_path")
    if isinstance(tp, str) and tp.endswith(".jsonl"):
        return Path(tp).stem
    return None


def _run() -> int:
    # The event JSON on stdin identifies WHICH session is compacting —
    # authoritative when present (mtime guessing misfires with concurrent
    # background sessions).
    event = read_event()
    session_id = session_from_event(event)

    if not preference_enabled():
        # Silent no-op — the common case when preference is false/missing
        return 0

    pa = load_paths()
    if pa is None:
        log("could not locate scripts/_paths.py; skipping")
        return 0
    cwd = event_cwd(event)
    root = pa.archive_root(cwd)
    if root is None:
        log(f"the project root for {cwd} would be the home folder, which holds no "
            "perdure/; not archiving there (open the session in a project folder)")
        return 0
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
        "--project-dir", str(root),
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


def main() -> int:
    # The exit-0 guarantee lives HERE: no input, preference file, module or
    # export failure may surface as a hook error that blocks /compact.
    try:
        return _run()
    except Exception as e:
        log(f"unexpected {type(e).__name__}: {e}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
