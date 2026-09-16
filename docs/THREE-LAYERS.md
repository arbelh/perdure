# Three layers

A perdure checkout carries three kinds of content. Each is produced a different
way, fails a different way, and deserves a different degree of trust. Keeping
them apart is what lets the plugin report something checkable about the trail,
instead of only storing it.

| Layer | What it holds | Who produces it | In one word | Command |
|---|---|---|---|---|
| **Asserted** | records, ADRs, archives | whoever did the work | *intent* | `/perdure:list` |
| **Observed** | the sessions that ran | the `raw` skill, from Claude Code's session files | *denominator* | `/perdure:raw` |
| **Derived and checked** | HANDOFF, lint, coverage | scripts the model runs at each step | *verification* | `/perdure:handoff` |

---

## Asserted: what someone wrote down

**What it is.** Workflow records under `perdure/workflows/`, decision records
under `perdure/decisions/`, and session archives. Prose and frontmatter written
during the work, by a model or a person.

**What it is for.** What a diff cannot show. A diff shows what changed. A record
says why, what was ruled out and on what grounds, and what is still open. The
path not taken leaves no trace in code at all; here it has a line.

**How it is produced.** `/perdure:start` scaffolds a record with a fixed section
layout. The work updates it in place. `/perdure:close` sets a terminal status,
but only once a review verdict or a recorded skip sits in the `# Review`
section.

**Limits.** An assertion is worth the author's care at the moment of writing. A
status line is a claim about a point in time. The other two layers exist to
check it.

---

## Observed: what actually ran

**What it is.** A committed index of the sessions themselves at
`perdure/raw/INDEX.jsonl`: one line per session with its id, timestamps, a
content hash, and counts of prompts and subagent transcripts. A reference to the
sessions, not a copy, which is what keeps it small enough to commit.

**What it is for.** A denominator. "We recorded our decisions" is not a claim
until there is a population to measure it against. This layer supplies the
population.

**How it is produced.** `/perdure:raw` reads Claude Code's session files for the
current project and appends what it finds. `--verify` re-checks the hashes and
reports sessions that have gone missing. Labels are sanitised before they are
written, so a session title cannot inject content into the index.

**Limits.** The sweep is keyed by working directory: work done on one repository
while the shell sits in another appears in neither. The sweep is manual, and an
unswept project produces an empty index, which reads the same as a project that
never had a session. Check both before treating a low count as a finding.

**Across tools.** Records and checks run in every tool the skills reach. This
layer adds a denominator on top: with it, coverage becomes a number rather than
a claim. The reader ships for Claude Code's session files, and the index holds
only ids, timestamps, hashes and counts, so a reader for another tool's store
feeds the same file.

---

## Derived and checked: what a script can confirm

**What it is.** Three things, none of them hand-maintained:

- `scripts/rot-lint.py` compares fields the convention defines against each
  other and against git, and ends every run with a per-check coverage table.
- `scripts/handoff.py` writes `perdure/HANDOFF.md` from the records alone.
  `--check` regenerates the page and compares content, so it reports a
  difference whether the records moved or the page was hand-edited.
- `scripts/coverage.py` classifies each session in the population by the
  strength of its link to a record: **cited** when a record's frontmatter names
  the session id, **weak** when there is only a body mention or a time overlap,
  **unexplained** when there is neither, **unevaluable** when the timestamps do
  not permit a comparison.

**What it is for.** Turning assertions into statements that can fail. A record
that contradicts itself, a page that no longer matches its sources, a terminal
status over an empty review section: each is something a person would have to
notice, and each is something a script reports.

**How it is produced.** By scripts, from the two layers above. Python 3 and git
are enough to run them, and in practice the model does: the lifecycle skills
call the lint, the closer and the HANDOFF generator at the right moments, and
under Claude Code the close-gate hook re-runs the lint on its own when a record
closes.

**Limits.** Every check has a scope, and this layer prints its own. A check
whose precondition a record does not meet is reported `n/a`. A check the tool
could not evaluate is reported `unchecked`, with the reason and the records
named. No check reads prose, so a contradiction stated only in prose is not
detected. The review gate recognises a short English list of pending markers in
the `# Review` body; an equivalent marker in another language is not
recognised. A pass with no findings means no contradictions among the checks
that ran, and the table says which those were.

---

## How they fit

Trust runs one way:

```
  ASSERTED  ──────────────►  DERIVED AND CHECKED
  (records)                  (lint, HANDOFF, --check)
      ▲                              ▲
      │                              │
      └──── OBSERVED ────────────────┘
            (the denominator for coverage)
```

Asserted content is the input. The checked layer can only be as complete as
what it reads, which is why it reports its coverage rather than a bare verdict.
The observed layer is what gives that coverage a denominator.

---

## Reading the current state

Each layer reports itself, so the state is a command away rather than a claim in
a document:

```bash
/perdure:list         # asserted: the records and their statuses
/perdure:raw          # observed: sweep and summarise the population
/perdure:coverage     # the two compared
/perdure:handoff      # regenerate the derived page (--check to verify it)
```

Or directly, from the project root. `${CLAUDE_PLUGIN_ROOT}` is the plugin
directory under Claude Code; elsewhere use the `scripts/` folder beside any
installed skill, or your clone of `github.com/arbelh/perdure`:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/rot-lint.py" .
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/raw-index.py" --root . --summary
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/coverage.py" --root .
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/handoff.py" . --check
```

Each takes the project root, not the plugin directory, and each reports what it
could not do alongside what it found.

Two habits keep the layers honest. Cite the session id in a record's
frontmatter, which moves a session from *unexplained* to *cited*. And use the
convention's status vocabulary, since the review gate keys on it and skips a
record whose status it cannot classify.

`RECORDS-CONVENTION.md` has the record format and the full list of checks; the
releases page lists each release. A pass means exactly
what it says, and the table says what it checked.
