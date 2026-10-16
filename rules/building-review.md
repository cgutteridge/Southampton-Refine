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
   Google shows roof greeblies (user, 2026-10-16): plant boxes, vents, louvred vents, skylights, solar panels, lift overruns, parapets. List
   them per roof in this step; lidar filters them out (`geocraft-lidar-filters-small-features`), so Google is the only source.
4. **Keep or rebuild.** Keep when nothing in the list matters at street scale (`rules/radial-good-enough.md`). Rebuild by
   reusing the cell's builder (`scripts/oakdene_court.py` is the pattern), clearing only the build's own recorded blocks, so
   trees stay. Claim the lock, dry run, apply with `SITE_OWNER`. Done when readback is 0, the footprint check is OK and doors reach.
5. **Check with the user.** Run the `human-confirm-fix` skill. Steering replies loop back to step 4 and become rules
   (`site/CRAFTSMANSHIP.txt` §2). Only the user's "yes" closes the issue.
6. **Record.** Issue state with the user's words, a REVIEWS entry (3 matches, mismatches, token notes), the general lesson in
   the rule file that owns it, commit.
