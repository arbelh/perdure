#!/usr/bin/env python3
"""coverage.py — check the records against the population of sessions.

This is the check Tier R exists for. `perdure/raw/INDEX.jsonl` says which
sessions ran; `perdure/workflows/` says which work was written down. Until
now nothing compared them, so a session that produced no record was invisible
from inside the system — measured in the 2026-08-31 lifecycle dry run, which
produced four records for five units of work and could not tell.

WHAT THIS DOES NOT DO, deliberately: it does not decide whether a session
*should* have produced a record, and it never calls an unlinked session a
violation. The convention says plainly not to open records for typo fixes,
obvious edits, or interactive back-and-forth, so most sessions in a healthy
project legitimately have none. Asserting otherwise would be the exact
overclaim this project exists to prevent. It reports what it can check, separates what it could not check from what it
checked and found nothing for, and treats the remainder as a question for a
human rather than a verdict.

Four buckets, in descending strength of evidence:

  CITED        a record's FRONTMATTER names the session id. Checkable.
               Deliberately not "a UUID appears somewhere in the record": that
               counted a quoted log line, and a sentence declining to record a
               session, as evidence it had been recorded.
  WEAK         a body mention, or a record whose [started, updated] window
               intersects the session's. Correlation, labelled as such
               everywhere including --json — two things happening at once is
               not evidence that one describes the other.
  UNEXPLAINED  neither. Not an error. A list to look at.
  UNEVALUABLE  no usable timestamps, so no check was possible. Distinct from
               UNEXPLAINED, because "I could not check" is not "I found nothing".

A KNOWN STRUCTURAL LIMIT, stated because it changes how the numbers read: the
population is keyed by working directory, because that is how the transcript
store is keyed — but records describe a REPOSITORY, and one session routinely
edits a repo other than its cwd. Work done from elsewhere is invisible here and
is reported as records-without-sessions rather than guessed at. Coverage is a
per-directory measure; do not read it as a per-repo one.

Usage:
  coverage.py [--root DIR]                    report coverage
  coverage.py --strict --min-prompts N        exit 1 on unexplained sessions
                                              with at least N prompts
  coverage.py --json                          machine-readable

Exit codes: 0 ok · 1 strict threshold exceeded · 2 no index (run /perdure:raw)
"""
from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

INDEX_REL = Path("perdure") / "raw" / "INDEX.jsonl"
WORKFLOWS_REL = Path("perdure") / "workflows"

# A session id as it appears in an index entry, and the 8-char short form a
# human or a record is likely to write.
_UUIDISH = re.compile(r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", re.I)
_SHORT = re.compile(r"\b[0-9a-f]{8}\b", re.I)
_TS = re.compile(r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}))?")
_ISO = re.compile(
    r"(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?(\.\d+)?"
    r"\s*(Z|[+-]\d{2}:?\d{2})?)?")


def instant(s: str, end_of_day: bool = False):
    """Parse a timestamp to an aware datetime, or None.

    Records are stamped with a LOCAL offset (new-workflow.py uses
    .astimezone(), so -07:00 here) while index timestamps come from transcripts
    as UTC "Z". Comparing their ISO strings was wrong in both directions —
    a record written during a session read as no overlap, and one written seven
    hours later read as overlapping (review 2026-09-02). Compare instants.

    A date with no time is a whole day: opening bound at 00:00, closing bound
    at 23:59:59, because a bare date sorts before every timestamp on that same
    day and inverted the interval test.
    """
    if not isinstance(s, str) or not s:
        return None
    m = _ISO.search(s)
    if not m:
        return None
    date, hh, mm, ss, frac, off = m.groups()
    had_time = hh is not None
    if hh is None:
        hh, mm, ss = ("23", "59", "59") if end_of_day else ("00", "00", "00")
    if not off:
        # A bare DATE has no offset by nature and its window is a whole day —
        # the worst-case ambiguity is smaller than the bound itself, so treat it
        # as UTC. A date WITH a time but no offset is the genuinely ambiguous
        # case: assuming UTC produced a silent seven-hour error on a real record
        # in this repo, and a wrong instant feeds --strict. Return None so the
        # session lands in UNEVALUABLE — the honest bucket (review 2026-09-02).
        if had_time:
            return None
        tz = "+00:00"
    elif off.upper() == "Z":
        tz = "+00:00"
    elif re.fullmatch(r"[+-]\d{2}:?\d{2}", off):
        tz = off if ":" in off else off[:3] + ":" + off[3:]
    else:
        return None                     # e.g. a 2-digit "-07": confidently wrong
                                        # is worse than uncheckable
    micro = (frac or ".0")[1:7].ljust(6, "0")
    try:
        return datetime.datetime.fromisoformat(
            f"{date}T{hh}:{mm}:{ss or '00'}.{micro}{tz}")
    except ValueError:
        return None


def load_index(root: Path) -> list[dict]:
    p = root / INDEX_REL
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(d, dict) and isinstance(d.get("session"), str):
            out.append(d)
    return out


def norm_ts(s: str) -> str:
    """Comparable prefix of a timestamp: YYYY-MM-DDTHH:MM, or the date alone."""
    if not isinstance(s, str):
        return ""
    m = _TS.search(s)
    if not m:
        return ""
    return f"{m.group(1)}T{m.group(2)}" if m.group(2) else m.group(1)


def load_records(root: Path) -> list[dict]:
    d = root / WORKFLOWS_REL
    if not d.is_dir():
        return []
    out = []
    # rglob, not glob: the convention sanctions archiving terminal records into
    # perdure/workflows/<YYYY>/, and handoff.py already reads them that way.
    # Missing them flipped an explicitly CITED session to UNEXPLAINED after a
    # routine `git mv` and newly failed --strict in CI (review 2026-09-02).
    for p in sorted(d.rglob("*.md")):
        if p.name == "INDEX.md":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = {}
        if text.startswith("---"):
            pending, closed = {}, False
            for line in text.splitlines()[1:]:      # to the closing fence, not
                if line.strip() == "---":           # an arbitrary line cap
                    closed = True
                    break
                m = re.match(r"([\w-]+):\s*(.+)", line)
                if m:
                    pending[m.group(1)] = m.group(2).strip()
            # Commit ONLY if the fence actually closed. Without this, a record
            # missing its closing --- parsed its whole body as frontmatter, so a
            # flush-left "session:" line in prose became a citation — the same
            # CITED overclaim, reached through a different door, and rot-lint
            # passes such a file clean (review 2026-09-02).
            if closed:
                fm = pending
        # CITED comes ONLY from an explicit frontmatter key. Scanning the body
        # let any UUID count — including one inside a code fence, and one in a
        # sentence explicitly DECLINING to record that session — so a project
        # with zero real citations reported 100% checkable coverage (review
        # 2026-09-02). That is the precise overclaim this module exists to
        # prevent, in the bucket documented as strong.
        ids = set()
        for key in ("sessions", "session"):
            if key in fm:
                ids |= {i.lower() for i in _SHORT.findall(fm[key])}
                ids |= {i.lower() for i in _UUIDISH.findall(fm[key])}
        # A body mention is a WEAK signal, kept separate and labelled.
        body_ids = {i.lower() for i in _UUIDISH.findall(text)} - ids
        out.append({
            "path": str(p.relative_to(root)),
            "slug": fm.get("workflow") or p.stem,
            "status": fm.get("status", ""),
            "started": norm_ts(fm.get("started", "")),
            "updated": norm_ts(fm.get("updated", "")),
            "started_i": instant(fm.get("started", "")),
            "started_hi": instant(fm.get("started", ""), end_of_day=True),
            "updated_i": instant(fm.get("updated", ""), end_of_day=True),
            "cites": ids,
            "mentions": body_ids,
        })
    return out


def classify(sessions: list[dict], records: list[dict]) -> dict:
    cited, weak, unexplained, unevaluable = [], [], [], []
    linked_keys: set[str] = set()
    for s in sessions:
        sid = s["session"].lower()
        short = sid[:8]
        hits = [r for r in records if sid in r["cites"] or short in r["cites"]]
        if hits:
            cited.append((s, [r["slug"] for r in hits]))
            linked_keys |= {r["path"] for r in hits}
            continue
        s_lo = instant(s.get("first_ts", ""))
        s_hi = instant(s.get("last_ts", ""), end_of_day=True)
        signals = []
        for r in records:
            if sid in r["mentions"]:
                signals.append((r, "mentioned in body"))
                continue
            # a date-only `started` with no `updated` still spans its own day
            r_lo, r_hi = r["started_i"], r["updated_i"] or r["started_hi"]
            if r_lo and s_lo and s_hi and r_lo <= s_hi and s_lo <= r_hi:
                signals.append((r, "time overlap"))
        if signals:
            weak.append((s, [(r["slug"], why) for r, why in signals]))
            linked_keys |= {r["path"] for r, _ in signals}
        elif not s_lo or not s_hi:
            # no usable timestamps: we could not check, which is not the same
            # as finding no link (review 2026-09-02)
            unevaluable.append(s)
        else:
            unexplained.append(s)
    orphan_records = [r for r in records if r["path"] not in linked_keys]
    return {"cited": cited, "weak": weak, "unexplained": unexplained,
            "unevaluable": unevaluable, "orphan_records": orphan_records}


def prompts_of(s: dict) -> int:
    """prompts as an int. A null or string from a forward-compatible index once
    crashed the renderer, and Python's exit 1 is the code this tool defines as
    "strict threshold exceeded" — a death reported as a policy violation."""
    v = s.get("prompts")
    return v if isinstance(v, int) and not isinstance(v, bool) else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 if any unexplained session meets --min-prompts")
    ap.add_argument("--min-prompts", type=int, default=2,
                    help="substance bar for --strict: only unexplained sessions "
                         "with at least this many prompts are counted "
                         "(default 2, so at the default a one-prompt session is "
                         "not flagged)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()

    sessions = load_index(root)
    if not sessions:
        if (root / INDEX_REL).exists():
            print(f"{INDEX_REL} exists but yielded no usable entries — it may be "
                  f"corrupt. Coverage is UNKNOWN, not complete. Try "
                  f"/perdure:raw --verify.", file=sys.stderr)
        else:
            print(f"no session population at {INDEX_REL} — run /perdure:raw "
                  f"first. Coverage is UNKNOWN, not complete.", file=sys.stderr)
        return 2
    records = load_records(root)
    r = classify(sessions, records)

    if args.json:
        print(json.dumps({
            "sessions": len(sessions),
            "records": len(records),
            "cited": [s["session"] for s, _ in r["cited"]],
            "weak": [s["session"] for s, _ in r["weak"]],
            "unexplained": [s["session"] for s in r["unexplained"]],
            "unevaluable": [s["session"] for s in r["unevaluable"]],
            "records_without_a_session": [x["path"] for x in r["orphan_records"]],
            # carried in the machine surface too: a consumer that adds cited and
            # weak into one percentage is computing something this tool does not
            # claim, and --strict exists precisely for CI, which never reads the
            # skill prose (review 2026-09-02)
            "weak_is_heuristic": True,
            "unexplained_is_not_a_violation": True,
            "notes": [
                "cited = a record names the session id in frontmatter; checkable",
                "weak = body mention or time overlap; correlation, not evidence",
                "unexplained is NOT an error: the convention says not to record "
                "typo fixes, obvious edits or back-and-forth",
                "coverage is keyed by working directory, not by repository: "
                "work done from another directory is invisible here",
            ],
        }, indent=2, sort_keys=True))
    else:
        n = len(sessions)
        print(f"population: {n} session(s), {len(records)} record(s)")
        print(f"  cited by a record       {len(r['cited']):4d}   "
              f"(frontmatter names the session id — checkable)")
        print(f"  weak signal only        {len(r['weak']):4d}   "
              f"(HEURISTIC: body mention or time overlap — correlation, "
              f"not evidence)")
        print(f"  unexplained             {len(r['unexplained']):4d}   "
              f"(no link found — NOT an error; see below)")
        if r["unevaluable"]:
            print(f"  unevaluable             {len(r['unevaluable']):4d}   "
                  f"(no usable timestamps — could not check, which is not the "
                  f"same as no link)")
        if r["unexplained"]:
            print()
            print("Unexplained sessions — a question, not a verdict. The "
                  "convention says not to open records for typo fixes, obvious "
                  "edits or back-and-forth, so many of these need none:")
            for s in sorted(r["unexplained"], key=lambda x: x.get("first_ts") or ""):
                pr = prompts_of(s)
                st = "" if s.get("status") == "present" else f" [{s.get('status')}]"
                print(f"    {s['session'][:8]}  {norm_ts(s.get('first_ts',''))[:10]}"
                      f"  {pr:4d} prompt(s){st}")
        if r["unevaluable"]:
            print()
            print("Unevaluable — no usable timestamps, so no check was possible. "
                  "This is not a finding about the work; it is a gap in what "
                  "could be compared:")
            for s_ in r["unevaluable"]:
                print(f"    {s_['session'][:8]}  {prompts_of(s_):4d} prompt(s)")
        if r["orphan_records"]:
            print()
            print(f"{len(r['orphan_records'])} record(s) with no session in "
                  f"this population. Most likely causes, in order:")
            print("  1. The work was done from a DIFFERENT working directory. "
                  "The population is per-project-directory (that is how the "
                  "transcript store is keyed), but records describe a repo — "
                  "and one session often edits another repo. Those sessions are "
                  "in that directory's population, not this one.")
            print("  2. The record predates the index, or its session has been "
                  "pruned and was never swept while present.")
            print("  3. The record was written by hand.")
            print("  None of these is an error. Coverage cannot see work done "
                  "from elsewhere, and does not pretend to.")
            for x in r["orphan_records"][:20]:
                print(f"    {x['path']}")
            if len(r["orphan_records"]) > 20:
                print(f"    … plus {len(r['orphan_records']) - 20} more")
        if not r["cited"] and r["weak"]:
            print()
            print("Note: nothing is CITED yet — every link above is a weak "
                  "signal, and the honest answer to \"is this work recorded?\" "
                  "is \"not established\". To make coverage checkable, name the "
                  "session in a record's frontmatter:  sessions: <id>")

    if args.strict:
        over = [s for s in r["unexplained"]
                if prompts_of(s) >= args.min_prompts]
        if over:
            print(f"\nstrict: {len(over)} unexplained session(s) with "
                  f">= {args.min_prompts} prompt(s)", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
