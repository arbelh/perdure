#!/usr/bin/env python3
"""next-adr-id.py — print the next free decision (ADR) id for a project.

The decide skill used to number decisions with
`ls perdure/decisions/*.md | grep -oE '[0-9]{3}' | sort -n | tail -1`, which
reads the year's "202" out of `YYYY-MM-DD-NNN-slug.md` names (the next id came
out 203), fails on an empty folder, and sees the checked-out branch only — so
two branches that each add a decision take the same number (4.3.0).

The project is the nearest folder at or above --root holding perdure/,
looking no further than the repository top or the home folder (4.3.0: a run
from a subfolder printed 001 where the project root gave 014). This prints one
more than the highest id found:
  - in the project's perdure/decisions/ (INDEX.md excluded), from each file's
    name at the id position and from its `id:` frontmatter or `# ADR-NNN`
    title heading;
  - on every local and remote-tracking branch, from the names in that
    branch's perdure/decisions/ (`git for-each-ref` + `git ls-tree`, run from
    the git top). An id that exists only on another branch still counts. When
    the branches cannot be listed (no git, not a repository), a one-line note
    on stderr says so and the id comes from the working tree alone.
"001" when there are none. Ids are zero-padded to three digits; stdout holds
the id and nothing else. A working-tree decision file with no id this tool
can read is not counted, and a one-line note on stderr names it (ADR-008). Reading only: nothing is written. The id rules live
in scripts/_decision_ids.py, which rot-lint's duplicate-id check shares.

Usage: next-adr-id.py [--root DIR]

Exit codes: 0 printed · 2 the root is not a directory, or no perdure/ folder
            at or above it
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_di_spec = importlib.util.spec_from_file_location(
    "_decision_ids", Path(__file__).resolve().parent / "_decision_ids.py")
di = importlib.util.module_from_spec(_di_spec)
_di_spec.loader.exec_module(di)
_pa_spec = importlib.util.spec_from_file_location(
    "_paths", Path(__file__).resolve().parent / "_paths.py")
pa = importlib.util.module_from_spec(_pa_spec)
_pa_spec.loader.exec_module(pa)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print the next free 3-digit decision id: one more than the "
                    "highest id in the working tree's perdure/decisions/ or on "
                    "any local or remote-tracking branch (001 when there are none).")
    ap.add_argument("--root", default=".",
                    help="a folder inside the project; the nearest folder at or "
                         "above it holding perdure/ is the project (default: .)")
    args = ap.parse_args()
    start = Path(args.root)
    if not start.is_dir():
        print(f"next-adr-id.py: not a directory: {start}", file=sys.stderr)
        return 2
    root = pa.project_root(start)
    if root is None:
        print(f"next-adr-id.py: no perdure/ folder at or above {start.resolve()} "
              "(looked up to the repository top or the home folder). Run it from "
              "inside a project, or create perdure/decisions/ first: a project's "
              "first decision is 001.", file=sys.stderr)
        return 2
    nid, note = di.next_id(root.resolve())
    if note:
        print(f"note: {note}", file=sys.stderr)
    # ADR-008: say what was not counted. A file whose id cannot be read is left
    # out of the maximum, never guessed at.
    unread = [p.name for p in di.decision_files(root.resolve()) if not di.claimed_ids(p)]
    if unread:
        named = ", ".join(unread[:3]) + (f" and {len(unread) - 3} more" if len(unread) > 3 else "")
        print(f"note: {len(unread)} decision file(s) carry no id this tool can read, "
              f"so they were not counted: {named}", file=sys.stderr)
    print(nid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
