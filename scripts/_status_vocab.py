"""_status_vocab.py — the ONE definition of record status vocabulary.

Every consumer that classifies a record's status (rot-lint, the close-gate
hook, the deterministic closer, the HANDOFF generator) imports from here. Three
independently-maintained terminal-status regexes previously drifted — that drift
produced the "closed" bug (v3.2.0) and the review-gate bug (v3.2.1), and a
red-team (2026-08-30) found `closed`/`done`/`finished` still classified
terminal by two tools and unrecognized by the other two. One shared source
removes the drift surface.

Vocabulary (a status value, normalized, matched at its START):
  OPEN          in-progress · in_progress · active   — work continues
  PARKED        parked                                — resumable, set aside
  TERMINAL      complete(d) · abandoned               — the canonical done states
  NEAR_TERMINAL closed · done · finished              — a close that has not
                registered in canonical vocabulary; treated AS terminal for
                gate purposes (a record here IS being closed) but flagged so
                the author canonicalizes it.

`complete` (no 'd') is included: it is what real records actually write.
"""
from __future__ import annotations

import re
import unicodedata

OPEN = ("in-progress", "in_progress", "active")
PARKED = ("parked",)
TERMINAL = ("complete", "abandoned")          # 'complete' covers 'completed'
NEAR_TERMINAL = ("closed", "done", "finished")

# format/combining controls an attacker (or a bad paste) can hide in a status —
# category-based (Cf: zero-widths, bidi, word joiner, soft hyphen; Mn/Me:
# combining marks like CGJ), not a hand-list a new codepoint can sidestep
_STEALTH_CATS = ("Cf", "Mn", "Me")
# a leading '- **Status:** ' / '**Status**: ' / 'Status: ' label, ANCHORED to
# the string start: an unanchored search re-extracted from an inner mention
# ("completed (final status: shipped)" -> "shipped") and silently declassified
# a terminal status across all four consumers (review 2026-08-30)
_LABEL_RE = re.compile(r"[-*\s]*status\s*\**\s*:\s*\**\s*(.+)", re.I)
# bare 'complete' counts as terminal only when what follows reads as a close
# ("complete", "complete (deployed)", "complete, shipped"), not as an open
# plan ("complete rewrite planned")
# a bare hyphen needs leading whitespace ("complete - shipped"), or
# "complete-rewrite planned" would classify terminal
_TERMINAL_RE = re.compile(
    r"(?:completed|complete(?=\s*(?:$|[([{:;,.—–])|\s+-)|abandoned)\b", re.I)
_NEAR_RE = re.compile(r"(?:closed|done|finished)\b", re.I)
_OPEN_RE = re.compile(r"(?:in[-_]progress|active)\b", re.I)
_PARKED_RE = re.compile(r"parked\b", re.I)


def status_value(raw: str) -> str:
    """Reduce a raw status field to its bare value.

    Accepts both the frontmatter form ('completed') and the bulleted form the
    real corpus uses ('- **Status:** complete (deployed to test theme)'), and
    normalizes away zero-width/bidi controls and NFKC-folds homoglyphs so a
    Cyrillic-e 'complete' cannot hide from the keyword match. Returns the
    portion after any 'Status:' label, bold/bullet markers stripped.
    """
    s = unicodedata.normalize("NFKC", raw)
    s = "".join(c for c in s if unicodedata.category(c) not in _STEALTH_CATS)
    m = _LABEL_RE.match(s)
    if m:
        s = m.group(1)
    return s.strip().strip("*").strip()


def has_nonascii(raw: str) -> bool:
    """True if the status value's LEADING WORD carries a non-ASCII LETTER — a
    possible homoglyph in the classification keyword (e.g. Cyrillic-e
    'complete'). Scoped to the leading alphabetic token so legitimate freeform
    status lines with em-dashes, en-dashes, or ✅ emoji do not false-flag."""
    # examine the PRE-stripped value: stealth controls (word joiner, soft
    # hyphen, CGJ) are removed for classification but must still be surfaced
    v = unicodedata.normalize("NFKC", raw)
    m = _LABEL_RE.match(v)
    if m:
        v = m.group(1)
    v = v.strip().strip("*").strip()
    # ASCII-whitespace delimited: \s would also break on U+0085/U+2028-class
    # Unicode whitespace, splitting the token BEFORE the smuggled control
    lead = re.match(r"[^ \t\r\n\f\v]*", v).group(0)
    # surface letters, stealth controls, AND other control/private/surrogate
    # codepoints (Cc/Co/Cs) — those declassify the keyword just as silently
    return any(ord(c) > 127 and
               (c.isalpha() or
                unicodedata.category(c) in _STEALTH_CATS + ("Cc", "Co", "Cs"))
               for c in lead)


def is_terminal(raw: str) -> bool:
    """Canonical terminal (complete/completed/abandoned) at the value's start."""
    return bool(_TERMINAL_RE.match(status_value(raw)))


def is_near_terminal(raw: str) -> bool:
    """A close expressed in non-canonical vocabulary (closed/done/finished)."""
    return bool(_NEAR_RE.match(status_value(raw)))


def is_gate_terminal(raw: str) -> bool:
    """Terminal for GATE purposes: canonical OR near-terminal.

    This is the set the review-gate, the close-gate hook, and the closer all
    key on — a record here is being closed and must satisfy the gates.
    """
    return is_terminal(raw) or is_near_terminal(raw)


def is_open(raw: str) -> bool:
    return bool(_OPEN_RE.match(status_value(raw)))


def is_parked(raw: str) -> bool:
    return bool(_PARKED_RE.match(status_value(raw)))


def classify(raw: str) -> str:
    """One of: terminal · near-terminal · open · parked · unknown · none."""
    v = status_value(raw)
    if not v:
        return "none"
    if _TERMINAL_RE.match(v):
        return "terminal"
    if _NEAR_RE.match(v):
        return "near-terminal"
    if _OPEN_RE.match(v):
        return "open"
    if _PARKED_RE.match(v):
        return "parked"
    return "unknown"
