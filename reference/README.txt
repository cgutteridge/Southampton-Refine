REFERENCE IMAGERY
=================

Catalogue of sources (licences, zoom quirks): see SOURCES.txt.
How to log fetches / avoid token waste / privacy: see LOGGING.txt.
Index of assets: manifest.jsonl (append-only).

Drop ground-level photos in reference/photos/, aerial / orthophoto crops
in reference/aerial/, and OSM GeoJSON clips in reference/osm/ (from the
local Hampshire PBF via scripts/osm_extract.py). Prefer files named by
place + date, e.g.:

  civic-centre-west-facade-2024-06.jpg
  aerial-old-town-walls-su418112.png

Record OSGB or Minecraft coords in site/PLACES.txt for each active target.
Do not invent decorative detail that is not evidenced by a photo, survey, or
authoritative map. When sources disagree, prefer measured survey / LIDAR
footprint, then dated photography, then OSM.

Local tip: Uni Southampton XYZ aerial tiles at
  https://tiles.maps.southampton.ac.uk/aer/{z}/{x}/{y}.png
Zoom 18 = Hampshire Hub (OGL). Zoom 19 = Channel Coastal Observatory —
sharper, less coverage, more oblique over the river. See SOURCES.txt.
