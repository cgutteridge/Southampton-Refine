# Building review

Read when reviewing a built building (I-064 / I-069 items, or the user asks).
One building per review. Skip any building that already has an open feature item on the QUEUE (it is rebuilt there; user, 2026-10-16). Worked example: Oakdene Court, `site/REVIEWS.txt` 2026-10-16.

1. **Read the data, not the label.** Lump row (`site/cells/<cell>-LIDAR.txt`), `lidar_audit.py --cell`, and the raw
   height grid of the building. Labels (flat/pitched, storeys) are estimates until the grid and a photo agree.
   Done when you can say what lidar shows for shape, top Y and floor level.
2. **Gather evidence in `rules/evidence-order.md` order.** One Street View frame, a Google sheet
   (`google_aerial.py`), and a university aerial that covers the building (check `bbox_mc`, `rules/reference-token-budget.md`).
   Log each with `cell_sources.py --record`. Done when storeys, roof and openings each name a source.
3. **Compare the live build with the photos side by side.** Game capture from the photo's camera, a top-down capture beside the
   aerial. List matches and mismatches. A build that matches lidar and OSM can still be wrong (Oakdene: right plan and height,
   wrong roof colour and windows). Done when each mismatch is named.
   A review run of buildings uses all three: Google (greeblies, roof colour), the university aerial (footprint, roof form) and
   lidar (heights: plinth, plant and wing heights are read off the pristine lidar top, `lidar_heightmap.py`, never guessed).
   Greeblies are the decor step of a feature (`site/CRAFTSMANSHIP.txt`): unusual blocks welcome, plants matched by colour and size.
   Roof levels and their extents come from the lidar cell by cell (3x3 majority filter, rim cells take their neighbour's level), never
   from boxes drawn on a picture; Google decides colours and greeblies, not heights (user, 2026-10-16: "you ignored the lidar").
   Before painting or adding to a roof, print the live columns (top block and Y per cell) and compare with the lidar grid; a
   later build can have left pits, holes or lidar-rim bands (SU retail: a 5-wide pit round the north edge, 2026-10-16).
   Google shows roof greeblies (user, 2026-10-16): plant boxes, vents, louvred vents, skylights, solar panels, lift overruns, parapets. List
   them per roof in this step; lidar filters them out (`geocraft-lidar-filters-small-features`), so Google is the only source.
4. **Keep or rebuild.** Keep when nothing in the list matters at street scale (`rules/radial-good-enough.md`). Rebuild by
   reusing the cell's builder (`scripts/oakdene_court.py` is the pattern), clearing only the build's own recorded blocks, so
   trees stay. Claim the lock, dry run, apply with `SITE_OWNER`. Done when readback is 0, the footprint check is OK and doors reach.
5. **Check with the user.** Run the `human-confirm-fix` skill. Steering replies loop back to step 4 and become rules
   (`site/CRAFTSMANSHIP.txt` §2). Only the user's "yes" closes the issue.
6. **Record.** Issue state with the user's words, a REVIEWS entry (3 matches, mismatches, token notes), the general lesson in
   the rule file that owns it, commit.

## Pitfalls from the B42 / Jubilee review (2026-10-16)
 - **Numbers before pictures.** Before showing the user, print live-minus-lidar per cell over the building (pristine lidar, one
   heightmap per cell: a building can straddle a cell edge, B42 does at z -5505) and fix every cell off by 2 or more. Every visual
   complaint in that review (3-high strip, pillars, grey triangle) was already a number.
 - **Extents from cells, not drawings.** A shape read off a picture (box, polygon) is a hint for where to look. Lowered roofs, colour
   patches and membrane areas are defined by lidar cells of the feature's own part, so a colour cannot spill onto a neighbour and a
   rim cell cannot stand up as a pillar. Edge (coping) cells are never recoloured.
 - **Follow-up steps of a feature** (`--lower`, `--greeblies`, shared `MODIFIES`, undo from the base record, never `built_cells()`):
   see FEATURE FOLLOW-UP STEPS in `site/CRAFTSMANSHIP.txt`. Re-run steps rather than patching by hand.
 - **One defect is a class.** When the user finds one (a door with no jamb, a trench from the door generator, a canopy from an OSM
   `building=roof` that Google does not show), fix it, then add the guard to `site_kit.apply` or the generator and run an audit over
   everything already built (`scripts/door_audit.py`: 142 of 700 doors unframed, QUEUE Q-182). No evidence in Google or lidar for an
   OSM micro-feature means remove it.
 - **Ask what is really there.** For entrances, steps and levels the user's knowledge beats every source here. Ask them to stand
   where it is wrong; read their position (`player_list_online`) and look (`view_capture`), say what you observed, then act.
 - **Do not move the user.** Observe with `player_list_online`, `view_capture` and `block_render_region` (server-side, no client).
   Teleport only on request (the user said "you moved me" and "don't move me"). `site_kit.apply` still moves them when they are
   more than 80 blocks from a build, but puts them back exactly where they were afterwards (f4c536c).
 - **Browser pane.** It refuses some new `file://` paths. Write the sheet over a filename it has already opened (instance/google-aerial/)
   and navigate again. `google_aerial.py --marks cells.json` paints live cells (tile, membrane, colour patches) on the Google sheet.

