#!/usr/bin/env python3
"""SessionStart hook, Codex only: give the session perdure's records rule.

Codex followed perdure only where an instructions file it reads carried the
records rule (ADR-012, item 7), and placing that file was the user's job.
This hook removes the step: when a session starts, clears or compacts, it
prints the rule from templates/AGENTS.user.md, which Codex adds to the
session as developer context. A resumed or forked session already carries it
in its history, so those sources are skipped, here and in the hook's matcher.

Codex only. .codex-plugin/plugin.json lists hooks/codex-session-start.json
beside hooks/hooks.json; Claude Code reads hooks/hooks.json alone, so it never
runs this and keeps its own route (/perdure:install writes the rule into
CLAUDE.md).

Silent when an instructions file Codex reads already carries a
perdure-records begin marker: the global file ($CODEX_HOME, else ~/.codex)
and one file in each directory from the git top down to the working
directory, chosen as Codex 0.155.1 chooses them. Globally Codex reads the
first non-empty of AGENTS.override.md and AGENTS.md. In a project directory
it takes the first of the two that exists, so a blank override there hides
that directory's AGENTS.md and Codex reads neither.

Not mirrored: Codex's project_doc_fallback_filenames and
project_doc_max_bytes settings. A marker only in a fallback-named file, or
past the byte limit, is judged differently here than in Codex.

Off switches are Codex's own: leave the hook untrusted in /hooks, or remove
the plugin. Fail-open: any error prints nothing and exits 0, because a
session must never fail to start over this hook.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BEGIN = "<!-- perdure-records:begin -->"
END = "<!-- perdure-records:end -->"
SOURCES = {"startup", "clear", "compact"}


def plugin_root() -> Path:
    for var in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        value = os.environ.get(var)
        if value:
            return Path(value)
    return Path(__file__).resolve().parent.parent


def rule_text(root: Path) -> str:
    """The rule between the markers of templates/AGENTS.user.md."""
    text = (root / "templates" / "AGENTS.user.md").read_text(encoding="utf-8")
    start = text.index(BEGIN) + len(BEGIN)
    return text[start:text.index(END, start)].strip()


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def global_text(codex_home: Path) -> str:
    """Codex's global file: the first non-empty of the override and AGENTS.md."""
    for name in ("AGENTS.override.md", "AGENTS.md"):
        text = read(codex_home / name)
        if text.strip():
            return text
    return ""


def project_text(directory: Path) -> str:
    """A project directory's file: the first of the two that exists, read as is."""
    for name in ("AGENTS.override.md", "AGENTS.md"):
        path = directory / name
        if path.is_file():
            return read(path)
    return ""


def git_top(start: Path) -> Path | None:
    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory
    return None


def instruction_texts(cwd: Path) -> list:
    codex_home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    top = git_top(cwd)
    if top is None:
        directories = [cwd]
    else:
        parts = cwd.relative_to(top).parts
        directories = [top] + [top.joinpath(*parts[:i + 1]) for i in range(len(parts))]
    return [global_text(codex_home)] + [project_text(d) for d in directories]


def main() -> int:
    try:
        raw = sys.stdin.read()
        try:
            event = json.loads(raw) if raw.strip() else {}
        except ValueError:
            event = {}
        if not isinstance(event, dict):
            event = {}
        source = event.get("source")
        if source is not None and source not in SOURCES:
            return 0
        cwd = Path(event.get("cwd") or os.getcwd()).resolve()
        if any(BEGIN in text for text in instruction_texts(cwd)):
            return 0
        sys.stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": rule_text(plugin_root()),
        }}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
