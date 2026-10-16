# Houses: footprint, frontage and evidence

Read before planning or applying any house, plot or streetscape build.

## What a house build is
A house feature (pass 1 of a cell, `site/HANDOFF-LAYERED-PASSES.txt` §1) is
the house only, built on every side:
- Walls on the OSM footprint as a guide (Minecraft-readable, not a jagged 1:1
  trace; see `site/CRAFTSMANSHIP.txt` §1), a real roof form (ridge direction
  and type from aerial, Y from LIDAR), windows and doors on all sides, bays,
  porches, chimney stacks as plain massing.
- Inside: one floor per storey and one stair so it is walkable. No rooms,
  partitions or furniture. Private interiors are never researched.
- No gardens in the house build. Gardens belong to the later passes: lawn and
  paving = ground, trees and shrubs = trees, fences, walls, hedges, sheds =
  decor. Garden layout comes from the aerial only (no peering photos).
  Boundaries come from `scripts/garden_sources.py` (OSM barrier, then the
  per-street convention `site/gardens/<street>.json`, then aerial hedge strip,
  then marked inference), read by `decor_layer.py`.

Why whole houses: I-009, five façade builds put a brick shell on the pavement
of Broadlands Road, about 6 blocks in front of the real houses. Readback, walk
and patrol all passed. All five were reverted.

## 1. Survey first
- `python3 scripts/osm_footprints.py frontage --bbox x0,z0,x1,z1`: real
  `addr:street` + number, front-wall MC x,z, setback, surface profile to the road.
- `python3 scripts/osm_footprints.py plots --bbox …`: a first-guess plot per
  house (JSON + PNG). Plot sides continue the party walls.
- Name builds by real street + numbers, e.g. `broadlands_rd_20_22`.
- Work a whole run of adjacent houses per build (a terrace between two gaps),
  so neighbours meet cleanly at party walls and roof steps.

## 2. Placement
- Walls sit on the OSM footprint within about 1-2 blocks after squaring. Never
  at "the last solid block before the pavement" (I-009).
- Doors face the street they are numbered on.
- Geocraft/LIDAR Y is the massing authority (ground, eaves, ridge).
- `site_kit.apply()` refuses building-like blocks far outside OSM footprints.
  Set `plan.outside_footprint_ok` only for a genuinely unmapped structure and
  name its evidence id. Never to shove a house onto the kerb.
- A building visible in imagery but missing from OSM or lidar is built too
  (PROCESS §2d-i).
- Lidar is a dated snapshot: if newer photos clearly show a change, follow the photo and
  record the mismatch (PROCESS §2d-i).

## 3. Describe the evidence before planning
3-5 lines per property group in REVIEWS or the place notes: storeys, bays and
porches, opening rhythm, materials, roof form (aerial), front boundary line
(street photo). Name the photo or aerial id for each. Same-terrace typology
may be used as a hint for side and rear elevations; label it `hint`.
Storeys: photo evidence first (Street View, Rightmove, other-side photos), then OSM
`building:levels`, then the lidar estimate only if nothing else exists; label it.

## 4. Check the result against the evidence, not against itself
Readback, walk and patrol prove the blocks match the plan, not that the plan
matches Southampton. Done needs:
- `osm_footprints.py check --build <name>` passes.
- A client view from the reference photo's camera (manifest `bbox_mc`) beside
  the photo, and a top-down view beside the Google sheet (`google_aerial.py`; the university aerial too where it
  helps), in the contact sheet.
- 3 concrete matches or mismatches written in REVIEWS.

## 5. Stop instead of patching
The stop rule is in `site/PROCESS.txt` §2: a geometry fix build means revert
and re-survey, never _b/_c patches. If a QUEUE item tells you to repeat a
method that contradicts the evidence, fix the queue item and log an ISSUE.
