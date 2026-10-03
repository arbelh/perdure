"""_paths.py — the ONE definition of where a project's files are.

Every consumer that turns a path into a transcript-folder name, a project
root, a git top or an archive root imports from here (rot-lint, handoff,
raw-index, export-session, and both hooks). Each of these was once computed
in two places, and the copies drifted:

  - the transcript-folder slug: the scripts moved to Claude Code's rule
    (every character outside [A-Za-z0-9] becomes "-") while the pre-compact
    hook kept replacing "/" only, so its fallback looked for a folder that
    does not exist for any path holding "_" or "." (4.3.0);
  - the base for paths a record names: rot-lint resolved them against the
    first .git above the record, handoff against the project root it was
    given, and handoff gated its git use on .git sitting AT that root — so a
    project inside a repo subfolder got two answers about one record (4.3.0).

Definitions:
  project root  the folder holding the record's perdure/ — the parent of the
                OUTERMOST perdure/workflows segment of the record's path
                (lexical, never symlink-resolved: macOS /tmp must not re-home a
                record), the rule the close-gate hook always used
  git top       the nearest folder at or above a start folder holding .git
                (a FILE in a worktree or a submodule, a directory otherwise),
                else what `git rev-parse --show-toplevel` answers there
  archive root  where a session's archive lands for a working folder: the
                nearest folder at or above it holding perdure/, never crossing
                a folder that holds .git; else the folder holding .git (the
                repo top); else the working folder itself — and None for the
                home folder when it holds no perdure/
  project root  (of a folder) the nearest folder at or above it holding
                perdure/, looking no further than the first folder that holds
                .git or the home folder; None when there is none (4.3.0:
                next-adr-id.py run from a subfolder numbered from nothing)

When the project root IS the git top (the usual case) every consumer gets the
same answers it got before this module existed.

Known gap, until one folder-finder serves every consumer: archive_root's walk,
unlike project_root's, does not stop at the home folder. Both reach a
~/perdure folder from a folder under home that holds no perdure/ and no .git
of its own: a session in ~/Documents/budget that has no record there yet
archives into ~/perdure, while the start skill opens its record in
~/Documents/budget/perdure/.
"""
from __future__ import annotations

import functools
import os
import re
import subprocess
from pathlib import Path


def project_slug(cwd) -> str:
    """Claude Code's transcript-folder name for a working folder.

    /Users/you/Dev/my_project.v2 -> -Users-you-Dev-my-project-v2

    Every character outside [A-Za-z0-9] becomes "-", not only "/": measured
    over 72 transcript folders (2026-09-15), `_` and `.` included.
    """
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def has_git(folder: Path) -> bool:
    """True when the folder holds .git — `.exists()`, not `.is_dir()`: in a git
    worktree or a submodule `.git` is a FILE (the 3.9.1 lesson)."""
    try:
        return (Path(folder) / ".git").exists()
    except (OSError, ValueError):
        return False


def records_root_of(path) -> Path | None:
    """The project root of a record: the parent of the OUTERMOST perdure/workflows
    segment of its path, or None when the path has no such segment.

    Outermost, matching the close-gate hook's path gate: a pathological path
    holding the segment twice must resolve to the same project every consumer
    keys on (review 2026-08-31). Lexical: the path is made absolute without
    resolving symlinks.
    """
    parts = Path(os.path.abspath(str(path))).parts
    # parts[0] is the anchor ("/"), so i >= 1; the record itself must sit
    # below the workflows segment, hence len - 2
    for i in range(1, len(parts) - 2):
        if parts[i] == "perdure" and parts[i + 1] == "workflows":
            return Path(*parts[:i])
    return None


@functools.lru_cache(maxsize=256)
def _git_top(start: str) -> str:
    d = Path(start)
    cur = d
    while True:
        if has_git(cur):
            return str(cur)
        if cur.parent == cur:
            break
        cur = cur.parent
    try:
        r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(d),
                           capture_output=True, text=True, timeout=20)
        top = r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        top = ""
    return top


def git_top(start) -> Path | None:
    """The git top for a folder (or a file's folder), or None outside git.

    Walks up for .git (file or dir) first — no subprocess in the common case —
    then asks `git rev-parse --show-toplevel` from the start folder, which also
    answers when the repository is located another way (GIT_DIR, a gitdir
    file higher up than the walk can see)."""
    d = Path(os.path.abspath(str(start)))
    try:
        if not d.is_dir():
            d = d.parent
    except OSError:
        d = d.parent
    top = _git_top(str(d))
    return Path(top) if top else None


def _same_folder(a, b) -> bool:
    try:
        return os.path.realpath(str(a)) == os.path.realpath(str(b))
    except OSError:
        return str(a) == str(b)


def project_root(start, home=None) -> Path | None:
    """The project root for a folder: the nearest folder at or above `start`
    holding perdure/ (a directory), or None.

    The walk is lexical (a symlinked folder is not resolved away) and stops
    after the first folder that holds .git — a project never takes its records
    from outside its repository — and after the home folder, never above it.
    None means no project: the caller says so rather than guess one."""
    cur = Path(os.path.abspath(str(start)))
    home = Path(home) if home is not None else Path.home()
    while True:
        try:
            if (cur / "perdure").is_dir():
                return cur
        except OSError:
            pass
        if has_git(cur) or _same_folder(cur, home) or cur.parent == cur:
            return None
        cur = cur.parent


def archive_root(cwd, home=None) -> Path | None:
    """Where an archive for a session working in `cwd` belongs, or None to skip.

    The nearest folder at or above `cwd` holding perdure/, never crossing a
    folder that holds .git (the repo top is the last folder looked at); else
    the folder holding .git; else `cwd` itself. A session started in a
    subfolder therefore archives into the project root, and no stray perdure/
    appears in the subfolder. The home folder is never made a project: when
    the answer would be home and home holds no perdure/, None.
    """
    start = Path(os.path.abspath(str(cwd)))
    found = None
    cur = start
    while True:
        try:
            if (cur / "perdure").is_dir() or has_git(cur):
                found = cur
                break
        except OSError:
            pass
        if cur.parent == cur:
            break
        cur = cur.parent
    root = found or start
    home = Path(home) if home is not None else Path.home()
    try:
        is_home = os.path.realpath(str(root)) == os.path.realpath(str(home))
    except OSError:
        is_home = str(root) == str(home)
    if is_home and not (root / "perdure").is_dir():
        return None
    return root
