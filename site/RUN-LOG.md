# Run log

One block per finished cell, newest last. Written by the orchestrator via `scripts/site_status.py log`. Read with `site_status.py morning`.

## 2026-10-16 14:04 — cell 50,-42
- Did: (back-filled 16 Oct, built 15 Oct 19:12-19:20) 16 Welbeck Avenue houses from OSM footprints (27k blocks), door stoops fixed, trees re-run 127->121 crowns; all 61 doors in one walkable area. You walked the frontage: good enough.
- Layers now: ground ✓ trees ✓ decor ✓  (all applied)
- Look at: 6464,-5276: the door that was sealed, now stair stoops
- Problem / open: roofs are a colour hint, not matched to the aerial
- Marker: 48,-42 · lock: free

## 2026-10-16 14:04 — cell 49,-42
- Did: (back-filled 16 Oct, built 15 Oct 19:29-19:34) 19 buildings: Church Lane 8, Hilldown Road 8, garages, Oakdene Court; trees re-run 127->108 crowns; doors 45->81, none sealed. You walked Oakdene + garages: looks good.
- Layers now: ground ✓ trees ✓ decor ✓  (all applied)
- Look at: 6371-6390,-5290..-5265: Oakdene Court (4 levels, flat roof assumed)
- Look at: 6377-6392,-5254..-5244: garages (single storey, no aerial checked)
- Marker: 48,-42 · lock: free

## 2026-10-16 14:04 — cell 47,-45
- Did: (back-filled 16 Oct) 2 canopies built then one corrected: y54 diagonal canopy kept (building wrong, good enough); y58 canopy at way 444 removed because the registered Google aerial shows a tree, oak placed (extra_crowns override); 156 floating leaves removed; ground/trees/decor re-planned with the black-pixel fix and the plaza-lawn rule, decor 734 blocks, 0 mismatches.
- Layers now: ground ✓ trees ✓ decor ✓  (all applied)
- Look at: 6139,-5742: the oak by Building 2
- Look at: 6054-6074,-5712..-5682: lawn east of the big grey-roof building (was grey)
- Problem / open: Building 2 build overhangs the lawn strip (floors every 3 blocks to y71), strip stays mostly paved; logged in ISSUES.txt, needs the Building 2 east edge checked
- Problem / open: 5 other early cells' ground plans predate the aerial fix and likely have grey-over-lawn; re-plan one at a time
- Marker: 48,-42 · lock: free
