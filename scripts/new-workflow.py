#!/usr/bin/env python3
"""
new-workflow.py — deterministic, zero-turn workflow-file creation.

Creates perdure/workflows/<YYYY-MM-DD>-<slug>.md from the canonical schema
(docs/RECORDS-CONVENTION.md) without any model involvement. Intended for
autonomous flows (claude -p, cron, CI pre-steps) where a workflow file should
exist BEFORE the model starts, and for anyone who prefers a deterministic
scaffold over asking the model to write the file.

This is the surviving mechanism of the retired UserPromptSubmit hook: the
hook died because its *triggers* (prompt phrase-matching, slug derivation
from prose) were unreliable — the deterministic creation itself was sound.
Now it runs only when explicitly invoked, with an explicit slug.

Usage:
    python3 new-workflow.py <slug> [--goal "text"] [--root <project-dir>]

Exit codes: 0 created (prints the path), 1 usage error, 2 already exists.
"""

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

TEMPLATE = """---
workflow: {slug}
status: in-progress
started: {now}
updated: {now}
---

# Goal

{goal}

# Plan

- [ ] (fill after exploration / planning)

# Findings

# Decisions

# Files modified

# Open questions

# Next step

(fill — the resume point)

# Review

(empty until the review gate runs; see docs/RECORDS-CONVENTION.md)

# Outcome
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Create a workflow state file.")
    ap.add_argument("slug", help="kebab-case task slug, e.g. add-jwt-refresh")
    ap.add_argument("--goal", default="(fill in)", help="1-3 sentence goal")
    ap.add_argument("--root", default=".", help="project root (default: cwd)")
    args = ap.parse_args()

    slug = args.slug.strip().lower()
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug) or len(slug) > 60:
        print(f"new-workflow.py: invalid slug '{args.slug}' "
              "(kebab-case, alphanumeric, <=60 chars)", file=sys.stderr)
        return 1

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    today = datetime.now().strftime("%Y-%m-%d")
    path = Path(args.root) / "perdure" / "workflows" / f"{today}-{slug}.md"

    if path.exists():
        print(f"new-workflow.py: already exists: {path}", file=sys.stderr)
        return 2

    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8 + atomic: on a non-UTF-8 locale the default encoding crashed on
    # the em dash in TEMPLATE and left a 0-byte record, which the
    # refuse-to-overwrite guard then treated as an existing record — wedging
    # that slug forever (pre-publish critic, 2026-08-31)
    body = TEMPLATE.format(slug=slug, now=now, goal=args.goal.strip())
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
