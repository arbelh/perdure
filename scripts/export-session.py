#!/usr/bin/env python3
"""Export Claude Code session JSONL(s) to human-readable markdown archives.

Reads the raw transcript Claude Code stores at
~/.claude/projects/<cwd-slug>/<session-id>.jsonl and emits a portable markdown
file preserving the dialogue, with tool calls summarized and operational noise
stripped.

Modes:
    Single session:  --session-id <uuid> [--output <path>]
    Sweep project:   --sweep [--project-dir <path>] [--force]

Formats:
    brief    — prose only, tool calls elided entirely
    medium   — prose + one-line tool summaries (default)
    verbose  — prose + tool summaries + truncated outputs

Output path default: <project-root>/perdure/archives/session-<YYYY-MM-DD>-<slug>-<short-uuid>.md
"""

from __future__ import annotations

import re

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECTS_ROOT = Path.home() / ".claude" / "projects"
TOOL_OUTPUT_MAX_LINES = 3
TOOL_OUTPUT_MAX_CHARS = 240
COMMAND_MAX_CHARS = 120


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def project_slug(cwd: str | Path) -> str:
    """Convert a cwd to Claude Code's project directory slug.

    /Users/you/Dev/my_project.v2 -> -Users-you-Dev-my-project-v2

    Every character outside [A-Za-z0-9] becomes "-", not only "/": measured
    over 72 transcript directories (2026-09-15), `_` and `.` included.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def projects_dir_for(cwd: str | Path) -> Path:
    return PROJECTS_ROOT / project_slug(cwd)


def archive_filename(session_id: str, slug: str, first_date: str) -> str:
    short = session_id[:8]
    return f"session-{first_date}-{slug}-{short}.md"


# ---------------------------------------------------------------------------
# JSONL parsing
# ---------------------------------------------------------------------------

def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                print(f"warning: JSONL parse error at line {line_no}: {e}",
                      file=sys.stderr)


def extract_text(content: Any) -> str:
    """Extract readable text from a message.content field.

    Content may be a str, a list of content blocks, or None.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def extract_tool_uses(content: Any) -> list[dict[str, Any]]:
    """Return tool_use blocks from an assistant message.content."""
    if not isinstance(content, list):
        return []
    return [b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"]


def strip_system_reminders(text: str) -> str:
    """Remove <system-reminder>...</system-reminder> blocks from user text."""
    if not text or "<system-reminder>" not in text:
        return text
    out = []
    i = 0
    while i < len(text):
        start = text.find("<system-reminder>", i)
        if start == -1:
            out.append(text[i:])
            break
        out.append(text[i:start])
        end = text.find("</system-reminder>", start)
        if end == -1:
            break
        i = end + len("</system-reminder>")
    return "".join(out).strip()


# ---------------------------------------------------------------------------
# Tool summarization
# ---------------------------------------------------------------------------

def truncate(s: str, n: int) -> str:
    s = s.strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def summarize_tool_use(tu: dict[str, Any], fmt: str) -> str:
    """One-line markdown summary of a tool_use block."""
    name = tu.get("name", "?")
    inp = tu.get("input", {}) or {}

    def fmt_path(p: str) -> str:
        # Shorten home dir for readability
        home = str(Path.home())
        if p.startswith(home):
            p = "~" + p[len(home):]
        return f"`{p}`"

    if name == "Bash":
        cmd = truncate(inp.get("command", ""), COMMAND_MAX_CHARS)
        return f"*Ran:* `{cmd}`"
    if name == "Read":
        return f"*Read:* {fmt_path(inp.get('file_path', '?'))}"
    if name == "Write":
        path = fmt_path(inp.get("file_path", "?"))
        content = inp.get("content", "")
        lines = len(content.splitlines()) if content else 0
        return f"*Wrote:* {path} ({lines} lines)"
    if name == "Edit":
        return f"*Edited:* {fmt_path(inp.get('file_path', '?'))}"
    if name == "Grep":
        return f"*Searched:* `{truncate(inp.get('pattern', ''), 80)}`"
    if name == "Glob":
        return f"*Found files:* `{inp.get('pattern', '?')}`"
    if name == "Task":
        subtype = inp.get("subagent_type", "")
        desc = inp.get("description", "")
        return f"*Delegated to {subtype or 'agent'}:* {desc}"
    if name == "Skill":
        return f"*Invoked skill:* `/{inp.get('skill', '?')}`"
    if name == "WebFetch":
        return f"*Fetched:* {inp.get('url', '?')}"
    if name == "WebSearch":
        return f"*Web search:* \"{truncate(inp.get('query', ''), 80)}\""
    if name == "TodoWrite":
        todos = inp.get("todos", [])
        return f"*Updated todos* ({len(todos)} items)"
    if name == "NotebookEdit":
        return f"*Edited notebook:* {fmt_path(inp.get('notebook_path', '?'))}"
    if name == "ToolSearch":
        return f"*Tool search:* `{truncate(inp.get('query', ''), 80)}`"
    # MCP or other
    return f"*Tool:* `{name}`"


def summarize_tool_result(content: Any, fmt: str) -> str | None:
    """Short markdown of a tool result, if worth showing (verbose mode only)."""
    if fmt != "verbose":
        return None
    text = extract_text(content)
    if not text.strip():
        return None
    lines = text.splitlines()[:TOOL_OUTPUT_MAX_LINES]
    snippet = "\n".join(lines)
    snippet = truncate(snippet, TOOL_OUTPUT_MAX_CHARS)
    return f"> {snippet}"


# ---------------------------------------------------------------------------
# Session metadata
# ---------------------------------------------------------------------------

def collect_metadata(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Scan messages once to build header metadata."""
    session_id = ""
    cwd = ""
    git_branch = ""
    slug = "unknown"
    first_ts = ""
    last_ts = ""
    user_count = 0
    assistant_count = 0
    tool_counter: Counter[str] = Counter()
    compactions = 0
    has_in_progress_marker = False

    for msg in messages:
        t = msg.get("type")
        ts = msg.get("timestamp", "")
        if ts:
            if not first_ts or ts < first_ts:
                first_ts = ts
            if ts > last_ts:
                last_ts = ts
        session_id = msg.get("sessionId", session_id) or session_id
        cwd = msg.get("cwd", cwd) or cwd
        git_branch = msg.get("gitBranch", git_branch) or git_branch
        slug = msg.get("slug", slug) or slug

        if msg.get("isCompactSummary"):
            compactions += 1

        if t == "user":
            inner = msg.get("message", {}) or {}
            content = inner.get("content", "")
            text = extract_text(content)
            # Count as "user" only if there's real text (skip tool-result-only)
            if isinstance(content, list) and not any(
                isinstance(b, dict) and b.get("type") == "text"
                for b in content
            ):
                # pure tool_result message
                pass
            elif strip_system_reminders(text).strip():
                user_count += 1
        elif t == "assistant":
            assistant_count += 1
            inner = msg.get("message", {}) or {}
            for tu in extract_tool_uses(inner.get("content", [])):
                tool_counter[tu.get("name", "?")] += 1

    return {
        "session_id": session_id,
        "cwd": cwd,
        "git_branch": git_branch,
        # 2.1.270 transcripts carry no slug field (measured 2026-09-15); name the
        # archive after the project directory instead of "unknown"
        "slug": slug if slug != "unknown" else (re.sub(r"[^A-Za-z0-9]", "-", Path(cwd).name) if cwd else "unknown"),
        "first_ts": first_ts,
        "last_ts": last_ts,
        "user_count": user_count,
        "assistant_count": assistant_count,
        "tool_counter": tool_counter,
        "compactions": compactions,
    }


def format_ts(ts: str) -> str:
    """Format ISO timestamp for display. Returns '' if unparseable."""
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return ts


def date_only(ts: str) -> str:
    if not ts:
        return "unknown"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        return "unknown"


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def render_header(meta: dict[str, Any], jsonl_path: Path, fmt: str) -> str:
    tool_total = sum(meta["tool_counter"].values())
    tool_breakdown = ", ".join(
        f"{name}: {n}"
        for name, n in meta["tool_counter"].most_common()
    ) or "none"
    jsonl_size = jsonl_path.stat().st_size if jsonl_path.exists() else 0

    def human_size(n: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if n < 1024:
                return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
            n /= 1024
        return f"{n:.1f} TB"

    return (
        f"# Session Archive: {meta['slug']}\n"
        f"\n"
        f"**Session ID:** `{meta['session_id']}`  \n"
        f"**Date range:** {format_ts(meta['first_ts'])} → {format_ts(meta['last_ts'])}  \n"
        f"**Working directory:** `{meta['cwd']}`  \n"
        f"**Git branch:** `{meta['git_branch'] or 'unknown'}`  \n"
        f"**Messages:** {meta['user_count']} user / {meta['assistant_count']} assistant  \n"
        f"**Tool calls:** {tool_total} ({tool_breakdown})  \n"
        f"**Compactions:** {meta['compactions']}  \n"
        f"**Format:** {fmt}  \n"
        f"**Source:** `{jsonl_path}` ({human_size(jsonl_size)})  \n"
        f"**Exported:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}\n"
        f"\n"
        f"---\n"
    )


def render_user_message(msg: dict[str, Any]) -> str | None:
    inner = msg.get("message", {}) or {}
    content = inner.get("content", "")

    # Skip pure tool-result messages
    if isinstance(content, list):
        has_text = any(
            isinstance(b, dict) and b.get("type") == "text"
            for b in content
        )
        if not has_text:
            return None

    text = extract_text(content)

    # Compaction markers get special treatment
    if msg.get("isCompactSummary"):
        ts = format_ts(msg.get("timestamp", ""))
        stripped = strip_system_reminders(text).strip()
        return (
            f"\n---\n"
            f"\n### ── Context compacted at {ts} ──\n"
            f"\n"
            f"<details>\n<summary>Compaction summary (click to expand)</summary>\n\n"
            f"{stripped}\n\n"
            f"</details>\n"
            f"\n---\n"
        )

    cleaned = strip_system_reminders(text).strip()
    if not cleaned:
        return None

    ts = format_ts(msg.get("timestamp", ""))
    ts_suffix = f" ({ts})" if ts else ""
    # Indent user text as blockquote for visual distinction
    quoted = "\n".join(f"> {line}" if line else ">" for line in cleaned.splitlines())
    return f"\n**User{ts_suffix}:**\n\n{quoted}\n"


def render_assistant_message(msg: dict[str, Any], fmt: str) -> str | None:
    inner = msg.get("message", {}) or {}
    content = inner.get("content", [])
    text = extract_text(content).strip()
    tool_uses = extract_tool_uses(content)

    if not text and not tool_uses:
        return None

    parts = ["\n**Assistant:**\n"]
    if text:
        parts.append(f"\n{text}\n")

    if tool_uses and fmt != "brief":
        tool_lines = [summarize_tool_use(tu, fmt) for tu in tool_uses]
        parts.append("\n" + "\n".join(tool_lines) + "\n")

    return "".join(parts)


def render_messages(messages: list[dict[str, Any]], fmt: str) -> str:
    out: list[str] = []
    for msg in messages:
        t = msg.get("type")
        if t == "user":
            rendered = render_user_message(msg)
            if rendered:
                out.append(rendered)
        elif t == "assistant":
            rendered = render_assistant_message(msg, fmt)
            if rendered:
                out.append(rendered)
        # Skip queue-operation, system, etc.
    return "".join(out)


def render_footer(meta: dict[str, Any]) -> str:
    return (
        "\n---\n"
        "\n*Archive generated by `perdure` "
        f"v1.5 (export-session.py).*  \n"
        f"*Source of truth: `{meta['cwd']}/.claude/projects/` JSONL transcript.*\n"
    )


# ---------------------------------------------------------------------------
# Main operations
# ---------------------------------------------------------------------------

def export_session(
    jsonl_path: Path,
    output_path: Path | None,
    fmt: str,
    project_dir: Path,
) -> Path:
    """Export a single JSONL to markdown. Returns the output path."""
    messages = list(iter_jsonl(jsonl_path))
    if not messages:
        raise RuntimeError(f"No messages in {jsonl_path}")

    meta = collect_metadata(messages)
    if not output_path:
        archive_dir = project_dir / "perdure" / "archives"
        _gi = archive_dir.parent / ".gitignore"
        if not _gi.exists():
            archive_dir.parent.mkdir(parents=True, exist_ok=True)
            _body = ("# perdure records root (ADR-010). Committed: workflows/, decisions/.\n"
                     "# Local by default (opt in explicitly before committing):\narchives/\nruns/\n")
            try:
                import json as _json
                _pp = Path.home() / ".claude" / "perdure-preferences.json"
                if _pp.exists():
                    if _json.loads(_pp.read_text(encoding="utf-8")).get("preferences", {}).get("commit-archives") is True:
                        _body = ("# perdure records root (ADR-010). All records committed (commit-archives: true).\n"
                                 "# Scratch only:\nruns/.last-spawn.json\n")
            except Exception:
                pass
            try:
                _gi.write_text(_body, encoding="utf-8")
            except OSError:
                pass
        archive_dir.mkdir(parents=True, exist_ok=True)
        fname = archive_filename(
            meta["session_id"],
            meta["slug"],
            date_only(meta["first_ts"]),
        )
        output_path = archive_dir / fname

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = render_header(meta, jsonl_path, fmt)
    body = render_messages(messages, fmt)
    footer = render_footer(meta)
    output_path.write_text(header + body + footer, encoding="utf-8")
    return output_path


def find_jsonl_for_session(session_id: str, project_dir: Path) -> Path:
    """Locate the JSONL file for a given session ID, searching project dir first."""
    slug = project_slug(project_dir)
    candidate = PROJECTS_ROOT / slug / f"{session_id}.jsonl"
    if candidate.exists():
        return candidate
    # Fall back: scan all project dirs
    for p in PROJECTS_ROOT.glob(f"*/{session_id}.jsonl"):
        return p
    raise FileNotFoundError(
        f"No JSONL found for session {session_id} under {PROJECTS_ROOT}"
    )


def existing_archives(project_dir: Path) -> set[str]:
    """Return the short-uuid prefixes of already-archived sessions.

    Returns SHORT IDS uniformly — the caller tests ``session_id[:8]``
    membership, so returning anything else silently disables dedup (a measured
    failure mode, 2026-08: an earlier filename-returning version made every
    sweep re-archive every session). Records live in ``perdure/`` only.
    """
    archives_dir = project_dir / "perdure" / "archives"
    ids: set[str] = set()
    if archives_dir.exists():
        for f in archives_dir.glob("session-*.md"):
            # filename: session-<date>-<slug>-<shortid>.md
            parts = f.stem.rsplit("-", 1)
            if len(parts) == 2 and len(parts[1]) == 8:
                ids.add(parts[1])
    return ids


def sweep_project(project_dir: Path, fmt: str, force: bool) -> list[Path]:
    """Archive every JSONL for this project that isn't already archived."""
    jsonl_dir = projects_dir_for(project_dir)
    if not jsonl_dir.exists():
        raise FileNotFoundError(f"No project dir found: {jsonl_dir}")

    archived_short_ids = set() if force else existing_archives(project_dir)
    to_archive = []
    for jsonl in sorted(jsonl_dir.glob("*.jsonl")):
        session_id = jsonl.stem
        if session_id[:8] in archived_short_ids:
            continue
        to_archive.append(jsonl)

    written: list[Path] = []
    for jsonl in to_archive:
        try:
            path = export_session(jsonl, None, fmt, project_dir)
            written.append(path)
            print(f"  archived: {path.name}")
        except Exception as e:
            print(f"  skipped {jsonl.name}: {e}", file=sys.stderr)
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export Claude Code session JSONLs to markdown archives.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--session-id", help="UUID of session to archive")
    parser.add_argument("--output", type=Path,
                        help="Output file path (default: archives/<auto>.md)")
    parser.add_argument("--format", choices=("brief", "medium", "verbose"),
                        default="medium", help="Output verbosity")
    parser.add_argument("--project-dir", type=Path, default=Path.cwd(),
                        help="Project root (default: cwd)")
    parser.add_argument("--sweep", action="store_true",
                        help="Archive every JSONL for project that lacks an archive")
    parser.add_argument("--force", action="store_true",
                        help="Re-archive even if archive exists (sweep mode)")
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()

    if args.sweep:
        written = sweep_project(project_dir, args.format, args.force)
        print(f"\nSweep complete: {len(written)} archive(s) written to "
              f"{project_dir / 'perdure' / 'archives'}")
        return 0

    if not args.session_id:
        parser.error("--session-id required (or use --sweep)")

    jsonl = find_jsonl_for_session(args.session_id, project_dir)
    out = export_session(jsonl, args.output, args.format, project_dir)
    print(f"Archive written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
