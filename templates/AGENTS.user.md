<!-- perdure-records:begin -->
## perdure records

Any task that changes files or decides something keeps one record under
perdure/workflows/, opened before the first edit or as soon as planning or a
review reaches a decision; the work that follows continues in the same record.
The format is in the perdure plugin's `docs/RECORDS-CONVENTION.md`.

- Write the record's plan and decisions when you open it; update it at
  checkpoints.
- When a record opens, say so in one passing line; never ask whether to keep
  one.
- A dispatched agent works under the record of the session that dispatched it
  and opens none.
- When you pick a task back up from its record, say so first, in one line:
  `Resumed from perdure: <task>, next: <next step>`.
- Close it with the perdure `close` skill (`scripts/close-workflow.py`), never
  by editing its status, and only with a review verdict or a recorded skip.
- A plan that is dropped is closed as abandoned, with one line on why.
- `perdure/HANDOFF.md` is generated from the records. Never edit it by hand;
  on a merge conflict, regenerate it (`handoff.py .`).
- With someone who does not code, call the record a note and say "where we
  left off". At the first note in a folder outside a repository, add: "These
  notes are plain files in this folder; anyone who can open it can read them.
  Tell me what is confidential and I'll leave it out."
- In the home folder, keep the notes in ~/perdure and say so.

Skip the record only when the whole task is one line in one file (a typo, a
one-line fix), or a question or brainstorm that decides nothing.
<!-- perdure-records:end -->
