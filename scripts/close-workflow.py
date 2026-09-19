#!/usr/bin/env python3
"""close-workflow.py — deterministic, zero-turn close for a workflow record.

Why this exists: in headless mode (`claude -p`) skill bodies do not load, so a
model closing a record compensates from convention memory — and measured
compensation drift includes out-of-vocabulary statuses ("closed") that silently
escape the close-gate hook, malformed verdict blocks, and hand-written HANDOFF
pages. This script is the close-side mirror of new-workflow.py: the mechanical
parts of a close, done deterministically, so autonomous flows never improvise
them.

What it does, in order (each step gates the next):
  1. resolves the record (path or slug)
  2. refuses if the frontmatter has no conforming `status:` (freeform records
     close manually); an ALREADY-TERMINAL record is verified instead (lint,
     `# Review` present, page created or refreshed) and left byte-identical
     unless --skip-review adds the recorded skip it lacked, so a record closed
     by hand can be completed after the fact (4.1.0)
  3. refuses if `# Review` is empty — append a verdict or a recorded skip
     first (the gate checks the record, not the producer); --skip-review
     "<reason>" writes the convention's recorded skip and proceeds (4.1.0)
  4. runs the rot lint; refuses on findings unless --force-lint
  5. sets `status: completed` (or `abandoned` with --abandon), bumps
     `updated:`, and appends --outcome text under `# Outcome` when given
  6. regenerates perdure/HANDOFF.md via the sibling handoff.py, creating it
     at the first close when the project has none (never hand-write that
     page; opt out with preferences.handoff-regen-at-close = false)

Exit codes: 0 closed or verified · 1 resolution/freeform · 2 usage (argparse)
or an empty --abandon/--skip-review reason · 3 lint findings (--force-lint
overrides; record why; on an already-terminal record an empty `# Review` is
such a finding) · 4 review gate refused (`# Review` empty on an open record,
absent on a terminal one).

A record passed as a direct path may live outside perdure/workflows — an
explicit operator choice; the frontmatter, review, and lint gates still apply.
Slug resolution only searches perdure/workflows/.

Usage:
  close-workflow.py <record.md | slug> [--abandon "<reason>"] [--skip-review "<reason>"]
                    [--outcome "<text>"] [--force-lint] [--root DIR]
"""
from __future__ import annotations

import argparse
import json
import datetime
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

_sv_spec = importlib.util.spec_from_file_location(
    "_status_vocab", Path(__file__).resolve().parent / "_status_vocab.py")
sv = importlib.util.module_from_spec(_sv_spec)
_sv_spec.loader.exec_module(sv)


def load_lint(scripts_dir: Path):
    spec = importlib.util.spec_from_file_location("rot_lint", scripts_dir / "rot-lint.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.lint


def resolve(target: str, root: Path) -> Path | None:
    p = Path(target)
    if p.is_file():
        return p
    hits = sorted((root / "perdure" / "workflows").glob(f"*{target}*.md"))
    hits = [h for h in hits if h.name != "INDEX.md" and h.is_file()]
    if len(hits) == 1:
        return hits[0]
    print(f"cannot resolve '{target}': {len(hits)} match(es)"
          + (f" — {', '.join(h.name for h in hits)}" if hits else ""), file=sys.stderr)
    return None


def heading_index(lines: list[str], heading: str) -> int | None:
    """Index of the first H1-H3 heading named `heading` (the same shape section_body reads), else None."""
    pat = re.compile(rf"^#{{1,3}}\s+{re.escape(heading)}\b")
    return next((i for i, l in enumerate(lines) if pat.match(l)), None)


def section_body(lines: list[str], heading: str) -> list[str]:
    # H1-H3, matching the lint's review-gate: records authored outside the
    # scaffold legitimately nest sections one level down. Only a heading at
    # the matched heading's own level or shallower ENDS the section — a
    # "## Verdict" under "# Review" is content, not a boundary (a false
    # exit-4 refusal otherwise, review 2026-08-30).
    out, active, lvl = [], False, 0
    for line in lines:
        m = re.match(rf"(#{{1,3}})\s+{re.escape(heading)}\b", line)
        if m and not active:
            active, lvl = True, len(m.group(1))
            continue
        if active and re.match(rf"#{{1,{lvl}}}\s+\S", line):
            break
        if active:
            out.append(line)
    return out


PREFS_PATH = Path.home() / ".claude" / "perdure-preferences.json"


def handoff_regen_enabled() -> bool:
    """Same rule as the close-gate hook: enabled unless the preference is
    explicitly false; an unreadable or wrong-typed prefs file never disables."""
    if not PREFS_PATH.exists():
        return True
    try:
        data = json.loads(PREFS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    prefs = data.get("preferences") if isinstance(data, dict) else None
    if not isinstance(prefs, dict):
        return True
    return prefs.get("handoff-regen-at-close", True) is not False


def heading_level(lines: list[str]) -> str:
    """The record's own section-heading level ("#", "##" or "###"), H1 when it has none."""
    for l in lines:
        m = re.match(r"^(#{1,3})\s+\S", l)
        if m:
            return m.group(1)
    return "#"


def insert_section(lines: list[str], heading: str, body: list[str]) -> list[str]:
    """Create `<level> <heading>` with `body` before the Outcome section, or at EOF, with a blank line before it."""
    out_ln = heading_index(lines, "Outcome") if heading != "Outcome" else None
    at = out_ln if out_ln is not None else len(lines)
    pad = [""] if at > 0 and lines[at - 1].strip() else []
    return lines[:at] + pad + [f"{heading_level(lines)} {heading}", ""] + body + [""] + lines[at:]


def insert_skip(lines: list[str], skip_line: str) -> list[str]:
    """Put the recorded skip inside `# Review` (any H1-H3 shape); create the section when absent."""
    rev_ln = heading_index(lines, "Review")
    if rev_ln is not None:
        return lines[:rev_ln + 1] + ["", skip_line] + lines[rev_ln + 1:]
    return insert_section(lines, "Review", [skip_line])


def refresh_page(root: Path, scripts_dir: Path) -> str:
    """Create the HANDOFF page at the first close, regenerate it after; honour the preference.

    Measured 2026-09-15: headless, the skill's "offer to generate it" has nobody to
    ask, so a fresh project never got the page. Never hand-write it; the hook keeps
    its never-creates rail. Opt-out: handoff-regen-at-close.
    """
    page = root / "perdure" / "HANDOFF.md"
    if not handoff_regen_enabled():
        return "HANDOFF untouched (handoff-regen-at-close is off)"
    verb = "regenerated" if page.exists() else "created"
    try:
        r = subprocess.run([sys.executable, str(scripts_dir / "handoff.py"), str(root)],
                           capture_output=True, text=True, timeout=120)
        return (f"HANDOFF {verb}" if r.returncode == 0
                else f"HANDOFF regeneration FAILED: {r.stderr.strip()[:160]}")
    except Exception as e:  # report, never traceback
        return f"HANDOFF regeneration FAILED: {type(e).__name__}"


def main() -> int:
    # This tool prints non-ASCII markers. stdout/stderr default to the LOCALE
    # encoding, so on a non-UTF-8 machine printing a finding could raise
    # UnicodeEncodeError mid-close (review 2026-08-31).
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--abandon", metavar="REASON")
    ap.add_argument("--skip-review", metavar="REASON",
                    help="record the convention's conscious skip in # Review when it is empty, then close")
    ap.add_argument("--outcome", metavar="TEXT")
    ap.add_argument("--force-lint", action="store_true")
    ap.add_argument("--root", default=".")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    scripts_dir = Path(__file__).resolve().parent

    record = resolve(args.target, root)
    if record is None:
        return 1
    # lstrip BOM: a UTF-8 BOM before the first --- silently defeated
    # frontmatter detection (red-team 2026-08-30)
    lines = record.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").splitlines()

    # frontmatter status (conforming records only)
    status_ln = None
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:60], 1):
            if line.strip() == "---":
                break
            if re.match(r"status:\s*\S", line):
                status_ln = i
                break
    if status_ln is None:
        print(f"refusing: {record.name} has no frontmatter `status:` — "
              f"freeform records close manually (see the convention)", file=sys.stderr)
        return 1
    current = lines[status_ln].split(":", 1)[1].strip()
    if args.skip_review is not None and not args.skip_review.strip():
        print("refusing: --skip-review requires a non-empty reason "
              "(the skip itself becomes part of the record)", file=sys.stderr)
        return 2
    # canonical-terminal only: a near-terminal status ("closed"/"done") is an
    # unregistered close — the closer proceeds and canonicalizes it, which is
    # exactly what the close-gate hook's vocabulary note tells the author to do
    if sv.is_terminal(current):
        # A record that went terminal by hand (an Edit of the frontmatter, not this
        # closer) skipped the stamp, the outcome or skip line, and the page. Verify it
        # and refresh the page instead of refusing: measured 2026-09-17, 3 of 5 closes
        # were hand edits, and the close-gate hook now names them and sends the model
        # here. Order (review 2026-09-18): record the skip FIRST when asked, so the
        # lint judges the record as it will stand; then lint; then hold the review gate.
        now_ = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        review = [l for l in section_body(lines, "Review")
                  if l.strip() and not l.strip().startswith("(empty until")]
        wrote_skip = False
        stamped = False
        if args.outcome or args.abandon is not None:
            print("note: --outcome/--abandon are ignored on an already-terminal record "
                  "(the closer never rewrites a closed record's outcome; append by hand "
                  "with a dated note if it must change)", file=sys.stderr)
        if not review and args.skip_review:
            skip_line = (f"Review: skipped — {args.skip_review.strip()} "
                         f"({now_[:10]}; recorded by close-workflow.py --skip-review)")
            lines = insert_skip(lines, skip_line)
            for i, line in enumerate(lines[1:60], 1):
                if line.strip() == "---":
                    break
                if re.match(r"updated:\s*", line):
                    lines[i] = f"updated: {now_}"  # the record changed; say when
                    stamped = True
                    break
            # the scaffold placeholder is stale text once a real skip sits beside it
            lines = [l for l in lines if not re.match(r"\s*\(empty until", l, re.I)]
            record.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
            lines = record.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").splitlines()
            review = [skip_line]
            wrote_skip = True
            print(f"review: recorded skip — {args.skip_review.strip()}", file=sys.stderr)
        elif review and args.skip_review:
            print("note: # Review already carries content; --skip-review ignored", file=sys.stderr)
        findings = load_lint(scripts_dir)(record)
        if findings and not args.force_lint:
            print(f"rot lint REFUSED the verification: {len(findings)} finding(s) on an "
                  f"already-terminal record — reconcile per the convention's correction "
                  f"rules, or rerun with --force-lint and record why. If the finding is an "
                  f"empty `# Review`, `--skip-review \"<reason>\"` records the skip and is "
                  f"the remedy:", file=sys.stderr)
            for kind, n1, a_, n2, b_ in findings:
                print(f"  [{kind}] line {n1}: {a_}", file=sys.stderr)
                if b_:
                    print(f"    ⟂ line {n2}: {b_}", file=sys.stderr)
            return 3
        if not review:
            # a record whose `# Review` is empty OR missing altogether: the lint files a
            # missing section as n/a, so this branch must hold the gate itself
            handoff_msg = refresh_page(root, scripts_dir)
            print(f"review gate REFUSED: {record.name} is already terminal but `# Review` is "
                  f"empty or absent — append a verdict block, or rerun with "
                  f"--skip-review \"<reason>\" to record a conscious skip. {handoff_msg}.", file=sys.stderr)
            return 4
        lint_msg = "lint clean" if not findings else f"{len(findings)} lint finding(s) accepted by --force-lint"
        handoff_msg = refresh_page(root, scripts_dir)
        touched = ("recorded skip written" + (", updated: stamped" if stamped else ", no updated: field to stamp")
                   if wrote_skip else "record untouched")
        print(f"verified: {record} already terminal ('{current}') · {lint_msg} · # Review present · {touched} · {handoff_msg}")
        return 0
    if sv.classify(current) not in ("open", "parked"):
        print(f"note: current status '{current}' is outside the convention's "
              f"open/parked vocabulary; closing anyway with a canonical "
              f"terminal status", file=sys.stderr)

    if args.abandon is not None and not args.abandon.strip():
        print("refusing: --abandon requires a non-empty reason "
              "(an empty $VAR would have recorded a false completion)", file=sys.stderr)
        return 2

    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    today = now[:10]

    # review gate: # Review must carry content beyond the scaffold placeholder
    review = [l for l in section_body(lines, "Review")
              if l.strip() and not l.strip().startswith("(empty until")]
    if not review and args.skip_review:
        # the convention's conscious skip, written where a verdict would go, so an
        # autonomous run with no reviewer closes on a recorded skip instead of stalling
        skip_line = (f"Review: skipped — {args.skip_review.strip()} "
                     f"({today}; recorded by close-workflow.py --skip-review)")
        lines = insert_skip(lines, skip_line)
        review = [skip_line]
        # write the recorded skip BEFORE the lint runs: the lint reads the file on
        # disk, and a skip it never saw would leave the review gate judging stale
        # text (review 2026-09-18). The status is still open at this point.
        record.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        lines = record.read_text(encoding="utf-8", errors="replace").lstrip("\ufeff").splitlines()
        print(f"review: recorded skip — {args.skip_review.strip()}", file=sys.stderr)
    elif review and args.skip_review:
        print("note: # Review already carries content; --skip-review ignored", file=sys.stderr)
    if not review:
        print("review gate REFUSED: `# Review` is empty — append a verdict block "
              "or a recorded skip (with reason) before closing. "
              "The gate checks the record, not the producer.", file=sys.stderr)
        return 4

    # rot lint before the status flips
    findings = load_lint(scripts_dir)(record)
    if findings and not args.force_lint:
        print(f"rot lint REFUSED the close: {len(findings)} finding(s) — reconcile "
              f"per the convention's correction rules, or rerun with --force-lint "
              f"and record why:", file=sys.stderr)
        for kind, n1, a, n2, b in findings:
            print(f"  [{kind}] line {n1}: {a}", file=sys.stderr)
            if b:
                print(f"    ⟂ line {n2}: {b}", file=sys.stderr)
        return 3

    # flip the status, bump updated, append outcome/abandon reason
    new_status = "abandoned" if args.abandon is not None else "completed"
    lines[status_ln] = f"status: {new_status}"
    for i, line in enumerate(lines[1:60], 1):
        if line.strip() == "---":
            break  # frontmatter fence: never touch body lines starting 'updated:'
        if re.match(r"updated:\s*", line):
            lines[i] = f"updated: {now}"
            break
    additions = []
    if args.abandon is not None:
        additions.append(f"Abandoned ({today}): {args.abandon.strip()}")
    if args.outcome:
        additions.append(args.outcome.strip())
    if additions:
        # insert INSIDE the Outcome section (any H1-H3 shape, matching how section_body
        # reads it), creating it at the record's own heading level when absent; an
        # H1-only match appended a second `# Outcome` to H2 records (review 2026-09-18)
        out_ln = heading_index(lines, "Outcome")
        if out_ln is None:
            lines = insert_section(lines, "Outcome", [])
            out_ln = heading_index(lines, "Outcome")
        end = next((i for i in range(out_ln + 1, len(lines))
                    if re.match(r"^#{1,3}\s+\S", lines[i])), len(lines))
        insert = []
        for a in additions:
            insert += ["", a]
        lines[end:end] = insert + ([""] if end < len(lines) else [])
    # drop the scaffolder's own "(empty until ...)" placeholder: by close time
    # a real verdict sits beside it, and leaving it behind is stale text in a
    # record whose whole job is to be trustworthy
    lines = [l for l in lines if not re.match(r"\s*\(empty until", l, re.I)]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip() + "\n"
    record.write_text(text, encoding="utf-8")

    # derived page: regenerate when present, create at the first close when
    # absent. Measured 2026-09-15: headless, the skill's "offer to generate it"
    # has nobody to ask, so a fresh project never got the page. Never hand-write
    # it; the hook keeps its never-creates rail. Opt-out: the same preference.
    handoff_msg = refresh_page(root, scripts_dir)

    print(f"closed: {record} -> status: {new_status} · {handoff_msg}")
    if args.force_lint and findings:
        print(f"note: closed over {len(findings)} lint finding(s) by --force-lint — "
              f"record the override reason in the file.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
