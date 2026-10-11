#!/usr/bin/env python3
"""Capture client views of named Southampton places, restore game mode after.

Views are registered in VIEWS as name -> (eye_pos, look_at). Start empty;
add entries in place briefs as you survey.

  python3 scripts/site_views.py [prefix] name ...
"""
import base64
import re
import sys
import time
from pathlib import Path

from contact_sheet import make_sheet
from mc_paced import D, UUID, Paced, xyz

OUT = Path(__file__).resolve().parent.parent / 'verification/site/views'

# name -> ([x,y,z] eye, [x,y,z] look-at). Fill as places are surveyed.
VIEWS = {
    # Seed Civic Centre aerial (approx) — refine after Q-002 survey
    'civic-aerial': ([5652, 90, -2492], [5652, 40, -2492]),
}


def main():
    """Capture named views and write a contact sheet.

    @returns: None
    """
    args = sys.argv[1:]
    prefix = args.pop(0) if args and args[0] not in VIEWS else ''
    names = args or list(VIEWS)
    if not names:
        raise SystemExit('No views registered yet — add entries to site_views.VIEWS')
    OUT.mkdir(parents=True, exist_ok=True)
    w, v = Paced(), Paced(8766)
    shots = []
    info = w.text('player_get_info', {'uuid': UUID})
    num = lambda k: float(re.search(rf'{k}: (-?[\d.]+)', info).group(1))
    mode = re.search(r'gameMode: (\w+)', info).group(1)
    w.call('player_set_gamemode', {'uuid': UUID, 'gamemode': 'spectator'})
    try:
        for name in names:
            pos, look = VIEWS[name]
            w.call('entity_teleport', {
                'uuid': UUID, 'dimension': D,
                'position': xyz(pos), 'facing': xyz(look),
            })
            time.sleep(4)
            r = v.call('view_capture', {'downscale': 2, 'close_screen': True})
            for b in r['content']:
                if b['type'] == 'image':
                    path = OUT / f'{prefix}{name}.png'
                    path.write_bytes(base64.b64decode(b['data']))
                    shots.append(path)
                    print(path, flush=True)
    finally:
        w.call('player_set_gamemode', {'uuid': UUID, 'gamemode': mode})
    sheet = make_sheet(shots, OUT / f'{prefix or "views-"}contact.png')
    if sheet:
        print(f'CONTACT SHEET: {sheet}  (read this one image; open single views only for detail)')


if __name__ == '__main__':
    main()
