#!/usr/bin/env python3
"""handoff.py — derive a rot-aware HANDOFF orientation page from perdure/.

The naive version of this idea — mechanically extracting record content into
a one-page summary — strips the surrounding context that lets a reader catch a
stale claim, then presents the stale claim with the summary's implicit
authority. This generator exists to make that shape safe. Its rules, each
closing one of those failures:

  1. LINT-GATED INCLUSION  every record passes scripts/rot-lint.py first; a
     record with findings contributes NO state claims — it is listed under
     "Needs reconciliation" with its finding kinds.
  2. STRUCTURED EXTRACTION ONLY  the page carries the status token, the goal
     line, and the record's own # Next step — never freeform status prose.
     Records without conforming frontmatter contribute no status at all.
  3. PROVENANCE + TIME-SCOPE  every claim names its source record and its
     as-of date; the page is stamped with the generating commit; readers are
     told to regenerate when HEAD has moved.
  4. STALENESS DERIVATION  commits touching a record's named files AFTER its
     `updated:` date get the record flagged "repo activity after last update".
  5. EXTERNAL-STATE HONESTY  a standing footer says external systems
     (experiments, deployments, tickets) are never checked here.

The page is DERIVED, never merged, never hand-maintained (records convention,
Extensions). Regenerate at close or before handing off; --check regenerates
the page in memory and content-compares it to the committed one (volatile
stamp and staleness annotations normalized), so it exits 1 when the records
changed OR the page was hand-edited — with or without git.

Usage: handoff.py [project-root] [--output PATH] [--check]
       Default output: <root>/perdure/HANDOFF.md
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

_sv_spec = importlib.util.spec_from_file_location(
    "_status_vocab", Path(__file__).resolve().parent / "_status_vocab.py")
sv = importlib.util.module_from_spec(_sv_spec)
_sv_spec.loader.exec_module(sv)


def load_lint():
    """Import lint() from the sibling rot-lint.py (hyphenated filename)."""
    path = Path(__file__).resolve().parent / "rot-lint.py"
    spec = importlib.util.spec_from_file_location("rot_lint", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.lint


def git(args, cwd):
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def frontmatter(lines):
    """Return the frontmatter dict, or None when the file has none."""
    if not lines or lines[0].strip() != "---":
        return None
    fm = {}
    for line in lines[1:60]:
        if line.strip() == "---":
            return fm
        m = re.match(r"([\w-]+):\s*(.+)", line)
        if m:
            fm[m.group(1)] = m.group(2).strip()
    return None


def section(lines, heading):
    """Lines of the `# <heading>` section, up to the next H1."""
    out, active = [], False
    for line in lines:
        if re.match(rf"#\s+{re.escape(heading)}\s*$", line):
            active = True
            continue
        if active and re.match(r"#\s+\S", line):
            break
        if active:
            out.append(line)
    return [l.rstrip() for l in out]


def first_text(lines):
    for l in lines:
        if l.strip() and not l.strip().startswith(("(", "<!--")):
            return l.strip()
    return ""


def first_para(lines):
    """Join the first paragraph — a one-line extraction can silently drop a
    continuation line that carries the safety condition ("ONLY IF ...")."""
    para, started = [], False
    for l in lines:
        t = l.strip()
        if not t:
            if started:
                break
            continue
        if not started and t.startswith(("(", "<!--")):
            continue
        started = True
        para.append(t)
    return " ".join(para)


def excerpt(text, cap=160):
    """Word-boundary cap with ellipsis; strip markdown bold markers."""
    text = text.replace("**", "").strip()
    if len(text) <= cap:
        return text
    cut = text[:cap].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + " …"


def date_of(value):
    m = re.search(r"(20\d\d-\d\d-\d\d)", value or "")
    return m.group(1) if m else ""


class Record:
    def __init__(self, path: Path, root: Path):
        self.path = path
        self.rel = path.relative_to(root)
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        fm = frontmatter(lines)
        self.freeform = fm is None or "status" not in fm
        self.status = (fm or {}).get("status", "").strip().lower()
        self.updated = date_of((fm or {}).get("updated", ""))
        self.goal = first_para(section(lines, "Goal"))
        if not self.goal:  # freeform records: the H1 title is the descriptor
            for l in lines:
                m = re.match(r"#\s+(\S.*)", l)
                if m:
                    self.goal = re.sub(r"^Workflow:\s*", "", m.group(1).strip())
                    break
        self.goal = excerpt(self.goal, 220)
        # The record's own status bullet (freeform records). Shown ONLY when
        # the record is lint-clean, clearly attributed, capped, time-scoped —
        # the lint screens bullet statuses against the body the same way it
        # screens frontmatter ones, which is what makes quoting it safe.
        self.status_bullet = ""
        for l in lines:
            m = re.match(r"-\s+\*\*Status[:*\s]*\**:?\s*(.+)", l)
            if m:
                self.status_bullet = excerpt(m.group(1))
                break
        self.next_step = excerpt(first_para(section(lines, "Next step")), 300)
        self.named_files = {m for m in re.findall(
            r"`([\w./-]+/[\w.-]+\.\w{2,7})`", "\n".join(lines))
            if not m.startswith("perdure/")}
        self.findings = []
        self.stale_activity = ""

    @property
    def is_open(self):
        return sv.is_open(self.status)

    @property
    def is_terminal(self):
        return sv.is_gate_terminal(self.status)

    @property
    def is_parked(self):
        return sv.is_parked(self.status)

    def cite(self):
        asof = f" — as of {self.updated}" if self.updated else ""
        return f"[`{self.rel}`]({self.href}){asof}"


def has_supersessor(text: str) -> bool:
    """True iff a `superseded-by:` frontmatter key names an actual supersessor.

    An EMPTY YAML list (`superseded-by: []`) means nothing supersedes this —
    it is the value the /perdure:decide template ships, so treating it as a
    death marker filed every product-created ADR under "Rejected/superseded"
    (pre-publish verification, 2026-08-31). Same for an empty string, `~`,
    `null`, or a bare key.
    """
    m = re.search(r"^superseded-by:[ \t]*(.*)$", text, re.M)
    if not m:
        return False
    v = re.sub(r"\s*#.*$", "", m.group(1)).strip().strip("\"'").strip()
    if v == "":
        # bare key: a BLOCK-form list may follow as indented "- item" lines.
        # Missing this rendered a genuinely superseded ADR under "Decisions in
        # force" — the dangerous direction (review 2026-08-31).
        for line in text[m.end():].splitlines():
            if not line.strip():
                continue
            return bool(re.match(r"^[ \t]+-[ \t]*\S", line))
        return False
    if re.fullmatch(r"\[\s*\]", v) or v.lower() in ("~", "null", "none", "-"):
        return False
    return True


def collect_adrs(root: Path):
    """Parse ADRs (bullet-metadata or YAML form) into (id, title, status, date)."""
    adrs = []
    ddir = root / "perdure" / "decisions"
    if not ddir.is_dir():
        return adrs
    for p in sorted(ddir.glob("*.md")):
        if p.name == "INDEX.md":
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s+ADR-(\d+):\s*(.+)$", text, re.M)
        if m:
            aid, title = m.group(1), m.group(2).strip()
        else:  # YAML frontmatter form (what the /perdure:decide template writes)
            im = re.search(r"^id:\s*\"?(\d+)\"?\s*$", text, re.M)
            tm = re.search(r"^title:\s*(.+?)\s*$", text, re.M)
            aid = im.group(1) if im else "?"
            title = tm.group(1).strip().strip("\"'") if tm else p.stem
        sm = re.search(r"^-\s*\*\*Status\**[:*\s]*\**:?\s*(.+)$", text, re.M) or \
             re.search(r"^status:\s*(.+)$", text, re.M)
        dm = re.search(r"^-\s*\*\*Date\**[:*\s]*\**:?\s*([\d-]+)", text, re.M) or \
             re.search(r"^date:\s*([\d-]+)", text, re.M)
        raw = sm.group(1).strip().rstrip("*").strip() if sm else ""
        low = raw.lower()
        # Classify on the WHOLE status text plus superseded-by markers anywhere
        # in the file: "Accepted (superseded by ADR-9)" is NOT in force, and a
        # first-word parse rendered exactly that under "in force" (review
        # 2026-08-26). ADRs are not rot-linted; parse conservatively instead.
        if any(k in low for k in ("superseded", "rejected", "deprecated")) or \
           has_supersessor(text):
            cls = "dead"
        elif low.startswith("accepted"):
            cls = "accepted"
        elif low.startswith("proposed"):
            cls = "proposed"
        else:
            cls = "unknown"
        adrs.append((aid, title, cls, raw, dm.group(1) if dm else "",
                     p.relative_to(root)))
    return adrs


def build(root: Path):
    lint = load_lint()
    wdir = root / "perdure" / "workflows"
    records = []
    for p in sorted(wdir.rglob("*.md")):
        if p.name == "INDEX.md":
            continue
        rec = Record(p, root)
        try:
            rec.findings = lint(p)
        except Exception as e:
            rec.findings = [("lint-error", 0, str(e)[:120], 0, "")]
        records.append(rec)

    # last repo touch per record (freeform records have no `updated:` key)
    for rec in records:
        rec.touched = rec.updated
        if not rec.touched and (root / ".git").exists():
            rec.touched = git(["log", "-1", "--format=%ad", "--date=short",
                               "--", str(rec.rel)], root)
        if not rec.touched:
            try:
                rec.touched = datetime.date.fromtimestamp(
                    rec.path.stat().st_mtime).isoformat()
            except OSError:
                rec.touched = ""

    # staleness: commits touching the record's named files after `updated:`
    if (root / ".git").exists():
        for rec in records:
            if rec.findings or not rec.updated or not rec.named_files:
                continue
            existing = [f for f in sorted(rec.named_files)[:20]
                        if (root / f).exists()]
            if not existing:
                continue
            ev = git(["log", "--oneline", f"--since={rec.updated} 23:59",
                      "--", *existing], root)
            if ev:
                n = len(ev.splitlines())
                rec.stale_activity = (f"{n} commit(s) touched files this record "
                                      f"names after its last update — statuses "
                                      f"may lag the repo")
    return records


def render(root: Path, records, adrs, page_dir: Path):
    sha = git(["rev-parse", "--short", "HEAD"], root) or "no-git"
    for r in records:
        r.href = os.path.relpath(root / r.rel, page_dir)
    now = datetime.datetime.now().astimezone().isoformat(timespec="minutes")
    name = root.resolve().name
    flagged = [r for r in records if r.findings]
    clean = [r for r in records if not r.findings]
    open_recs = sorted([r for r in clean if r.is_open and not r.freeform],
                       key=lambda r: r.updated, reverse=True)
    other = [r for r in clean if not r.freeform and not r.is_open
             and not r.is_terminal and not r.is_parked]
    parked = sorted([r for r in clean if r.is_parked and not r.freeform],
                    key=lambda r: r.updated, reverse=True)
    done_all = sorted([r for r in clean if r.is_terminal and not r.freeform],
                      key=lambda r: r.updated, reverse=True)
    done = done_all[:8]
    freeform = [r for r in clean if r.freeform]

    L = []
    L.append(f"# HANDOFF — {name}")
    L.append("")
    L.append(f"> Derived orientation page, generated at commit `{sha}` on {now} "
             f"by perdure `scripts/handoff.py`. **Every status below is a claim "
             f"about that moment, not now**: if `HEAD` has moved, regenerate "
             f"before trusting this page. It is built only from records that "
             f"pass the record-rot lint; records with contradictions are listed "
             f"under *Needs reconciliation* and contribute no state claims "
             f"(ADR sections are parsed from ADR status lines, not linted). "
             f"External systems (experiments, deployments, tickets) are never "
             f"checked here. The records under `perdure/` are the source of "
             f"truth — this page is regenerated, never edited.")
    L.append("")

    L.append("## In flight")
    L.append("")
    if open_recs:
        for r in open_recs:
            L.append(f"- **{r.goal or '(no goal line)'}**  ")
            nxt = f"next: {r.next_step}" if r.next_step else "next step not recorded"
            L.append(f"  {nxt} · {r.cite()}")
            if r.stale_activity:
                L.append(f"  ⚠ {r.stale_activity}")
    else:
        L.append("- nothing in flight in lint-clean records")
    if parked:
        L.append("")
        L.append("**Parked:**")
        for r in parked:
            L.append(f"- {r.goal or '(no goal line)'} · {r.cite()}")
            if r.stale_activity:
                L.append(f"  ⚠ {r.stale_activity}")
    L.append("")

    if flagged:
        L.append("## Needs reconciliation — state claims withheld")
        L.append("")
        L.append("These records contradict themselves or git; fix them per the "
                 "convention's *Correcting a record* rules, then regenerate. "
                 "Nothing from them is summarized here — a contradicted record "
                 "misleads with the summary's authority.")
        L.append("")
        for r in flagged:
            kinds = ", ".join(sorted({f[0] for f in r.findings}))
            L.append(f"- [`{r.rel}`]({r.href}) — {len(r.findings)} finding(s): {kinds}")
        L.append("")

    if freeform:
        L.append("## Unstructured records (lint-clean) — statuses quoted, not derived")
        L.append("")
        L.append("These records predate the frontmatter convention. Each line "
                 "quotes the record's own status bullet verbatim (capped), "
                 "as of the record's last repo touch — read the record before "
                 "acting on it.")
        L.append("")
        for r in sorted(freeform, key=lambda x: x.touched, reverse=True):
            L.append(f"- **{r.goal or r.rel.name}** · [`{r.rel}`]({r.href})")
            if r.status_bullet:
                asof = f" (as of {r.touched})" if r.touched else ""
                L.append(f"  its own status line{asof}: “{r.status_bullet}”")
            else:
                L.append("  no status line found — this page asserts nothing "
                         "about its state")
            if r.stale_activity:
                L.append(f"  ⚠ {r.stale_activity}")
        L.append("")

    if other:
        L.append("## Records with unrecognized statuses — quoted, not classified")
        L.append("")
        for r in sorted(other, key=lambda x: x.touched, reverse=True):
            L.append(f"- **{r.goal or r.rel.name}** · [`{r.rel}`]({r.href})")
            L.append(f"  frontmatter status (outside the convention's vocabulary, "
                     f"as of {r.touched or 'unknown'}): “{excerpt(r.status, 120)}”")
            if r.stale_activity:
                L.append(f"  ⚠ {r.stale_activity}")
        L.append("")

    L.append("## Recently completed")
    L.append("")
    if done:
        for r in done:
            # the FULL status token: split()[0] once stripped a diligent
            # "completed (ROLLED BACK ...)" down to "completed" (review
            # 2026-08-26) — the page must never manufacture a claim the
            # record qualifies
            L.append(f"- {r.goal or '(no goal line)'} · "
                     f"{excerpt(r.status, 120) if r.status else 'terminal'} · {r.cite()}")
            if r.stale_activity:
                L.append(f"  ⚠ {r.stale_activity}")
        if len(done_all) > len(done):
            L.append(f"- … plus {len(done_all) - len(done)} older completed "
                     f"record(s) — see `perdure/workflows/`")
    else:
        L.append("- none recorded")
    L.append("")

    def adr_href(rel):
        return os.path.relpath(root / rel, page_dir)

    active_adrs = [a for a in adrs if a[2] in ("accepted", "proposed")]
    dead_adrs = [a for a in adrs if a[2] == "dead"]
    unknown_adrs = [a for a in adrs if a[2] == "unknown"]
    L.append("## Decisions in force (ADRs)")
    L.append("")
    if not active_adrs and not unknown_adrs:
        L.append("- none")
    if active_adrs:
        shown = active_adrs[-12:]
        for aid, title, _, raw, date, rel in shown:
            L.append(f"- ADR-{aid}: {title} · {excerpt(raw, 80) or 'accepted'}"
                     f" {date} · [`{rel}`]({adr_href(rel)})")
        if len(active_adrs) > len(shown):
            L.append(f"- … plus {len(active_adrs) - len(shown)} older accepted "
                     f"ADR(s) still in force — see `perdure/decisions/`")
    if unknown_adrs:
        for aid, title, _, raw, date, rel in unknown_adrs:
            L.append(f"- ADR-{aid}: {title} · **status unparseable** — read "
                     f"[`{rel}`]({adr_href(rel)}); this page asserts nothing about it")
    L.append("")
    L.append("## Rejected / superseded paths — do not re-litigate blind")
    L.append("")
    if dead_adrs:
        for aid, title, _, raw, date, rel in dead_adrs:
            L.append(f"- ADR-{aid}: {title} · {excerpt(raw, 80)} {date} · "
                     f"[`{rel}`]({adr_href(rel)})")
    else:
        L.append("- no rejected or superseded ADRs; rejected *approaches* live in "
                  "each workflow record's `# Decisions` section — read the record "
                  "before re-proposing something")
    L.append("")
    L.append("---")
    L.append(f"*Regenerate with `/perdure:handoff` (or "
             f"`python3 \"$CLAUDE_PLUGIN_ROOT/scripts/handoff.py\" .`). "
             f"Point-in-time page; the lint gate covers "
             f"deterministic contradictions only — it does not prove records "
             f"true, and it never checks external systems.*")
    L.append("")
    return "\n".join(L)


def main():
    # Non-ASCII in the --check verdict: stdout defaults to the LOCALE encoding
    # with errors='strict', and in regenerate_handoff() a crash here is
    # indistinguishable from "stale" (review 2026-08-31).
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--output")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the committed page differs from what the "
                         "generator would produce now (stale OR hand-tampered)")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    out = Path(args.output) if args.output else root / "perdure" / "HANDOFF.md"

    if args.check:
        # INTEGRITY check by regeneration, not by trusting the page's own git
        # stamp: regenerate the page from the current records into a buffer and
        # compare against the committed file, ignoring only the volatile stamp
        # line (sha + timestamp, which always differ). This catches BOTH a
        # stale page (records changed) AND a hand-written/tampered page that
        # copied a real sha (red-team 2026-08-30: such a page passed the old
        # stamp-only check) — and it needs no git at all, so it also stops the
        # shallow-clone false-stale (the stamp commit may be outside fetched
        # history). Records are the source of truth; the page must match them.
        if not out.exists():
            print(f"stale: {out} does not exist")
            sys.exit(1)
        wdir = root / "perdure" / "workflows"
        if not wdir.is_dir():
            print(f"no records root at {wdir}", file=sys.stderr)
            sys.exit(1)
        fresh = render(root, build(root), collect_adrs(root), out.parent.resolve())

        def normalize(text):
            # Drop the volatile fragments so an authentic page regenerated at
            # a different moment/commit still compares equal — and ONLY those:
            # each is constrained to its real alphabet, or an attacker could
            # smuggle an arbitrary token where the timestamp belongs and have
            # the normalizer erase it (review 2026-08-30).
            text = re.sub(
                r"generated at commit `(?:[0-9a-f]{7,40}|no-git)` on [0-9T:+.\-]+",
                "generated at commit `<sha>` on <t>", text)
            # ⚠ staleness annotations are advisory, recomputed per generation,
            # and their commit counts move with code-only commits touching
            # record-named files — content drift they flag is not RECORD
            # drift. Forgive ONLY the generator's exact template (the count is
            # the sole variable): a free-text rewrite of an existing ⚠ line is
            # a hand edit and must fail the compare (review 2026-08-30).
            return re.sub(r"^(\s*)⚠ \d+ commit\(s\) touched files this "
                          r"record names after its last update — statuses "
                          r"may lag the repo$",
                          r"\1⚠ <staleness annotation>", text, flags=re.M)

        if normalize(out.read_text(encoding="utf-8", errors="replace")).strip() == normalize(fresh).strip():
            print("fresh: committed page matches the current records")
            sys.exit(0)
        print("stale: the committed page does NOT match what the generator "
              "produces from the current records — records changed since it was "
              "written, or the page was hand-edited. Regenerate.")
        sys.exit(1)

    wdir = root / "perdure" / "workflows"
    if not wdir.is_dir():
        print(f"no records root at {wdir}", file=sys.stderr)
        sys.exit(1)
    records = build(root)
    page = render(root, records, collect_adrs(root), out.parent.resolve())
    out.parent.mkdir(parents=True, exist_ok=True)
    # atomic replace: parallel closes can regenerate concurrently (the hook
    # path), and a truncate-then-write window would let a concurrent --check
    # read a torn page (review 2026-08-31)
    tmp = out.with_name(f"{out.name}.{os.getpid()}.tmp")
    tmp.write_text(page, encoding="utf-8")
    os.replace(tmp, out)
    flagged = sum(1 for r in records if r.findings)
    print(f"{out} written: {len(records)} record(s), {flagged} withheld for "
          f"reconciliation")
    sys.exit(0)


if __name__ == "__main__":
    main()
