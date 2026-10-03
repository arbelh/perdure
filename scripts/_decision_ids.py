"""_decision_ids.py — the ONE reading of a decision record's id.

Every consumer that numbers decisions or compares their ids (next-adr-id.py,
rot-lint's duplicate-id check) imports from here. The decide skill numbered
ADRs with `grep -oE '[0-9]{3}'` over `YYYY-MM-DD-NNN-slug.md` names, so the
year's "202" won and the next id came out 203; an empty folder gave nothing;
and only the checked-out branch was looked at, so two branches that each
added a decision took the same number, and nothing flagged the pair (4.3.0).

An id is read in exactly these places:
  the file NAME, at the id position only, exactly three digits
      YYYY-MM-DD-NNN-slug.md            the decide skill's shape
      NNN-slug.md · ADR-NNN-slug.md     id-first shapes
  the file's own TEXT, in the two forms handoff.py renders
      an `id:` key inside the frontmatter fence
      an `# ADR-NNN` H1 heading — only the FIRST H1 after the frontmatter,
      outside code fences: the title, never an example or a later mention
Digits anywhere else in a name (the date, a number in the slug) are never an
id. A name that starts with a date and has no three-digit id after it carries
none. These rules are strict on purpose (4.3.0): `1-pager.md` read as 1,
`2026-09-04-3-tier-architecture.md` as 3, a fenced `# ADR-003` example and a
mid-file `# ADR-5 was superseded` line as ids, and each false reading could
fail rot-lint --strict as a duplicate. A file whose id this module cannot read
is reported as not compared, never guessed at: rot-lint's `decision ids:` line
names it, and next-adr-id.py counts it in a note on stderr.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
from pathlib import Path

# shared project paths: the git top the branch listing runs from
_pa_spec = importlib.util.spec_from_file_location(
    "_paths", Path(__file__).resolve().parent / "_paths.py")
_pa = importlib.util.module_from_spec(_pa_spec)
_pa_spec.loader.exec_module(_pa)

DECISIONS_REL = Path("perdure") / "decisions"

# exactly three digits, then "-": the id position of each shape and nothing else
_DATED = re.compile(r"\A\d{4}-\d{2}-\d{2}(?:-(\d{3})-)?")
_ID_FIRST = re.compile(r"\A(?:ADR[-_]?)?(\d{3})-", re.I)
_FM_ID = re.compile(r"""\Aid:[ \t]*["']?(\d+)["']?[ \t]*\Z""")
# an ATX H1 (up to three spaces of indent), and the ADR id it may carry
_H1 = re.compile(r" {0,3}#(?:[ \t]|\Z)")
_H1_ADR = re.compile(r" {0,3}#[ \t]+ADR-(\d+)\b", re.I)
# a code fence opener or closer: three or more backticks or tildes
_FENCE = re.compile(r" {0,3}(`{3,}|~{3,})")


def name_id(name: str) -> int | None:
    """The id a decision file's NAME carries at the id position, else None."""
    m = _DATED.match(name)
    if m:
        # a dated name carries an id only right after the date
        return int(m.group(1)) if m.group(1) else None
    m = _ID_FIRST.match(name)
    return int(m.group(1)) if m else None


def first_h1(lines) -> str | None:
    """The first ATX H1 line outside code fences, or None. A fence closes on
    the same character, at least as long as its opener, with nothing after."""
    fence = None                         # (character, length) while inside one
    for line in lines:
        m = _FENCE.match(line)
        if fence is not None:
            if (m and m.group(1)[0] == fence[0] and len(m.group(1)) >= fence[1]
                    and not line[m.end():].strip()):
                fence = None
            continue
        # a backtick fence's info string holds no backtick (CommonMark)
        if m and not (m.group(1)[0] == "`" and "`" in line[m.end():]):
            fence = (m.group(1)[0], len(m.group(1)))
            continue
        if _H1.match(line):
            return line
    return None


def text_ids(text: str) -> set[int]:
    """Ids the file's own text claims: the frontmatter `id:`, and an ADR id in
    the first H1 after the frontmatter (outside code fences) — the title."""
    ids: set[int] = set()
    if text.startswith("\ufeff"):
        text = text[1:]
    lines = text.splitlines()
    body = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:80], start=1):
            if line.strip() == "---":
                body = i + 1
                break
            m = _FM_ID.match(line.rstrip())
            if m and not ids:
                ids.add(int(m.group(1)))
    h1 = first_h1(lines[body:])
    m = _H1_ADR.match(h1) if h1 is not None else None
    if m:
        ids.add(int(m.group(1)))
    return ids


def decision_files(root: Path) -> list[Path]:
    """The decision files in the working tree: perdure/decisions/*.md, INDEX.md
    excluded, sorted by name."""
    d = Path(root) / DECISIONS_REL
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.md") if p.name != "INDEX.md" and p.is_file())


def claimed_ids(path: Path) -> set[int]:
    """Every id one working-tree decision file claims, by name and by text."""
    ids = set()
    n = name_id(path.name)
    if n is not None:
        ids.add(n)
    try:
        ids |= text_ids(path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        pass
    return ids


def duplicates(root: Path):
    """(dups, unread, n_files): dups is a sorted list of (id, [files]) where two
    or more working-tree decision files claim one id; unread lists the files
    that claim no id this module can read (they were not compared)."""
    by_id: dict[int, list[Path]] = {}
    unread: list[Path] = []
    files = decision_files(root)
    for p in files:
        ids = claimed_ids(p)
        if not ids:
            unread.append(p)
        for i in ids:
            by_id.setdefault(i, []).append(p)
    dups = [(i, ps) for i, ps in sorted(by_id.items()) if len(ps) > 1]
    return dups, unread, len(files)


def _git(args, top: Path):
    """(stdout, None) when git succeeds in `top`, else (None, why) — one line."""
    try:
        r = subprocess.run(["git", "-C", str(top), *args], capture_output=True,
                           text=True, timeout=20)
    except FileNotFoundError:
        return None, "git is not installed"
    except Exception as e:
        return None, f"git did not run: {type(e).__name__}"
    if r.returncode != 0:
        err = (r.stderr or "").strip().splitlines()
        return None, (err[0].strip() if err else f"git exited {r.returncode}")
    return r.stdout, None


def _unchecked(why: str) -> str:
    return (f"other branches were not checked ({why}); the id comes from the "
            "working tree only")


def branch_names(root: Path):
    """(names, note): decision file names on every local and remote-tracking
    branch, and None when every branch was listed — else a one-line note
    saying what was not (no git, not a repository, a tip git could not read).

    `git for-each-ref` lists the branch tips; `git -C <top> ls-tree
    --name-only <tip> -- <decisions folder relative to top>` lists each tip's
    perdure/decisions/. Git runs from the git top with a top-relative path, so
    the answer does not depend on the folder the script was started in (it did:
    pathspecs are relative to the current folder, and a run from a subfolder
    listed nothing, 4.3.0). Tips are deduplicated by commit, and an id that
    exists only on another branch still counts."""
    top = _pa.git_top(root)
    if top is None:
        if shutil.which("git") is None:
            return set(), _unchecked("git is not installed")
        return set(), _unchecked(f"{root} is not inside a git repository")
    try:
        top_real = os.path.realpath(str(top))
        rel = os.path.relpath(os.path.realpath(str(root)), top_real)
    except (OSError, ValueError):
        return set(), _unchecked(f"{root} could not be placed inside its repository")
    if rel == os.pardir or rel.startswith(os.pardir + os.sep):
        return set(), _unchecked(f"{root} lies outside the repository git reports, {top}")
    rel_dir = DECISIONS_REL.as_posix() if rel == os.curdir else \
        f"{Path(rel).as_posix()}/{DECISIONS_REL.as_posix()}"
    refs, why = _git(["for-each-ref", "--format=%(objectname)", "refs/heads",
                      "refs/remotes"], top_real)
    if why:
        return set(), _unchecked(why)
    names: set[str] = set()
    failed: list[str] = []
    for sha in sorted(set(refs.split())):
        if not re.fullmatch(r"[0-9a-f]{7,64}", sha):
            continue
        out, why = _git(["ls-tree", "--name-only", sha, "--", f"{rel_dir}/"], top_real)
        if why:
            failed.append(why)
            continue
        for line in out.splitlines():
            name = line.strip().rsplit("/", 1)[-1]
            if name.endswith(".md") and name != "INDEX.md":
                names.add(name)
    if failed:
        return names, (f"{len(failed)} branch tip(s) could not be listed ({failed[0]}); "
                       "a decision only they hold is not counted")
    return names, None


def highest_id(root: Path):
    """(id, note): the highest id any decision carries, in the working tree
    (name and text) or by name on any branch, 0 when there are none; and
    branch_names' note — None when every branch was looked at."""
    ids = set()
    for p in decision_files(root):
        ids |= claimed_ids(p)
    names, note = branch_names(root)
    for name in names:
        n = name_id(name)
        if n is not None:
            ids.add(n)
    return max(ids, default=0), note


def next_id(root: Path):
    """(id, note): the next free id, zero-padded to three digits ("001" when
    there are none), and why other branches were not checked (None if they were)."""
    top, note = highest_id(root)
    return f"{top + 1:03d}", note
