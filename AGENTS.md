# Southampton Refine: agent entry point

Accuracy to the real place only: no fictional districts, themes or whimsy.
Files in `site/` are the memory, not chat. Works for any AI coding tool or a human.

## Start
Run `python3 scripts/site_handoff.py next`. Its SESSION BRIEF names the top
queue item and the exact files to read (RULES READING, from
`site/RULES-CONTEXT.txt`). Begin that item straight away; running the command
is the go-ahead. Do not read every rule file or all of `site/PROCESS.txt`.

## Always
- One builder at a time: claim `site/LOCK.json` with `scripts/site_lock.py`
  before any world change; apply with `SITE_OWNER=<owner>`.
- Read before any live edit: `rules/radial-good-enough.md`,
  `rules/geocraft-accuracy.md`. Before touching imagery:
  `rules/reference-token-budget.md`.
- Never use a browser automation that takes over the user's Firefox unless the
  user explicitly asks for it in the current request.
- After a world fix the user should see, run the `human-confirm-fix` skill:
  ask first, show it in the game, put one question. The user's "yes" closes
  the issue.
- Process, session start/end, handoff, chain rule and the "call the user in"
  rule: `site/PROCESS.txt` §6–§7.
- Sound cues: `python3 ~/Projects/agent-soundboard/scripts/play.py <id>` (`done`, `need-you`, `error`;
  flair rare). Table and rules: `.cursor/rules/agent-soundboard-flair.mdc`. Never `--wait`.
- Python: `.venv/bin/python` (system python is locked down).

## Where rules live (one home each)
| Topic | File |
| --- | --- |
| Good enough, radial cadence | `rules/radial-good-enough.md` |
| What to trust from Geocraft | `rules/geocraft-accuracy.md` (+ `site/GEOCRAFT.txt`) |
| House footprints, frontage, evidence, interiors | `rules/frontage-and-evidence.md` |
| Terraces | `rules/terrace-builds.md` |
| Reviewing a built building | `rules/building-review.md` |
| Reference imagery | `rules/reference-token-budget.md` |
| What to trust per question (storeys, roof, ground) | `rules/evidence-order.md` |
| How blocks are placed (walls, glass, roofs, streets) | `site/CRAFTSMANSHIP.txt` |
| Pass order, who clears Geocraft, masks | `site/HANDOFF-LAYERED-PASSES.txt` |
| Vegetation, saplings | `site/FOLIAGE.txt` |
| Cadence, coverage, session start/end | `site/PROCESS.txt` |
| Overview, done-bar, accuracy rules | `site/NOTES.txt` |
