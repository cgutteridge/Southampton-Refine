# Start prompts

Copy one, change the bits in `<angle brackets>`, paste into a Claude Code session opened in this project.
Each one runs the `cell-orchestrator` skill (`.claude/skills/cell-orchestrator/SKILL.md`), which builds in fresh agents,
verifies, moves the marker on, and writes one block per cell to `site/RUN-LOG.md`.

## See where things are (no building)
```
Show me where we are: run site_status.py status --gaps, then site_status.py since "<yesterday 17:00>", and tell me
in a few lines what is done, what is next in the backlog, and anything waiting on me.
```

## One cell, hands-on
```
/cell-orchestrator 1 cell, <tx,tz or "next in backlog">. Stop after it and tell me what to look at.
```

## A few cells while I'm around
```
/cell-orchestrator <3> cells, backlog first, start with <tx,tz>. Stop and ask me whenever the skill's
"Stop and ask when" list says to. After each cell: log it with site_status.py log, move the marker on,
and give me the "Look at" coordinates in a line.
```

## Overnight
```
/cell-orchestrator overnight: run until <07:00> or <N> cells, whichever is first. Backlog first, start with <tx,tz>.
Nobody is watching, so do not ask questions. Policy:
- After EVERY cell: verify (lock free, cell_gaps empty, STAGES updated), run site_status.py log with what was
  done, the coordinates I should look at, and anything open, then move the marker to the next cell.
- If a cell fails or looks risky (patrol failure caused by it, readback mismatches, a stage left in flight,
  a dense-fill trees dry run adding hundreds of crowns): put it in the log as a PROBLEM, do not retry more than once,
  leave the world as the last good state (site_recover if needed) and continue with the next cell.
- STOP the whole run (do not continue) if: the lock is held by someone fresh, two cells in a row fail, a tool or API
  error repeats, or the next cell is ambiguous (see "Stop and ask when").
- Do not touch hand-made cells (48,-44, 48,-45), do not commit, do not edit shared scripts.
- At the end (or on stopping) write the morning report: site_status.py morning --since "<start time>", and leave a
  one-paragraph summary at the top of site/RUN-LOG.md.
```

## Morning after
```
Run site_status.py morning --since "<yesterday 22:00>" and walk me through it: what finished, what failed, and the
"Look at" list in the order I should visit them. Take me to the first one.
```

## After a crash or an app restart
```
Something died mid-run. Check site_recover.py status and the lock. If the lock is stale, recover, then tell me what
state each touched cell is in (site_status.py since "<time>") before doing anything else.
```

## Handy commands
| What | Command |
| --- | --- |
| Grid of cells, marker, lock | `.venv/bin/python scripts/site_status.py status` (add `--gaps` for the real done-bar, ~20 s) |
| What changed since a time | `.venv/bin/python scripts/site_status.py since "2026-10-15 17:00"` |
| Write a run-log block | `.venv/bin/python scripts/site_status.py log --cell 47,-45 --did "..." --look "x,z: what to check" --problem "..."` |
| Morning report | `.venv/bin/python scripts/site_status.py morning --since "2026-10-15 22:00"` |
| Which cells are not done | `.venv/bin/python scripts/site_handoff.py next --plan` (~20 s, read-only) |
