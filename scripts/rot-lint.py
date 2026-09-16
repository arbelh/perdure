#!/usr/bin/env python3
"""rot-lint.py — detect record rot in perdure workflow records.

Rot = a record contradicting itself or contradicting git: the one failure mode
that makes records worse than none, because a misled reader has no signal to
distrust a confident record.

Deterministic checks only (every kind lint() can emit — CHECKS below is the
one list, and eval T14 asserts it equals what the code emits):
  structure              unclosed code fence; duplicate ids in a continuing table
  conflict-marker        unresolved git conflict markers
  status-nonascii        non-ASCII (possible homoglyph) in the status value
  status-vs-git          "nothing committed" vs commits on the record's files
  review-gate-vs-status  terminal status over an empty or pending # Review

REMOVED in v3.9.0, and worth saying why. Three checks (intra-line,
status-vs-body, terminal-vs-blocked) matched a fixed table of English
phrases. An audit (2026-09-04) measured that table producing ONE finding
across the maintainer's 34 records; one pair could not fire at all, its
positive side matching 0 of 138,737 corpus lines; and 0 of 4 planted
contradictions were caught once the same records were reworded into another
team's vocabulary. The phrases also encoded one employer's deploy nouns and
branch names, shipped in a public artifact. A check calibrated to one corpus
reports no findings for everyone else, which is the false clean this tool
exists to prevent. What remains compares fields the convention defines, plus
one narrow question put to git.

EVERY RUN REPORTS ITS OWN COVERAGE. A check that silently does not run is a
false clean — worse than no check, because it invites trust. Audit
2026-09-04: both terminal gates had never run on 8 of the maintainer's own 34
records (8 of 14 in the calibration repo, 0 of 20 in the plugin's own),
because `in progress` with a space is not a vocabulary value, and nothing
said so. So after the findings the tool prints, per check, how many
records it ran on and the reason for every record it did not; then it names
the records where a check COULD NOT run (the tool's limit — distinct from a
check that did not apply because the record is open). The verdict line never
says "clean": it states findings over records, and how many were left partly
unchecked.

ADVISORY BY DESIGN: prints contradicting lines side by side and exits 0 so a
human adjudicates; --strict exits 1 when findings exist (for CI/eval use).
Unchecked records do not change the exit code — an open policy question
recorded in ADR-008; this release changes what is PRINTED, not what fails.
Known out of scope: a contradiction stated only in ordinary prose is not read
at all. The phrase table that attempted it is gone, for the reasons above.
External-system state is never read.

Usage: rot-lint.py [--strict] [record.md ... | project-root | records-dir]
       A project root — any directory holding .git or perdure/ — lints
       perdure/workflows/*.md and reports zero records when none exist yet;
       root-level .md files are not read, and a stderr note counts them. Any
       other directory is linted as a directory OF records: every .md in it,
       INDEX.md excepted. A project's subdirectory holds neither marker and
       is therefore linted as a records directory, not walked up to its root.
"""
from __future__ import annotations
import importlib.util, os, re, subprocess, sys
from pathlib import Path

# shared status vocabulary (one source of truth across all consumers)
_sv_spec = importlib.util.spec_from_file_location(
    "_status_vocab", Path(__file__).resolve().parent / "_status_vocab.py")
sv = importlib.util.module_from_spec(_sv_spec)
_sv_spec.loader.exec_module(sv)

# The one phrase left, and it is a GATE rather than a verdict: it decides
# whether to ask git, and git supplies the answer. The phrase table that
# supplied verdicts is gone (see the docstring).
NEG_GIT = re.compile(r"\bnothing\s+committed\b|\bnot\s+committed\b|\bnothing\s+staged\b", re.I)
CONFLICT_RE = re.compile(r"^(<{7}|={7}|>{7})(\s|$)")
DATEISH = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")

# Every finding kind lint() can emit, in report order. The coverage table is
# printed from THIS tuple and eval T14 asserts it equals the set of kinds the
# code actually appends — a hardcoded self-description that can drift from the
# code is precisely the rot class this tool exists to catch (audit 2026-09-04).
CHECKS = (
    "structure", "conflict-marker", "status-nonascii", "status-vs-git",
    "review-gate-vs-status",
)
NAME_CAP = 3        # records named in the not-checked block before "… and N more"
# The one "unchecked" reason that is about the RUN, not the record: no file
# edit can address it, so the not-checked block states it once with a count
# instead of naming every record for it. Every other reason (no status line, a
# status outside the vocabulary, no heading) is a per-record defect and names
# the record, because those are the files someone has to go and fix.
NO_GIT = "not inside a git repository"
RUN_LEVEL = {NO_GIT}
SCOPE = (
    "\nscope: each check compares fields perdure writes (status, headings, tables,\n"
    "# Review) against each other, or against git. A contradiction stated only\n"
    "in prose is not read at all. No external system is read. \"ran\" means the\n"
    "check examined the record, not that the record is true."
)


def read_record(path: Path):
    """Read a record, tolerant of a UTF-8 BOM (which otherwise defeats the
    frontmatter fence detection and lets a contradiction escape every check)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if text and text[0] == "﻿":
        text = text[1:]
    return text.splitlines()


def fenced_lines(lines):
    """Set of 1-based line numbers inside ``` fenced code blocks — completion
    phrases there are examples/logs, not the record's own state claims."""
    fenced, in_fence = set(), False
    for n, l in enumerate(lines, 1):
        if re.match(r"\s*```", l):
            in_fence = not in_fence
            fenced.add(n)          # the fence line itself is not scannable prose
            continue
        if in_fence:
            fenced.add(n)
    return fenced


def find_status(lines):
    """Return (line_no, text) of the status declaration, else (None, '')."""
    in_fm = False
    for n, l in enumerate(lines, 1):
        if n == 1 and l.strip() == "---":
            in_fm = True
            continue
        if in_fm:
            if l.strip() == "---":
                in_fm = False
                continue
            m = re.match(r"status:\s*(.+)", l)
            if m:
                return n, m.group(1)
        if re.match(r"-\s+\*\*Status", l):
            return n, l
    return None, ""


def started_date(lines):
    for l in lines[:30]:
        m = re.search(r"(?:started|date)[:*\s]+.*?(20\d\d-\d\d-\d\d)", l, re.I)
        if m:
            return m.group(1)
    return None


def git(args, cwd):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def _exists(p: Path) -> bool:
    """Path.exists() that answers False instead of raising when the name cannot
    be a path on this filesystem. pathlib swallows only ENOENT/ENOTDIR/EBADF/
    ELOOP; a >255-byte segment raises ENAMETOOLONG under Python 3.9 (this
    machine's /usr/bin/python3, which the close-gate hook runs), and one such
    backticked token killed a whole run — 0 bytes of stdout, no table, no
    verdict, hook silently disabled (review 2026-09-04, round 5). A token the
    filesystem cannot hold does not exist."""
    try:
        return p.exists()
    except (OSError, ValueError):
        return False


def lint_report(path: Path):
    """Return (findings, coverage, info).

    findings  list of (kind, line, text, line2, text2) — unchanged shape
    coverage  {kind: (state, reason)} for EVERY kind in CHECKS, where state is
              "ran"       the check examined this record
              "n/a"       its precondition is not met by the record's own shape
                          (an open status, no # Review heading) — expected
              "unchecked" the TOOL could not evaluate it (no status line, a
                          status the vocabulary cannot classify, no git) —
                          a coverage gap the reader must be told about
    info      {"status_line": n|None, "status": text} for the not-checked block
    """
    findings = []
    cov = {}
    lines = read_record(path)
    sn, status = find_status(lines)
    fenced = fenced_lines(lines)
    cov["structure"] = cov["conflict-marker"] = ("ran", None)   # need no status

    # -- unclosed fence: an odd number of ``` fences marks everything after
    #    the stray fence as quoted text and silently suppresses body scanning
    #    (review 2026-08-30) — surface it instead of scanning blind
    fence_marks = [n for n, l in enumerate(lines, 1)
                   if l.lstrip().startswith("```")]
    if len(fence_marks) % 2 == 1:
        findings.append(("structure", fence_marks[-1],
                         lines[fence_marks[-1] - 1].strip()[:160], 0,
                         "unclosed code fence — the rest of the record is "
                         "treated as quoted text and not scanned"))

    # -- conflict markers: an unresolved merge left contradictory claims in the
    #    record (red-team 2026-08-30: a terminal record with <<<<<<< and two
    #    opposing status claims passed clean). Fenced lines are quoted text;
    #    ======= / >>>>>>> count only after a real "<<<<<<< label" opener, so a
    #    7-char setext underline never false-flags (review 2026-08-30).
    saw_opener = False
    for n, l in enumerate(lines, 1):
        if n in fenced:
            continue
        if re.match(r"<{7} \S", l):
            saw_opener = True
            findings.append(("conflict-marker", n, l.strip()[:160], 0,
                             "unresolved git conflict markers in the record"))
        elif saw_opener and re.match(r"(={7}|>{7})(\s|$)", l):
            findings.append(("conflict-marker", n, l.strip()[:160], 0,
                             "unresolved git conflict markers in the record"))

    # -- homoglyph/invisible status: surface a non-ASCII status value rather
    #    than silently treating it as unrecognized (an attacker could paste a
    #    Cyrillic-e 'completed' that reads terminal to a human).
    cov["status-nonascii"] = ("ran", None) if sn else ("unchecked", "no status line")
    if sn and sv.has_nonascii(status):
        findings.append(("status-nonascii", sn, status.strip()[:160], 0,
                         "status value contains non-ASCII characters (possible "
                         "homoglyph) — retype it in plain ASCII"))

    # -- status-vs-git: "nothing committed" vs commits on the record's own files
    # abspath, not resolve: a RELATIVE path's parent chain bottoms out at "."
    # and never reaches the repo root, so `rot-lint.py workflows/x.md` from a
    # subdirectory printed the environmental "not inside a git repository" for a
    # record that was (review 2026-09-04); resolve() would re-home symlinked
    # records, which the hook deliberately avoids (rot-lint-gate.py normpath)
    repo = Path(os.path.abspath(path))
    while repo.parent != repo and not (repo / ".git").exists():
        repo = repo.parent
    if not (repo / ".git").exists():
        cov["status-vs-git"] = ("unchecked", NO_GIT)
    elif not sn:
        cov["status-vs-git"] = ("unchecked", "no status line")
    elif not NEG_GIT.search(status):
        # the check is gated on a literal "nothing committed" claim; the table
        # shows how often that gate actually opens (audit 2026-09-04: 0 of 34)
        cov["status-vs-git"] = ("n/a", 'status carries no "nothing committed" claim')
    else:
        cov["status-vs-git"] = ("ran", None)
    if (repo / ".git").exists() and sn and NEG_GIT.search(status):
        since = started_date(lines)
        # paths the record itself names, that exist in the repo
        cands = set(re.findall(r"`([\w./-]+/[\w.-]+\.\w{2,7})`", "\n".join(lines)))
        named = {m for m in cands
                 if _exists(repo / m) and not m.startswith("perdure/")}
        branches = set(re.findall(r"branch\s+`([\w./-]+)`", "\n".join(lines)))
        if not named and not branches:
            if cands:
                # the record DOES name paths; the TOOL filtered every one out
                # (absent from the working tree, or under perdure/). That is
                # the tool's limit, not the record's shape — "unchecked", not
                # "n/a" (review 2026-09-04: the n/a wording was literally false)
                cov["status-vs-git"] = ("unchecked", "the paths this record names are "
                                        "absent from the working tree or under perdure/ — git was not asked")
            elif any(_exists(repo / m) and not m.startswith("perdure/")
                     for m in re.findall(r"`([\w.-][\w./-]*)`", "\n".join(lines))
                     if ".." not in m.split("/")):
                # the record names something that EXISTS in the working tree but
                # that this tool's `dir/file.ext` pattern cannot see — a bare
                # `README.md` or `Makefile`, a `.gitignore`, a `src/lib` directory.
                # Decided by existence, not token shape: round 4 found a shape
                # regex calling `sys.argv` and `example.com` filenames while
                # missing `Makefile`. The TOOL's limit, not the record's shape.
                # (If the record ALSO names a filtered `dir/file.ext`, the first
                # arm's reason is printed — it is unchecked either way.)
                cov["status-vs-git"] = ("unchecked", "the record names paths that exist in the "
                                        "working tree but do not match this tool's `dir/file.ext` "
                                        "pattern — git was not asked")
            elif (toks := sorted({m for m in re.findall(r"`([\w.-][\w./-]*)`", "\n".join(lines))
                                  if re.search(r"\w", m) and ".." not in m.split("/")
                                  and not m.startswith("perdure/")})) \
                    and any(git(["log", "--oneline", "-1", "--", *toks[i:i + 20]], repo)
                            for i in range(0, len(toks), 20)):
                # the record names a path git HAS history for but the working
                # tree no longer has — a since-deleted file. Git was asked only
                # whether such history exists, in chunks of 20 tokens so no token
                # is dropped (round 6: a [:20] cap sent a deleted file that sorted
                # past position 20 back to the false n/a); the comparison this
                # check makes for files that exist was not run for it.
                cov["status-vs-git"] = ("unchecked", "the record names paths git has history for "
                                        "but the working tree no longer has — git was asked only whether "
                                        "they have history, not what was committed after the record's start date")
            else:
                # the claim gate opened but the record names nothing git can be
                # asked about — say so rather than report a comparison that never ran
                cov["status-vs-git"] = ("n/a", "record names no file path or branch to compare against git")
        evidence = ""
        if named:
            args = ["log", "--oneline"]
            if since:
                # `{date} 00:00`, never a bare date: git approxidate fills the
                # unset fields from the CURRENT wall clock, so a bare
                # `--since=2026-09-02` answered differently depending on the
                # hour the lint ran (the audit measured 0 commits against 13
                # for one repo and date). handoff.py:292 already pinned its
                # own comparison this way, though against a different anchor
                # and boundary (`updated:` and 23:59). The shared property is
                # that neither leaves the time for git to infer.
                args += [f"--since={since} 00:00"]
            evidence = git([*args, "--", *sorted(named)[:20]], repo)
        if not evidence:
            for b in branches:
                if git(["rev-parse", "--verify", "--quiet", b], repo):
                    evidence = git(["log", "--oneline", "-4", b], repo)
                    if evidence:
                        break
        if evidence:
            first = evidence.splitlines()[0]
            findings.append(("status-vs-git", sn, status.strip()[:160], 0,
                             f"{len(evidence.splitlines())}+ commits touched this "
                             f"record's named files/branch after its start date "
                             f"(e.g. {first[:80]}) — verify whether they belong to "
                             f"this work; if so, the status is stale"))

    # -- the remaining terminal gate keys on the shared vocabulary, so a
    #    status the vocabulary cannot classify silently disables it. Report
    #    that as "unchecked" — distinct from an open or parked record, where
    #    it legitimately does not apply ("n/a").
    if not sn:
        gate_cov = ("unchecked", "no status line")
    elif sv.classify(status) == "none":
        # `status:` with nothing after it (or only stealth controls): the
        # vocabulary returns "none", a sixth class the first cut never tested,
        # so it fell through to the benign n/a arm and the record went un-named
        # — one trailing space flipped a disclosed gap into a silent one
        # (review 2026-09-04)
        gate_cov = ("unchecked", "status value is empty")
    elif sv.classify(status) == "unknown":
        gate_cov = ("unchecked", "status is not a vocabulary value "
                                 "(in-progress | parked | completed | abandoned)")
    elif not sv.is_gate_terminal(status):
        gate_cov = ("n/a", "status is not terminal")
    else:
        gate_cov = None                  # terminal: each gate reports its own site
    # -- review-gate-vs-status: a terminal (or near-terminal) status above a
    #    # Review section that is empty or still carries a pending marker.
    #    Measured (gauntlet G1, 2026-08-30): an interrupted session hand-flipped
    #    status: completed over "# Review: (not yet performed — do not close)"
    #    and nothing deterministic objected. The closer enforces this gate but
    #    hand-flips bypass it; this check closes the hole for the hook, the
    #    closer, and the HANDOFF generator at once.
    rv_ln, rv_lvl = next(((n, len(m.group(1)))
                          for n, l in enumerate(lines, 1)
                          for m in [re.match(r"(#{1,3})\s+Review\b", l)]
                          if m), (None, 0))
    #    A terminal record with NO # Review heading at all passes this check
    #    today; the table now says so ("n/a: no # Review heading") rather than
    #    letting it read as verified.
    cov["review-gate-vs-status"] = (gate_cov or (("ran", None) if rv_ln else
                                    ("n/a", "no # Review heading")))
    if sn and sv.is_gate_terminal(status):
        if rv_ln:
            body = []
            for n in range(rv_ln, len(lines)):
                # only a heading at the Review heading's own level or shallower
                # ends the section — "## Verdict" under "# Review" is content
                if re.match(rf"#{{1,{rv_lvl}}}\s+\S", lines[n]):
                    break
                body.append((n + 1, lines[n]))
            # The scaffolder's own placeholder is inert boilerplate, not an
            # assertion that review is pending — the deterministic closer
            # filters it exactly this way. Counting it as a pending marker made
            # the closer ACCEPT a close that the lint then flagged forever: the
            # two consumers disagreeing about one record, which is the drift
            # class the shared vocabulary exists to remove. Found by an
            # end-to-end journey on the release artifact (2026-08-31).
            SCAFFOLD = r"\(empty until"
            content = [(n, l) for n, l in body
                       if l.strip() and not re.search(SCAFFOLD, l, re.I)]
            pending = next((n for n, l in content if re.search(
                r"not yet (?:performed|reviewed|done)|do not close|"
                r"review pending|pending review|\bTBD\b", l, re.I)), None)
            if not content:
                findings.append(("review-gate-vs-status", sn, status.strip()[:160],
                                 rv_ln, "# Review is empty — a terminal record needs "
                                        "a verdict or a recorded skip"))
            elif pending:
                findings.append(("review-gate-vs-status", sn, status.strip()[:160],
                                 pending, lines[pending - 1].strip()[:160]))

    # -- structure: duplicate numbered-table ids ACROSS a shared numbering
    #    namespace. A table whose own numbering restarts at 1 opens a fresh
    #    local namespace (two independent 1..N tables are normal); a table that
    #    CONTINUES the file's numbering (first id != 1) shares the global
    #    namespace, so re-defining an id there is a real cross-reference hazard.
    tables, cur = [], []
    for n, l in enumerate(lines, 1):
        m = re.match(r"\|\s*(?:D\s*)?(\d{1,3})\s*\|", l)
        if m and l.count("|") >= 3:
            cur.append((n, int(m.group(1))))
        elif cur:
            tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    seen = {}
    for tbl in tables:
        if tbl[0][1] == 1:
            continue                     # local namespace, skip
        for n, k in tbl:
            if k in seen:
                findings.append(("structure", seen[k],
                                 f"decision/table id {k} (first defined)",
                                 n, f"id {k} defined again in a continuing table"))
                seen[k] = -10**9
            elif seen.get(k) != -10**9:
                seen[k] = n
    for k in CHECKS:                     # a check that forgot to report is a bug,
        cov.setdefault(k, ("unchecked", "coverage not recorded (bug)"))  # not a pass
    return findings, cov, {"status_line": sn, "status": status}


def lint(path: Path):
    """Findings only — the contract handoff.py and close-workflow.py import."""
    return lint_report(path)[0]


def print_coverage(reports):
    """Per-check ran/records with every not-ran reason, the not-checked block
    (records where a check COULD NOT run, capped at NAME_CAP), and the scope."""
    from collections import Counter
    n = len(reports)
    width = max(len(k) for k in CHECKS)
    print(f"\n{'checks':<{width}}    ran/records")
    for k in CHECKS:
        ran = sum(1 for _, _, cov, _ in reports if cov[k][0] == "ran")
        why = Counter(cov[k] for _, _, cov, _ in reports if cov[k][0] != "ran")
        # unchecked first — that is the number a reader must not scroll past
        notes = [f"{state} {c}: {reason}" for (state, reason), c in
                 sorted(why.items(), key=lambda kv: (kv[0][0] != "unchecked", -kv[1]))]
        print((f"  {k:<{width}}  {ran:>3}/{n:<3}" + ("  " + " · ".join(notes) if notes else "")).rstrip())
    # A finding whose kind is outside CHECKS has no row above. evals/ast_gate.py
    # refuses the code shapes that produce one, but a gate over source text can
    # be refactored around — four review rounds each found a shape it missed.
    # This row covers every kind that ENTERS a findings list main() stores: it
    # is computed from those lists, whatever name or alias put a finding there,
    # and printed on STDOUT inside the table so it reaches the close-gate hook,
    # --strict readers and humans alike. It does NOT cover a finding line
    # printed without entering a list — eval T14 #7j pins that property (every
    # printed [kind] is a table row) over every rot-lint stdout the harness
    # captures, collected in T14CAPS as each is made. (Round 3: a stderr
    # belt never reached the hook; round 4: main() printed from a local name the
    # row never saw.)
    # key=repr: two phantom kinds of different types (None and a str) must give
    # two rows, not a TypeError that kills the table (round 4)
    phantom = sorted({f[0] for _, fs, _, _ in reports for f in fs} - set(CHECKS), key=repr)
    for k in phantom:
        n_hit = sum(1 for _, fs, _, _ in reports if any(f[0] == k for f in fs))
        print(f"  (bug) {k}  {n_hit}/{n}  emitted by the code but absent from CHECKS — "
              f"no coverage was recorded for it; this is a defect in the lint, not in a record")
    # Run-level reasons (RUN_LEVEL) are stated once with a count — a block that
    # names every record for "no git" is scrolled past, which is the silent
    # skip with extra steps. Per-record reasons name the record: those are the
    # files someone has to fix, and the cap keeps the list readable.
    run_level = Counter(cov[k][1] for _, _, cov, _ in reports for k in CHECKS
                        if cov[k][0] == "unchecked" and cov[k][1] in RUN_LEVEL)
    def singled_out(cov):
        return [(k, cov[k][1]) for k in CHECKS
                if cov[k][0] == "unchecked" and cov[k][1] not in RUN_LEVEL]
    unchecked = [(t, cov, info) for t, _, cov, info in reports if singled_out(cov)]
    # The COUNT is every record with any unchecked check, run-level included;
    # only the NAMING is restricted to records a per-record reason singles out.
    # The first cut counted the named list and printed "0 record(s) where a
    # check could not run" directly above "(3 record(s): not inside a git
    # repository)" — a self-contradiction in the tool built to catch them, and
    # the verdict lost its qualifier with it (review 2026-09-04).
    n_gap = sum(1 for _, _, cov, _ in reports
                if any(cov[k][0] == "unchecked" for k in CHECKS))
    if n_gap:
        print(f"\nnot checked — {n_gap} record(s) where a check could not run")
        for reason, c in sorted(run_level.items()):
            print(f"  ({c} record(s): {reason} — see the table above)")
        for t, cov, info in unchecked[:NAME_CAP]:
            so = singled_out(cov)
            print(f"  {t}")
            if info["status_line"]:
                st = info["status"].strip()
                print(f"    line {info['status_line']}: {st[:100]}{'…' if len(st) > 100 else ''}")
            print(f"    {', '.join(k for k, _ in so)} — {'; '.join(sorted({r for _, r in so}))}")
        if len(unchecked) > NAME_CAP:
            print(f"  … and {len(unchecked) - NAME_CAP} more")
    print(SCOPE)
    return n_gap


def main():
    # This tool prints non-ASCII markers. stdout defaults to the LOCALE
    # encoding with errors='strict', so on a non-UTF-8 machine printing a
    # finding raised UnicodeEncodeError — and the close-gate hook reads a
    # non-zero exit as "skip", silently disabling the gate there.
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    if any(a in ("-h", "--help") for a in sys.argv[1:]):
        # the usage block is the docstring's tail, from "Usage:" on
        doc = __doc__ or ""
        print(doc[doc.index("Usage:"):].rstrip() if "Usage:" in doc else "Usage: rot-lint.py [--strict] [targets...]")
        return 0
    argv = [a for a in sys.argv[1:] if a != "--strict"]
    strict = "--strict" in sys.argv
    targets = []
    for a in (argv or ["."]):
        p = Path(a)
        if p.is_dir():
            wf = p / "perdure" / "workflows"
            if wf.is_dir():
                # A project root. Only the records, even when there are none
                # yet: an empty directory is zero records, not a cue to go
                # looking elsewhere. The previous `glob(...) or glob(...)`
                # treated the empty list as falsy and fell through.
                targets += sorted(wf.glob("*.md"))
            elif (p / ".git").exists() or (p / "perdure").is_dir():
                # A project root with no workflows directory yet — every
                # first run. Zero records. Before 3.9.1 this reached the
                # branch below and reported README.md as a record whose
                # status checks "could not run: no status line". `.exists()`
                # not `.is_dir()`: in a git worktree `.git` is a FILE.
                # Root-level .md files are deliberately NOT read; say so, by
                # count, so a zero-record result is never a silent one
                # (review 2026-09-14: a git-rooted folder of loose records
                # would otherwise print "no findings" about files never read).
                skipped = sum(1 for _ in p.glob("*.md"))
                if skipped:
                    print(f"note: {skipped} .md file(s) at the root of {a} were not "
                          "read as records — a project root's records live in "
                          "perdure/workflows/", file=sys.stderr)
            else:
                # A directory OF records (perdure/workflows/ itself, or
                # perdure/decisions/): lint every .md in it.
                targets += sorted(p.glob("*.md"))
        elif p.is_file():
            targets.append(p)
        else:
            # A verification tool must never answer "clean" about a path it
            # never read: an unresolvable target silently produced exit 0, so
            # a mistyped path sailed through the close gate green
            # (pre-publish verification, 2026-08-31).
            print(f"cannot lint '{a}': no such file or directory", file=sys.stderr)
            sys.exit(2)
    reports = []                         # (path, findings, coverage, info)
    for t in targets:
        if t.name == "INDEX.md":
            continue
        # Bind and store in ONE step, and print/count from the STORED lists
        # below. The (bug) row in print_coverage() is computed from `reports`,
        # so everything printed or counted here must come from the same objects
        # — round 4 (2026-09-04) rebound a local name after the store and the
        # phantom was printed and counted with no row.
        reports.append((t, *lint_report(t)))
    for t, fs, _, _ in reports:
        if fs:
            print(f"\n{t}")
            for kind, n1, a, n2, b in fs:
                loc = f"line {n1}" + (f" ⟂ line {n2}" if n2 else "")
                print(f"  [{kind}] {loc}")
                print(f"    {a}")
                print(f"    ⟂ {b}")
    # counted AFTER printing, from the stored lists, so a mutation during the
    # print loop is still counted and rowed
    total = sum(len(fs) for _, fs, _, _ in reports)
    # findings first, coverage after: the close-gate hook keys on the VERDICT
    # line (the last line, "ROT: …") when findings exist, and when it must
    # truncate it cuts the findings head and keeps this coverage tail
    n_unchecked = print_coverage(reports)
    n = len(reports)
    verdict = (f"ROT: {total} finding(s) across {n} record(s)" if total
               else f"no findings across {n} record(s)")
    if n_unchecked:
        verdict += f" — {n_unchecked} record(s) carry a check that could not run"
    print(f"\n{verdict}")
    sys.exit(1 if (strict and total) else 0)


if __name__ == "__main__":
    main()
