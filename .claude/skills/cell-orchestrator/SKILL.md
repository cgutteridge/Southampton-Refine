---
name: cell-orchestrator
description: Run the Southampton Refine cell queue as a thin orchestrator. Builds each queue item in a fresh session so the main context stays small. Use when the user says "run the queue", "orchestrate" or invokes /cell-orchestrator.
---

You are a thin orchestrator. You do not build anything yourself. Your context must stay small.

## Stop point
Default: stop after ONE queue item (the first unchecked `[ ]` in site/QUEUE.txt) has finished. The user may widen it ("whole cell", "N items", "N cells", "until HH:MM", "overnight") when invoking. Never go past the stop point without asking. Ready-made prompts: site/START-PROMPTS.md.

## Overnight / unattended mode
Used when the user says "overnight" or "nobody is watching". Then: do not ask questions. If a cell fails or looks risky, record it as a PROBLEM in the run log, retry at most once, leave the world at its last good state (`site_recover.py`), and carry on with the next cell. Stop the whole run if the lock is held fresh by someone else, two cells in a row fail, the same tool/API error repeats, or the next cell is ambiguous. Never touch hand-made cells, commit, or edit shared scripts unattended. Respect the stated end time or cell count.

## Keep the human informed (every cell, every mode)
After each cell is verified, write one block to the human run log, then move the marker:
`.venv/bin/python scripts/site_status.py log --cell <tx,tz> --did "<what was built, with counts>" --look "<x,z: what to check>" [--look ...] [--problem "<anything open or failed>"]`
Give at least one concrete `--look` coordinate per cell (the riskiest or newest thing). When the run ends or stops, run `site_status.py morning --since "<run start>"`, put a one-paragraph summary at the top of site/RUN-LOG.md, and give the user the same in your final message. `site_status.py status --gaps` shows the grid. Finish by refreshing the human pages: `.venv/bin/python scripts/site_pages.py` (HTML only; it links existing images and never makes new ones).

## Preflight (every item)
1. Read site/QUEUE.txt (first unchecked item only), site/CURRENT-CELL.json and site/LOCK.json. Do not read more.
2. If LOCK.json has an owner and its heartbeat is under 90 minutes old (scripts/site_lock.py STALE_MIN), STOP and tell the user who holds it. Never clear, steal or edit the lock by hand.
3. If the lock is stale, or `.venv/bin/python scripts/site_recover.py status` shows an in-flight/rolled-back stage, run `site_recover.py recover <cell> --apply` for that cell first (dry run without --apply; never on a fresh lock; tell the user if it reports unsure/failed), then continue.
4. Check mcp__ccd_session_mgmt__list_sessions for a running session already on this item.

## Current rules (read these, do not copy them into prompts; point builders at them)
- Start from site/RESUME-ISSUES.txt (state, next steps, what needs the user) and site/ISSUES.txt (I-057 umbrella). Work the backlog of unfinished cells BEFORE new cells such as Q-178.
- Definition of done: `site_handoff.py cell_gaps` is empty (ground/trees/decor applied, trees mask stamped rule 'overhang-v1', no unrefined Geocraft left except recorded stages.lump_sweep exceptions). `site_handoff.py next --plan` (~43s, read-only) lists the cells not done; the unit of work is one CELL.
- Within a cell: lumps first (house only from OSM footprints, or traced from aerial/Street View if a photo source shows a building OSM/lidar lack), then re-run trees under the current rule (dry run first; stop if dense fill adds hundreds of crowns to a built-up cell).
- Trees: a tree belongs to the cell its trunk is in; crowns overhang neighbours (air or neighbour tree leaves), lawn only (TREES_ON_PAVING False). Material rule: never place plain dirt, use coarse_dirt. Floors come from natural ground outside the footprint, never from a scan starting at y41. Check door reachability (site_walk) before and after.
- Do not touch 48,-44 / 48,-45 beyond a checked tree re-run (hand-made), and leave their marker alone. The cell marker only shows the user which cell is being worked on (user, 2026-10-15). When a cell is finished down to decor and `cell_gaps` is empty and the patrol is clean, move the marker to the next cell: claim the lock, `cell_marker.py --clear <old>` then `--raise <next>` under SITE_OWNER, release. The user reviews wherever they like; never wait on them for this. Process direction from the user: refine the underlying process, never stack per-symptom rules or extra checking steps; log new reports as symptoms of I-057.
- `site_handoff.py end` was fixed in this session but is only for numbered Q items; for cell-level work do not use it.

## Per cell (or per item)
1. Brief: run the `cell-researcher` subagent (or general-purpose reading .claude/agents/cell-researcher.md if it is not loaded) for the cell. Ask for a 200-word brief, or let the builder brief itself from `site_handoff.py next --no-brief`, site/cells/<cell>-STAGES.json and `lump_scan.py`.
2. Build: ONE blocking general-purpose Agent per cell, run in the foreground, strictly one at a time (one writer, one lock). Do NOT rely on start_session wake-ups: the app refuses start_session from an automated wake-up turn (only the user's own messages allow it), so a chain would stall. The prompt names the cell, points at the rules above, and says: claim the lock with a unique owner, explicit region snapshot + origin fingerprint before each apply, SITE_OWNER, readback 0 mismatches, patrol, update the cell's STAGES file and ISSUES.txt, release the lock, report in under 200 words.
3. When the agent returns: verify, do not trust. Check the lock is released (`ls site/LOCK.json`), `cell_gaps` for that cell is empty, a new region snapshot exists, and the STAGES file changed. Do not read the agent's transcript.
4. Report to the user in a few lines: what finished, what failed, anything needing the user's visual check. Then stop at the stop point.

## Stop and ask when
- the lock is held, or a patrol fails, or the brief flags real risks or open questions
- the next item belongs to a different cell or ring than expected
- anything is ambiguous about which cell is next (cell order: north centre of the ring, then clockwise; see rules/radial-good-enough.md)

## Context hygiene
Keep notes to one line per item. If this session grows past a comfortable size, write the current state to site/HANDOFF.txt (or the scratchpad), then tell the user it is safe to start a fresh orchestrator session.
