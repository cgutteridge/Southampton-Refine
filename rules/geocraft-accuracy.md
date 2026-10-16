# Geocraft accuracy: what to trust

Read before surveying or planning any world edit. Full write-up (generator
widths, history): `site/GEOCRAFT.txt`.

**Trust (keep):**
- Building plan footprints (OSM polygons rasterised 1:1).
- Road and path routes (OSM centrelines, junctions).
- Heights and massing Y (UKDEFRA DTM ground + DSM-DTM extrusion): top height and the
  roof surface. Caveats (`site/GEOCRAFT.txt`, `scripts/lidar_heightmap.py`): a dated
  snapshot that filters small features (cars, street furniture); the building rim reads
  3-6 blocks low, so flat vs pitched is judged on interior columns of wide buildings
  only; eave height and storeys are estimates; ground_y is too low for a building on a
  bank above the road.
- Absolute XY via `config/map-maker-offsets.json` + `scripts/osgb.py`.

**Do not trust (fix from aerial / street evidence):**
- Road and pavement widths: fixed buffers by highway class (road half-width
  4, pavement half-width 6). OSM `width=*` was ignored. Stock kerb and road
  edges are not survey.
- Materials, openings, roof colour and pitch, hollow interiors, procedural trees. Ranking per
  question, Google first for roofs and materials: `rules/evidence-order.md`.
- Front gardens: the pavement fringe (half-width 6) swallows them. The raised
  stone band between pavement and houses is usually gardens or hedges at
  LIDAR height, not building. House fronts come from
  `scripts/osm_footprints.py frontage` (see `rules/frontage-and-evidence.md`).

**Refine habit:** keep the corridor and building outline, adjust width
locally, rebuild on the footprints. Do not regenerate Geocraft over the city
unless the user asks.
