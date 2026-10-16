# Building review

Read when reviewing a built building (I-064 / I-069 items, or the user asks).
One building per review. Skip any building that already has an open feature item on the QUEUE (it is rebuilt there; user, 2026-10-16). Worked example: Oakdene Court, `site/REVIEWS.txt` 2026-10-16.

1. **Read the data, not the label.** Lump row (`site/cells/<cell>-LIDAR.txt`), `lidar_audit.py --cell`, and the raw
   height grid of the building. Labels (flat/pitched, storeys) are estimates until the grid and a photo agree.
   Done when you can say what lidar shows for shape, top Y and floor level.
2. **Gather evidence in `rules/evidence-order.md` order.** For a university building run `scripts/portals.py cell tx,tz` first: it
   gives every entrance's exact position and name (a canopy or door found in OSM/the build may be one of them: 42-A, 2026-10-16). One Street View frame, a Google sheet
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
   A feature build changes the building's own cells only: no landings, steps, paving or plants outside the footprint (ground,
   trees and decor are other passes); if a door needs steps, queue it for the ground pass (user, 2026-10-16).
   Fiddling a block or two to make a build sit well is fine (user, 2026-10-16); what is not fine is stacking follow-up fixes.
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


## Reflection on the 48,-44 review (2026-10-16): what went wrong and the approach we keep
What cost the most time, in order: (1) building from part of the evidence and being corrected (a whole building black from three frontage photos; tall
1x2 window slots; doors chosen by habit; a pavilion bigger than its photo; floating balustrades); (2) stacking follow-up patches on a
building instead of rebuilding it (a dozen plans on B42 made pits, pillars, holes and clashes); (3) scripts that read the world they
were changing, so a re-run chose different spots (entrances); (4) judging from previews and renders when the user's own view or a number
would have settled it.

The approach:
1. **Evidence table first, in the script docstring**: for each fact (footprint, heights, materials per face, doors, roof features) name the
   source: OSM, lidar grid cell by cell, Google z20, aerial, every portal photo at 800 px (`scripts/portals.py`), block reference for the
   block choice (`scripts/block_reference.py`). All relevant references, before the first block. A photo shows ONE face: say which.
2. **One building = one script** (lidar bands -> Campus subclass for per-zone materials -> `entrances` -> clear the old build -> keep trees).
   A second fix to the same building means rebuild it whole, never another follow-up. Per-face rules need positions as well, because a
   stepped outline has steps facing every way.
3. **Re-runnable**: plan from OSM footprints, lidar and recorded states, never from blocks the script itself placed; to re-run, put back
   the previous own record first (restore, then plan).
4. **Check with numbers, then show**: live-minus-lidar grid, `scripts/airtight.py`, door frame guard, footprint guard; then the user's
   own view (read their position, capture, never move them). Renders are rough shapes, not colours.
5. **Only the building's own cells**: ground, steps, trees and plants are other passes; queue what a door needs.
6. **Simple**: few big features that read at street scale (solar array, fans, fascia), not individual vents and seams.
Open items: the Prayer Room corner of the West Building (Q-quoted in the queue), the facade of the other B40 faces, B38/B40 are still the
older highfield_susu_west builds and should get the same one-script rebuild.


## Rebuild beats patch: SU retail B57 (user, 2026-10-16: "much much better; starting over is often much cheaper")
The retail had been fixed five times in a row (front turned, glazing redone, door moved, canopy shifted). Deleting it and rebuilding from the
evidence table alone, in one pass, got it accepted at the first look. What made the difference:
1. **Do not read the old build or its script as a reference** (user steered mid-task). They carry its wrong guesses forward. Keep only the
   mechanism that restores its own recorded blocks (re-runnable rule), plus lidar-derived levels. A redo starts from the table in
   "Reflection on the 48,-44 review" step 1. Third fix on one building = delete and restart, not patch.
   **Many new references since the feature was last worked on = start over too** (user, 2026-10-16): when photos, portal entries, outlines or
   Google reads have piled up since the last pass, the old build rests on a thinner evidence table; delete it and rebuild from the current one
   rather than patching, even if no single fix has been made yet. Same logic as the Library Square trees: the Google redo replaced the whole zone.
2. **The OSM outline of a canopied building is the ROOF outline.** The old build put the walls on the outline and the canopy outside it, so it
   came out ~4 blocks too big. Walls stand where the glazing is: Google shows an upstand line where canopy meets wall (here 3.8 in from the edge),
   and the portal sits behind the roof edge, not on it. Check portal-to-outline distance before choosing the wall line.
3. **Work in the building's own frame.** Fit the footprint (PCA of its cells: centre, long axis, angle), compute (along, across) for every cell,
   and write per-face rules on that: face = nearest rectangle side, front rhythm = a table by `t` across the face, roof features measured
   as (along, across) rectangles and lines off the Google sheet. A 24-degree rectangle then needs no per-direction exposure rules.
4. **One building = its own `shells()`** when it is not a plain Campus part (open canopy, set-back walls): only write the cells you mean,
   keep the Part over the whole footprint so clearing, deck and greeblies still work.
5. **Entrances on a stepped front**: no straight stretch is long enough for `entrances.py`. Take two flat (single-exposure) treads cells
   nearest the portal, steel jambs at both ends, the sign band as the lintel, open passage.
6. **Numbers then pictures**: live tops vs lidar, no air in exposed wall columns, then the user's own view. Iso render (`block_render_region`)
   is useful; its `front`/`side` views are flattened projections and mislead.
7. **Practical**: view a Google sheet whole with `document.body.style.zoom = 0.55` in the browser pane (one screenshot, no scrolling).
   Before teleporting the user, check the target is standing room (air at y+1, y+2) with `World`: the first spot I picked was inside another
   building.
Refinement done (2026-10-16): the frame helpers now live in `campus.BuildingFrame(cells)` (fit by PCA; `frame`, `world_xz`, `rect`, `line`, `point`,
`face_of`, `entrance_cells`, `jambs`; `centre=`/`axis=` pin the fit). `build_highfield_su_retail.py` uses it and its plan is cell-for-cell unchanged;
tests in `scripts/test_campus_frame.py`. B42 (Q-185), Jubilee (Q-186) and B38/B40 rebuilds: `F = BuildingFrame(FOOT)` and write the face rules on it.
