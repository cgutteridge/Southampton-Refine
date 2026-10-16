# Terraces: use the generator

Read before any terrace or Broadlands-type house build. Roof and fabric rules:
`site/CRAFTSMANSHIP.txt`.

Every Broadlands-type (Victorian/Edwardian) terrace is built by
`scripts/terrace.py`. Copy `scripts/build_broadlands_rd_14_24.py` for the next
terrace and change only the data:

- One build per whole terrace (every house between two gaps in the OSM
  roofs), not per pair.
- Party walls: squared columns, pitch 4 or 5 so the row keeps the real ~4.5 m
  frontage. Pick wall x's at the midpoints between OSM centroids and round;
  each house centre should land within ~1.5 of its OSM centroid.
- Front row per house from the OSM front edge (`front_row()`); floor `b` is
  the pristine pavement Y at the house (`pav_y()`).
- Door side alternates in pairs (doors share a party wall, bays share the
  next). Take it from the street photo; label it `hint` if unseen.
- Per-house `roof='granite'` for red clay tiles (aerial colour); default slate.
- Find the terrace ends first: `.venv/bin/python scripts/aerial_annot.py x0,z0,x1,z1 out.png`.
- Plot angle: `python3 scripts/geo.py slope --bearing …` or `--points x0,z0,x1,z1`
  gives `plot_slope=(dx,dz)`. Frontage pitch: `geo.py party --bbox …`.
- Per-house extras from evidence only: `wall` (render, `smooth_sandstone`).
  The garden extras (`front_boundary`, `shed`, `tree`) are not used in
  layered cells: gardens are ground, trees and decor passes.
- Pass every earlier build that touched the plots in `modifies`.

If something looks wrong, fix `terrace.py` and re-apply the same build name
(the backup stays the pre-build state). Never stack _b/_c patch builds.

Verify: readback, `osm_footprints.py check`, walks door to first floor and
door to back garden for every house, contact sheet (photo camera, front 3/4,
rear, top).
