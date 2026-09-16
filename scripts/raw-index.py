#!/usr/bin/env python3
"""raw-index.py — Tier R: a committed reference index of the raw layer.

The problem this solves, measured (2026-08-31 full-lifecycle dry run): a
five-unit project arc produced FOUR workflow records, and nothing in the system
could tell. perdure knows only about records someone chose to write, so a
missing record is invisible from the inside. Audit sampling — and any honest
claim about coverage — starts from a POPULATION, and there was none.

Tier R is that population. One line per session in perdure/raw/INDEX.jsonl:
identifiers, timestamps, counts and content digests. No transcript text.

Three properties, in priority order:

  1. SAFE BY CONSTRUCTION — the index carries ids, counts, hashes, timestamps
     and low-cardinality labels (branch, tool version, entrypoint). It never
     carries transcript text, file paths, or prose. That is why it can be
     committed while the payloads it points at cannot; safety is a property of
     the schema rather than of a scan that might miss something.
  2. ADDRESSABLE AFTER THE PAYLOAD IS GONE — every entry keeps its digest, so a
     record can cite a session and that citation stays checkable even once
     Claude Code has pruned the transcript. A pruned session keeps its entry
     and is marked `status: "pruned"`; an honest gap is a record, silence is not.
  3. MERGE, NEVER TRUNCATE — re-running is idempotent and additive. Entries are
     never dropped. Git supplies the history of the index itself, so the file
     stays one line per session rather than an append log that grows forever.

Deliberately NOT here: transcript payloads (that is Tier A, unbuilt and
unapproved), and any judgement about whether a session should have produced a
record (that is a consumer of this file, not this file).

Usage:
  raw-index.py [--root DIR]        sweep and update perdure/raw/INDEX.jsonl
  raw-index.py --verify [--root D] re-derive and compare; exit 1 on mismatch
  raw-index.py --summary           print the population, write nothing

Exit codes: 0 ok · 1 verify mismatch · 2 usage/no transcript store
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCHEMA = 1
# A session id becomes a directory name and an index key. A file literally
# named "...jsonl" yields the stem "..", which would walk the scan out of the
# store entirely (review 2026-09-02).
_SESSION_OK = re.compile(r"\A(?!\.+\Z)[\w.-]{1,128}\Z")
PROJECTS_ROOT = Path.home() / ".claude" / "projects"
INDEX_REL = Path("perdure") / "raw" / "INDEX.jsonl"

# Blocks we count. Anything else present is counted under "other" rather than
# dropped silently — an unrecognised block type is information, not noise.
KNOWN_KINDS = ("text", "thinking", "tool_use", "tool_result", "image")

# A digest is over file BYTES, so it is stable regardless of how this script
# evolves. Chunked so a 95 MB transcript does not land in memory.
_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with path.open("rb") as f:
            while True:
                b = f.read(_CHUNK)
                if not b:
                    break
                h.update(b)
    except OSError:
        return ""
    return "sha256:" + h.hexdigest()


def project_slug(cwd: Path) -> str:
    """Claude Code's transcript-directory name for a cwd: every character
    outside [A-Za-z0-9] becomes "-" (measured over 72 directories, 2026-09-15;
    `_` and `.` included). Replacing only "/" missed any path holding either
    and reported "no transcript store" for a store that existed."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


def belongs_to_project(transcript: Path, root_real: str) -> bool:
    """True unless the transcript demonstrably belongs to a DIFFERENT project.

    Slugs replace "/" with "-", so /a/b-c and /a-b/c collide, and without a
    check project A's sessions landed in project B's committed index. But the
    first version of this check demanded an exact match against three strings,
    and real transcripts do not honour that: sampled across 117 real
    cwd-bearing transcripts, 4 record several cwds (a project and its
    subdirectories) and 18 record a cwd that never re-slugs to their own store.
    Those were silently dropped from the population — the precise gap this
    index exists to close (review 2026-09-02).

    So: accept the project root or ANY DESCENDANT of it, consider every cwd
    record rather than the first, and accept when no cwd is recorded at all.
    Only an unambiguous mismatch — every observed cwd outside the project —
    excludes a session.
    """
    seen_any = False
    try:
        with transcript.open("r", encoding="utf-8", errors="replace") as f:
            for i, line in enumerate(f):
                if i > 400:
                    break
                if '"cwd"' not in line:
                    continue
                try:
                    d = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                cwd = d.get("cwd") if isinstance(d, dict) else None
                if not isinstance(cwd, str) or not cwd:
                    continue
                seen_any = True
                try:
                    real = os.path.realpath(cwd)
                except OSError:
                    real = cwd
                if real == root_real or real.startswith(root_real.rstrip(os.sep) + os.sep):
                    return True
    except OSError:
        return True
    return not seen_any


def store_for(root: Path) -> Path | None:
    """Locate Claude Code's transcript directory for this project.

    Tries the path as given AND its physical resolution: the slug is built from
    whatever string the tool was launched with, and on macOS `resolve()` turns
    /var into /private/var (and any symlinked home or worktree likewise), which
    silently points at a store that does not exist. Returns None when neither
    candidate is present, so the caller can say so rather than index nothing.
    """
    seen = []
    for cand in (root, Path(os.path.abspath(root)), root.resolve()):
        slug = project_slug(cand)
        # A relative path slugs to something degenerate — "." slugs to ".", and
        # PROJECTS_ROOT / "." IS PROJECTS_ROOT, which exists. That returned the
        # projects root itself, globbed zero sessions, and marked every live
        # session pruned (caught on the maintainer's own repo, 2026-09-02).
        if not slug or set(slug) <= {".", "-"}:
            continue
        d = PROJECTS_ROOT / slug
        if d in seen:
            continue
        seen.append(d)
        if d.is_dir() and d.resolve() != PROJECTS_ROOT.resolve():
            return d
    return None


def git(args: list[str], cwd: Path) -> str:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def scan_transcript(path: Path) -> dict:
    """Counts, timestamps and low-cardinality labels. Returns no text."""
    counts: dict[str, int] = {}
    prompts = set()
    branches: set[str] = set()
    versions: set[str] = set()
    entrypoints: set[str] = set()
    models: set[str] = set()
    first_ts = last_ts = ""
    records = 0
    compactions = 0
    api_errors = 0

    try:
        fh = path.open("r", encoding="utf-8", errors="replace")
    except OSError as exc:
        # a directory, a broken symlink, or a mode-000 file must cost one
        # session, not the whole sweep (review 2026-09-02)
        return {"unreadable": type(exc).__name__}
    with fh as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                counts["unparseable"] = counts.get("unparseable", 0) + 1
                continue
            if not isinstance(d, dict):
                continue
            records += 1
            ts = d.get("timestamp")
            if isinstance(ts, str) and ts:
                if not first_ts:
                    first_ts = ts
                last_ts = ts
            for key, bucket in (("gitBranch", branches), ("version", versions),
                                ("entrypoint", entrypoints)):
                v = d.get(key)
                if isinstance(v, str) and v:
                    bucket.add(v)
            pid = d.get("promptId")
            if isinstance(pid, str) and pid:
                prompts.add(pid)
            if d.get("isCompactSummary") or d.get("compactMetadata"):
                compactions += 1
            if d.get("isApiErrorMessage"):
                api_errors += 1
            msg = d.get("message")
            if isinstance(msg, dict):
                mdl = msg.get("model")
                if isinstance(mdl, str) and mdl:
                    models.add(mdl)
                content = msg.get("content")
                if isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        t = b.get("type")
                        k = t if t in KNOWN_KINDS else "other"
                        counts[k] = counts.get(k, 0) + 1
    return {
        "first_ts": first_ts,
        "last_ts": last_ts,
        "records": records,
        "prompts": len(prompts),
        "counts": dict(sorted(counts.items())),
        "branches": sorted(branches),
        "tool_versions": sorted(versions),
        "entrypoints": sorted(entrypoints),
        "models": sorted(models),
        "compactions": compactions,
        "api_errors": api_errors,
    }


def scan_agents(session_dir: Path) -> dict:
    """Subagent tree shape. Verified reconstructible: every agent file's first
    record carries agentId/parentUuid/promptId/sessionId. We record shape only —
    file count, distinct agent ids, prompts that spawned agents, bytes, and a
    digest over the sorted per-file digests so the set is addressable as a whole.

    RECURSIVE by necessity: workflow-run agents live at
    subagents/workflows/<wf_id>/agent-*.jsonl, not beside the directly-spawned
    ones. A non-recursive glob found 43 of 296 agent files on the maintainer's
    own session — an 85% undercount, and precisely the kind of silent gap this
    index exists to make impossible.
    """
    sub = session_dir / "subagents"
    if not sub.is_dir():
        return {"files": 0, "ids": 0, "spawning_prompts": 0, "bytes": 0,
                "workflow_runs": 0, "digest": ""}
    files = sorted(p for p in sub.rglob("agent-*.jsonl") if p.is_file())
    ids: set[str] = set()
    spawn: set[str] = set()
    total = 0
    per_file = []
    for p in files:
        try:
            total += p.stat().st_size
        except OSError:
            pass
        per_file.append(sha256_file(p))
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                head = f.readline()
            d = json.loads(head) if head.strip() else {}
            if isinstance(d, dict):
                for key, bucket in (("agentId", ids), ("promptId", spawn)):
                    v = d.get(key)
                    if isinstance(v, str) and v:
                        bucket.add(v)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
    runs = sum(1 for d in (sub / "workflows").glob("wf_*") if d.is_dir()) \
        if (sub / "workflows").is_dir() else 0
    roll = hashlib.sha256("\n".join(sorted(per_file)).encode()).hexdigest()
    return {"files": len(files), "ids": len(ids),
            "spawning_prompts": len(spawn), "bytes": total,
            "workflow_runs": runs,
            "digest": ("sha256:" + roll) if files else ""}


def scan_sidecars(session_dir: Path) -> dict:
    """Externalized payloads that belong to the session but sit outside the
    transcript: oversized tool results written to tool-results/, and workflow
    run manifests and scripts under workflows/. Counted and sized only.
    """
    out = {}
    for name in ("tool-results", "workflows"):
        d = session_dir / name
        if not d.is_dir():
            continue
        files = [p for p in d.rglob("*") if p.is_file()]
        total = 0
        for p in files:
            try:
                total += p.stat().st_size
            except OSError:
                pass
        out[name] = {"files": len(files), "bytes": total}
    return out


# The schema is a closed set. Anything not listed here must never be written,
# which is what makes property 1 checkable rather than aspirational.
ALLOWED_KEYS = {
    "v", "session", "status", "first_ts", "last_ts", "records", "prompts",
    "counts", "branches", "tool_versions", "entrypoints", "models",
    "compactions", "api_errors", "bytes", "mtime", "digest", "agents",
    "indexed_at", "indexed_at_sha", "pruned_detected_at", "source_tool",
    "sidecars", "dir_mtime", "unreadable", "last_absent_at",
}
def unknown_keys(e: dict) -> list[str]:
    """Top-level keys this version does not know — reported, never refused."""
    return sorted(k for k in e if k not in ALLOWED_KEYS)


# Values must look like identifiers, not prose. Branch names legitimately
# contain "/" (feature/x), so "/" is permitted — the no-paths property comes
# from FIELD SELECTION plus the absolute-path rejection below, not from this
# class alone. \Z (not $) so a trailing newline cannot sneak through.
_LABEL_OK = re.compile(r"\A[\w.@:/+-]{0,120}\Z")
_LOOKS_LIKE_PATH = re.compile(r"\A(?:/|~|[A-Za-z]:[\\/])")


def sanitize_label(v: str) -> str:
    """Return v if it is a safe identifier, else a stable digest sentinel.

    Fail closed on the VALUE, never on the file. A 125-character branch name is
    legal to git; refusing the whole write over one made a single such branch
    wedge the entire index permanently — no new sessions indexed, no prune
    detection, and no remedy but the hand edit the skill forbids (review
    2026-09-02). Replacing the value keeps every other fact in the entry.
    """
    if not isinstance(v, str):
        return v
    if _LABEL_OK.match(v) and not _LOOKS_LIKE_PATH.match(v):
        return v
    return "opaque:" + hashlib.sha256(v.encode("utf-8", "replace")).hexdigest()[:12]


def sanitize_tree(o):
    """Recursively sanitise every string, in keys and values, at any depth."""
    if isinstance(o, dict):
        return {sanitize_label(str(k)): sanitize_tree(v) for k, v in o.items()}
    if isinstance(o, list):
        return [sanitize_tree(x) for x in o]
    if isinstance(o, str):
        return sanitize_label(o)
    return o


def entry_is_safe(e: dict) -> list[str]:
    """Reasons the entry violates the no-free-text rule. Empty = safe.

    RECURSIVE, at every depth, over keys and values alike. The one-level
    version inspected only the top level and, for a dict, only its keys — so
    prose nested two deep round-tripped through the merge untouched and
    `--verify` then certified the file as carrying no free text (review
    2026-09-02).
    """
    bad = []

    def walk(node, path):
        if isinstance(node, dict):
            for k, v in node.items():
                ks = str(k)
                if not _LABEL_OK.match(ks) or _LOOKS_LIKE_PATH.match(ks):
                    bad.append(f"{path}: key is not an identifier ({len(ks)} chars)")
                walk(v, f"{path}.{ks}" if path else ks)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
        elif isinstance(node, str):
            if not _LABEL_OK.match(node) or _LOOKS_LIKE_PATH.match(node):
                bad.append(f"{path}: value is not an identifier ({len(node)} chars)")

    # Unknown keys are NOT a violation: INDEX.jsonl is committed and shared, so
    # a teammate on a newer plugin version will add fields. Refusing the file
    # over one wedged every older client with no repair path — original finding
    # 2's failure mode moved from values to keys (review 2026-09-02). They are
    # sanitised like everything else, so an unknown key cannot smuggle prose.
    walk(e, "")
    return bad


def build_entry(transcript: Path, session_dir: Path,
                head_sha: str, now: str) -> dict:
    st = transcript.stat()
    e = {
        "v": SCHEMA,
        "session": transcript.stem,
        "status": "present",
        "source_tool": "claude-code",
        "bytes": st.st_size,
        "mtime": int(st.st_mtime),
        "digest": sha256_file(transcript),
        "indexed_at": now,
        "indexed_at_sha": head_sha or "no-git",
    }
    e.update(sanitize_tree(scan_transcript(transcript)))
    e["agents"] = scan_agents(session_dir)
    e["sidecars"] = scan_sidecars(session_dir)
    return e


def read_index(path: Path) -> tuple[dict[str, dict], list[str]]:
    """Parse the index. Returns (entries, unparseable_raw_lines).

    Unparseable lines are RETURNED, not skipped. Dropping them silently erased
    citations permanently while the sweep reported success and `--verify` then
    certified the result (review 2026-09-02) — a partial write or a botched
    merge conflict was enough to lose an entry with no warning anywhere.
    """
    out: dict[str, dict] = {}
    rejects: list[str] = []
    if not path.exists():
        return out, rejects
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            rejects.append(line)
            continue
        if isinstance(d, dict) and isinstance(d.get("session"), str):
            out[d["session"]] = sanitize_tree(d)   # last line wins
        else:
            rejects.append(line)
    return out, rejects


def write_index(path: Path, entries: dict[str, dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        json.dumps(entries[k], sort_keys=True, separators=(",", ":")) + "\n"
        for k in sorted(entries)
    )
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--verify", action="store_true",
                    help="re-derive from the transcript store and compare")
    ap.add_argument("--force", action="store_true",
                    help="re-derive every session, ignoring the size/mtime skip")
    ap.add_argument("--repair", action="store_true",
                    help="quarantine unparseable index lines to .rejected")
    ap.add_argument("--summary", action="store_true",
                    help="print the population; write nothing")
    args = ap.parse_args()

    # store_for must see the path AS GIVEN: resolving first collapsed all three
    # candidates to the physical slug, so the symlink handling was dead code and
    # a symlinked checkout indexed nothing (review 2026-09-02).
    root_given = Path(args.root)
    root = root_given.resolve()
    index_path = root / INDEX_REL
    store = store_for(root_given)

    existing, rejects = read_index(index_path)

    if args.summary and args.verify:
        print("--summary and --verify are mutually exclusive", file=sys.stderr)
        return 2

    if args.summary:
        if store is None:
            print(f"no transcript store for this project under {PROJECTS_ROOT} — "
                  f"the population is UNKNOWN, not zero", file=sys.stderr)
            return 2
        present = [e for e in existing.values() if e.get("status") == "present"]
        pruned = [e for e in existing.values() if e.get("status") == "pruned"]
        agents = sum((e.get("agents") or {}).get("files", 0) for e in existing.values())
        prompts = sum(e.get("prompts", 0) for e in existing.values())
        think = sum((e.get("counts") or {}).get("thinking", 0) for e in existing.values())
        print(f"population: {len(existing)} session(s) — {len(present)} present, "
              f"{len(pruned)} pruned")
        print(f"            {prompts} prompt(s), {agents} subagent transcript(s), "
              f"{think} thinking block(s)")
        if existing:
            ts = sorted(e.get("first_ts", "") for e in existing.values() if e.get("first_ts"))
            if ts:
                print(f"            window {ts[0][:10]} .. "
                      f"{max(e.get('last_ts','') for e in existing.values())[:10]}")
        return 0

    if store is None:
        print(f"no transcript store for this project under {PROJECTS_ROOT} "
              f"(looked for slug {project_slug(root.resolve())!r})", file=sys.stderr)
        return 2

    head = git(["rev-parse", "--short", "HEAD"], root)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")

    seen: dict[str, dict] = {}
    skipped: list[str] = []
    on_disk: set[str] = set()          # every session file present, examined or not
    root_real = os.path.realpath(root)
    for transcript in sorted(store.glob("*.jsonl")):
        sid = transcript.stem
        on_disk.add(sid)
        if not _SESSION_OK.match(sid):
            skipped.append(f"{sid!r}: not a valid session id")
            continue
        if not belongs_to_project(transcript, root_real):
            skipped.append(f"{sid}: every recorded cwd lies outside this project")
            continue
        prev = existing.get(sid)
        try:
            st = transcript.stat()
        except OSError as exc:
            skipped.append(f"{sid}: {type(exc).__name__}")
            continue
        # cheap skip: unchanged size+mtime means the digest cannot have changed
        sdir = store / sid
        try:
            dir_mtime = int(sdir.stat().st_mtime) if sdir.is_dir() else 0
        except OSError:
            dir_mtime = 0
        # the skip must key on the session DIRECTORY too: agent files and
        # sidecars live there, and keying on the transcript alone made a whole
        # deleted subagents/ tree invisible to both sweep and verify
        # (review 2026-09-02)
        if (not args.verify and not args.force and prev
                and prev.get("status") == "present"
                and prev.get("bytes") == st.st_size
                and prev.get("mtime") == int(st.st_mtime)
                and prev.get("dir_mtime") == dir_mtime):
            seen[sid] = prev
            continue
        e = build_entry(transcript, sdir, head, now)
        e["dir_mtime"] = dir_mtime
        # A momentary EACCES/EIO must not overwrite good derived data with a
        # stub and blank the digest — that broke "a citation stays checkable"
        # via a transient error, reported as success (review 2026-09-02).
        if e.get("unreadable") and prev:
            keep = dict(prev)
            keep["unreadable"] = e["unreadable"]
            keep["indexed_at"] = now
            e = keep
        # A session that reappears keeps the FACT that it was once missing, but
        # renamed: "pruned_detected_at" on a present session asserts something
        # untrue. last_absent_at is exactly what was observed and nothing more.
        if prev and prev.get("pruned_detected_at"):
            e["last_absent_at"] = prev["pruned_detected_at"]
        seen[sid] = e

    if args.verify:
        problems = []
        for sid, fresh in seen.items():
            prev = existing.get(sid)
            if not prev:
                problems.append(f"{sid}: present on disk but absent from the index")
                continue
            for field in ("digest", "bytes", "records", "prompts", "counts",
                          "agents", "sidecars", "branches", "tool_versions",
                          "entrypoints", "models", "first_ts", "last_ts",
                          "compactions", "api_errors"):
                if prev.get(field) != fresh.get(field):
                    problems.append(
                        f"{sid}: {field} differs (index {prev.get(field)!r} "
                        f"vs disk {fresh.get(field)!r})")
        for sid, e in existing.items():
            if e.get("status") == "present" and sid not in seen:
                problems.append(f"{sid}: index says present, transcript is gone "
                                f"(sweep to mark it pruned)")
            if e.get("status") == "pruned" and sid in seen:
                problems.append(f"{sid}: index says pruned, but the transcript "
                                f"is present (sweep to resurrect it)")
            for reason in entry_is_safe(e):
                problems.append(f"{sid}: UNSAFE ENTRY — {reason}")
        if problems:
            print("index does NOT match the transcript store:", file=sys.stderr)
            for p in problems[:40]:
                print(f"  {p}", file=sys.stderr)
            return 1
        if not seen:
            if on_disk:
                print("verified NOTHING: transcripts are present but none was "
                      "examined — the index was not checked against anything",
                      file=sys.stderr)
                return 1
            # No transcripts remain locally. If every entry already says so and
            # keeps its digest, the index is exactly right — this is the
            # end-state property 2 exists for, and calling it a mismatch made
            # any project quieter than the retention window report a broken
            # index (review 2026-09-02).
            if existing:
                print(f"verified: no transcripts remain in the local store; "
                      f"all {len(existing)} entry/entries are marked pruned and "
                      f"keep their digests, so citations stay checkable")
                return 0
            print("verified NOTHING: the index is empty and the store holds "
                  "no transcripts", file=sys.stderr)
            return 1
        print(f"verified: {len(seen)} session(s) match the index; "
              f"no entry carries free text")
        return 0

    # merge, never truncate: keep every prior entry, flip vanished ones
    merged = dict(existing)
    added = updated = 0
    for sid, e in seen.items():
        if sid not in merged:
            added += 1
        elif {k: v for k, v in merged[sid].items()
              if k not in ("indexed_at", "indexed_at_sha")} != \
             {k: v for k, v in e.items()
              if k not in ("indexed_at", "indexed_at_sha")}:
            updated += 1
        merged[sid] = e
    pruned_now = 0
    for sid, e in merged.items():
        # ONLY a session whose transcript file is absent is pruned. A session
        # that was skipped is still on disk; calling it pruned writes a
        # falsehood into a committed record (review 2026-09-02).
        if sid not in on_disk and e.get("status") == "present":
            e["status"] = "pruned"
            e["pruned_detected_at"] = now
            pruned_now += 1

    merged = {k: sanitize_tree(v) for k, v in merged.items()}
    unsafe = [(sid, r) for sid, e in merged.items() for r in entry_is_safe(e)]
    if unsafe:
        # sanitize_tree should make this unreachable; if it fires it is a bug in
        # this script, so fail loudly rather than write something unvetted
        print("refusing to write: entry would carry non-identifier content "
              "(this is a bug in raw-index.py, not in your data)", file=sys.stderr)
        for sid, r in unsafe[:20]:
            print(f"  {sid}: {r}", file=sys.stderr)
        return 1

    skew = sorted({k for e in merged.values() for k in unknown_keys(e)})
    if skew:
        print(f"note: {len(skew)} field(s) from a newer index version preserved "
              f"as-is: {', '.join(skew[:8])}", file=sys.stderr)

    if rejects and not args.repair:
        print(f"refusing to write: {len(rejects)} unparseable line(s) in "
              f"{INDEX_REL} would be lost. Re-run with --repair to move them to "
              f"{INDEX_REL}.rejected and continue.", file=sys.stderr)
        return 1
    if rejects and args.repair:
        # Quarantined lines are raw by definition — the whole point is to
        # preserve them verbatim — so they must NOT become a committed file in
        # the records root. Keep them local and ignored (review 2026-09-02).
        rej = index_path.with_name(index_path.name + ".rejected")
        # Reconciled on every repair, never write-once: the write-once version
        # of exactly this pattern silently stopped honouring a privacy
        # preference elsewhere in this plugin. Appended rather than replacing,
        # so a file the user has added to is not clobbered.
        gi = index_path.parent / ".gitignore"
        rule = "*.rejected"
        try:
            current = gi.read_text(encoding="utf-8") if gi.exists() else ""
        except OSError:
            current = ""
        if rule not in current.split():
            body = current
            if body and not body.endswith("\n"):
                body += "\n"
            body += ("# quarantined raw lines — local only, never committed\n"
                     f"{rule}\n")
            try:
                gi.write_text(body, encoding="utf-8")
            except OSError:
                pass
        with rej.open("a", encoding="utf-8") as f:
            for line in rejects:
                f.write(line + "\n")
        print(f"moved {len(rejects)} unparseable line(s) to {rej.name} "
              f"(gitignored; inspect and delete when resolved)")

    write_index(index_path, merged)
    msg = (f"{index_path.relative_to(root)}: {len(merged)} session(s) "
           f"({added} new, {updated} updated, {pruned_now} newly pruned)")
    if skipped:
        msg += f"; {len(skipped)} skipped"
    print(msg)
    for s_ in skipped[:10]:
        print(f"  skipped {s_}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
