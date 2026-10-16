# Reference imagery: fetch once, judge once

Read before finding, fetching or viewing any photo or aerial. Logging format:
`reference/LOGGING.txt`.

- Before downloading: `ref_manifest.py find --xz/--wm/--place` and check
  url/sha256. Spatial keys are sparse `mc_tiles` (128) + `wm_tiles`, never a
  folder-per-tile tree.
- After downloading: `ref_manifest.py add …` (sets useful + tile fields).
- Do not re-Read images marked `useful=no`. Prefer mosaics and contact sheets.
- Which source answers which question: `rules/evidence-order.md`.
- Google aerial (`scripts/google_aerial.py sheet`, reference/SOURCES.txt) is look-only and is looked at for every
  cell: view the sheet once, write down what it shows, never save it. It may be the step's one primary aerial.
- Per build step: at most one primary aerial and one primary street photo,
  unless settling a named disputed detail.
- Private interiors are never researched (see `rules/frontage-and-evidence.md`).
  Public-building interiors only when explicit interior references exist.
  Back gardens come from the aerial, not from photos taken over fences.
- No exact house photo: same-terrace or same-typology exteriors may be used as
  hints (manifest `models` include `hint`; note the target). The LIDAR/aerial
  footprint for the target plot still wins.
- At handoff or the end of a queue stage, write TOKEN NOTES (2-5 lines) with
  fixes: `reference/LOGGING.txt` §8.
