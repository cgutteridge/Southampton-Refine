# Evidence order: what to trust for each question

Read before judging how a building, roof, surface or tree should look. One home
for the ranking; other rules point here. Source tools: `reference/SOURCES.txt`.

Use the first source that answers the question and move on (good enough:
`rules/radial-good-enough.md`). Name the source id in the note. Label anything
below the first row `hint` or `estimate`.

| Question | Best | Then | Last resort |
| --- | --- | --- | --- |
| Footprint, plan | OSM polygon, and the lidar roof columns where they agree (the university's own outline in `reference/buildings` cross-checks a campus building) | Google sheet roof outline | university aerial |
| Top height, roof surface Y | lidar (`lidar_heightmap.py`) | none: do not guess | |
| Storeys | photo: Street View, Rightmove, university building photo (`reference/buildings`), other-side photos | OSM `building:levels` | lidar estimate (label it) |
| Roof form, ridge axis | Google sheet (look at the roof) | lidar interior columns, wide buildings only | same-terrace hint |
| Roof colour, material | Google sheet | street photo | hint (default tile) |
| Walls, openings, doors, bays | street photo, university building photo (`scripts/buildings.py`, campus buildings) | Google (wall colour, wings) | same-terrace hint |
| Where a university building's entrances are, and their names | `reference/portals` (`scripts/portals.py`), exact position | portal photo, then street photo | OSM `entrance` nodes, same-building hint |
| Ground surface: lawn, paving, drive, car park, path | Google sheet | university aerial, OSM surface and landuse | Geocraft default |
| Trees, canopy cover | Google sheet cover, lidar tree columns (kind 2, 3) | university aerial | none: never invent crowns |
| Building missing from OSM or lidar | photos or Google show it: build it anyway | lidar UNMAPPED lump | |

## Cautions
- Aerial lean: a tall roof sits a few blocks off its ground footprint. Judge a
  roof on the roof, a wall on a street photo.
- Lidar is a dated, filtered snapshot: cars and street furniture are absent, the
  rim reads low, ground_y is too low for a building on a bank
  (`rules/geocraft-accuracy.md`, `site/GEOCRAFT.txt`). Newer photos win; record the
  mismatch.
- A portal gives the door's position and name, not its look (door type, canopy, steps): read that from its photo or a street
  photo. A building with no portal can still have doors.
- Google tiles and Street View are look-only: view, write down what they show,
  never save, hash or commit them (`reference/SOURCES.txt`).
- Never researched: private interiors; back gardens come from the aerial or
  Google, not from photos over fences (`rules/frontage-and-evidence.md`).
