# Southampton Refine

Tools and process for making the existing **Southampton2023** Geocraft LIDAR
world more accurate using ground photos, aerial imagery and surveys.

This project reuses the build kit and continuity lessons from
[Minecraft Magic](../Minecraft%20Magic) (plan → preview → apply → readback →
walk → views → records; one-builder lock; file-based handoff). It does **not**
carry over fictional districts, vibe pools or Enterprise work — only real-world
accuracy.

## World and coordinates

| | |
| --- | --- |
| World | `Southampton2023` (Geocraft UKDEFRA LIDAR + OSM) |
| Save | see `config/world.json` (Application Support; `geocraft/saves` is a symlink) |
| Grid | OSGB36 |
| Offsets | `OFFSET_E=436248`, `OFFSET_N=109608` in `config/map-maker-offsets.json` |
| Bounds (MC) | X 0…11604, Z −8666…0 |
| Sea level | Y 11 (Geocraft) |

```sh
python3 scripts/osgb.py info
python3 scripts/osgb.py to-mc 441900 112100    # Civic Centre approx
python3 scripts/osgb.py to-osgb 5652 -2492
```

## Layout

| Path | Role |
| --- | --- |
| `site/` | Process memory: QUEUE, PROCESS, PLACES, ISSUES, lock, handoff |
| `scripts/` | Kit, OSGB, walk, views, patrol, audit, MCP client |
| `config/` | World path + map-maker offsets (no POINTS blob) |
| `verification/site/` | Backups, cells archives, previews, patrol outputs |
| `reference/` | Local photos / aerial crops (gitignored content) |

## Cadence

1. `python3 scripts/site_handoff.py next` — boot prompt for the top QUEUE item  
2. Claim the world: `python3 scripts/site_lock.py claim <owner> "Q-nnn …"`  
3. Survey against evidence → plan with `site_kit.Plan` → preview →  
   `SITE_OWNER=<owner> … --apply` → readback → walk → contact-sheet views  
4. Update `PLACES` / `ISSUES` / `REVIEWS` / `TODO`; mark QUEUE done  
5. `python3 scripts/site_handoff.py end Q-nnn` — then a **new chat** for the next item  

Full rules: [site/PROCESS.txt](site/PROCESS.txt).

## MCP

Same Fabric MCP endpoints as Minecraft Magic:

| Connection | URL |
| --- | --- |
| World | `http://127.0.0.1:8765/mcp` |
| View | `http://127.0.0.1:8766/mcp` |

Open **Southampton2023** in a Fabric client that has the MCP mod (see open
issue I-001). Diagnostics:

```sh
python3 scripts/mcp.py tools/list
python3 scripts/mcp.py tools/call --port 8766 --tool client_status
```

## Wisdom kept (no town baggage)

- One builder at a time (`SITE_OWNER` + `site/LOCK.json`)
- Files are memory; one queue item per chat; hand off before context bloat
- Explicit air in plans; cells archive owns modifications
- Don’t regenerate terrain-reading plans to “fix” — write a new modify build
- Hop the player near fills so chunks load; restore game mode, don’t teleport home
- Posts must not float on bottom slabs; dry-run clash / protect checks
- Contact sheets for review; batch user asks

## First queue

See [site/QUEUE.txt](site/QUEUE.txt): set up Fabric MCP on this world, survey
Civic Centre, then prove the kit with a tiny evidence-based edit.
