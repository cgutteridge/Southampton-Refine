# Radial cadence and the good-enough bar

Read before choosing, planning or signing off build work.

## Good enough (the one home for this rule)
- Hit the done-bar (`site/NOTES.txt` §8) and move on. This is a big city.
- When a detail is burning tokens without changing street-readable accuracy:
  stop, mark it good enough, log a short note if useful, go to the next cell.
- Do not chase chimney pots, garden furniture, planting detail or single
  disputed blocks unless the place brief raised the bar.
- Good enough never means "skip the survey" or "front face only": a house is
  still built on every side (see `rules/frontage-and-evidence.md`).

## Radial, no gaps
- Rebuild all of an area, outward from the focus in `site/COVERAGE.txt`
  (origin cell 48,-44), finishing each Chebyshev ring before the next. One
  active cell at a time. Cell order: north centre of the ring, then clockwise
  (north is smaller tz).
- Coverage, parcels and sign-off: `site/PROCESS.txt` §2c. The record is
  `coverage.py`, never chat, and never hand-edit PROCESSED CELLS.
- Skip signed-off parcels in new-cell work. Where an area already has builds
  (Broadlands), keep them.
- Exception, current priority (user, 2026-10-16): the Google review (I-073,
  `site/GOOGLE-REVIEW.txt`) deliberately re-opens finished cells in ring order,
  features and ground, and runs ahead of new-cell passes (code first, then fixes
  to existing work, then new builds). A sign-off lapses where a redo touches it:
  re-sign afterwards. Snapshot first, dry-run diff before any re-apply (I-043).
- Outside that review, revisits of processed ground are allowed but not the focus.
- Queue explicit todos for distinctive local features (PROCESS §2e).
- If the focus changes, update COVERAGE FOCUS and leave no holes behind.
