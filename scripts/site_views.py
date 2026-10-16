#!/usr/bin/env python3
"""Capture client views of named Southampton places, restore game mode after.

Views are registered in VIEWS as name -> (eye_pos, look_at). Start empty;
add entries in place briefs as you survey.

  python3 scripts/site_views.py [--hires | --midres] [prefix] name ...

Default capture is low-res (downscale 4) to save tokens; use --hires (full
size) for sign-off evidence or fine detail, --midres (downscale 2) between.
"""
import base64
import re
import sys
import time
from pathlib import Path

from contact_sheet import make_sheet
from mc_paced import D, UUID, Paced, xyz

RES = {'--hires': 1, '--midres': 2}
LOWRES = 4


def pop_downscale(args):
    """Remove resolution flags from args and return the view_capture downscale.

    @param args: argv list, edited in place
    @returns: downscale factor (1 = full size)
    """
    found = [a for a in args if a in RES]
    for a in found:
        args.remove(a)
    return min((RES[a] for a in found), default=LOWRES)


OUT = Path(__file__).resolve().parent.parent / 'verification/site/views'

# name -> ([x,y,z] eye, [x,y,z] look-at). Fill as places are surveyed.
VIEWS = {
    # Q-024 Highfield campus B35 (David Kiddle) + grounds: photo camera, 3/4s, top
    'b35-photo-249': ([6396, 52, -5526], [6421, 52, -5510]),
    'b35-ne': ([6430, 57, -5488], [6395, 54, -5505]),
    'b35-sw-carpark': ([6342, 62, -5466], [6385, 54, -5505]),
    'b35-se-yard': ([6436, 58, -5452], [6400, 52, -5490]),
    'b35-top': ([6385, 125, -5494], [6385, 50, -5493]),
    # Q-025 Highfield campus neighbours of B35 (B30/B29, B37, Early Years, Estates)
    'q025-photo-121': ([6322, 55, -5558], [6345, 56, -5547]),
    'q025-photo-241': ([6308, 55, -5462], [6300, 57, -5485]),
    'q025-photo-353': ([6283, 56, -5514], [6270, 58, -5535]),
    'q025-b30-nw': ([6345, 80, -5600], [6395, 65, -5550]),
    'q025-ey-estates': ([6420, 66, -5420], [6365, 52, -5465]),
    'q025-top-west': ([6322, 140, -5512], [6322, 50, -5511]),
    'q025-top-east': ([6412, 140, -5530], [6412, 50, -5529]),
    # Q-026 grounds around B30/B37: colonnade + wall, forecourt stands, SW verge + stair tower
    'q026-b30-colonnade': ([6392, 53, -5521], [6404, 53, -5531]),
    'q026-b37-tower': ([6300, 56, -5470], [6316, 60, -5484]),
    # Q-027 campus C1: Chemistry B27 (flues) + B25/B26/B28; photo = commons-51225046 (looking W)
    'q027-photo-chem': ([6486, 50, -5543], [6455, 60, -5562]),
    'q027-se': ([6505, 78, -5640], [6440, 56, -5570]),
    'q027-nw': ([6395, 80, -5515], [6450, 56, -5580]),
    'q027-top': ([6432, 150, -5575], [6432, 50, -5574]),
    # Q-028 campus C2: Hartley Library, B34, B57, Jubilee Sports (+2025 extension)
    'q028-photo-lib': ([6251, 57, -5623], [6300, 58, -5630]),
    'q028-photo-b34': ([6354, 55, -5549], [6335, 57, -5575]),
    'q028-photo-jubilee': ([6251, 52, -5403], [6240, 58, -5460]),
    'q028-photo-sports': ([6301, 55, -5483], [6265, 56, -5500]),
    'q028-top-lib': ([6330, 160, -5620], [6330, 50, -5619]),
    'q028-top-sports': ([6255, 150, -5480], [6255, 50, -5479]),
    # Q-052 B57 Students' Union Retail Centre (fringe footprint finish)
    'q052-top-b57': ([6237, 130, -5564], [6237, 50, -5563]),
    'q052-se-b57': ([6265, 65, -5545], [6235, 58, -5565]),
    # Q-054 micro parcels: bike shed w171869344 + roof canopy w391790374 (aerial z18 b35)
    'q054-top-bikeshed': ([6234, 95, -5545], [6234, 50, -5544]),
    'q054-top-canopy': ([6192, 90, -5566], [6192, 50, -5565]),
    'q054-ne-bikeshed': ([6248, 62, -5538], [6234, 58, -5545]),
    'q054-sw-canopy': ([6180, 62, -5575], [6192, 58, -5566]),
    # Q-029 campus C3: West Building B40 (old Union), Staff Club B38, SUSU B42
    'q029-photo-west': ([6236, 57, -5600], [6195, 60, -5610]),
    'q029-photo-susu': ([6203, 56, -5569], [6175, 52, -5545]),
    'q029-top': ([6185, 160, -5595], [6185, 50, -5594]),
    'q029-b40-lawn': ([6245, 60, -5582], [6195, 60, -5608]),
    'q029-sw': ([6110, 75, -5470], [6180, 55, -5560]),
    # Q-030 campus C4: engineering quarter + cleared Faraday Tower site
    'q030-photo-lanchester': ([6401, 53, -5642], [6405, 56, -5665]),
    'q030-faraday-site': ([6460, 56, -5625], [6485, 50, -5645]),
    'q030-top': ([6440, 160, -5715], [6440, 50, -5714]),
    'q030-se': ([6520, 80, -5800], [6430, 58, -5700]),
    # Q-031 campus C5: Life Sciences B85, B32, Nightingale B67, B20
    'q031-photo-b85': ([6290, 58, -5835], [6325, 64, -5800]),
    'q031-photo-b67': ([6215, 58, -5860], [6245, 63, -5815]),
    'q031-top': ([6300, 165, -5805], [6300, 50, -5804]),
    'q031-ne': ([6385, 85, -5735], [6300, 62, -5800]),
    # Q-032 campus C6: Centenary B100, Nuffield Theatre, Law, B2, Annex
    'q032-photo-centenary': ([6168, 58, -5800], [6170, 70, -5830]),
    'q032-photo-nuffield': ([6235, 58, -5700], [6200, 62, -5730]),
    'q032-top': ([6175, 165, -5775], [6175, 50, -5774]),
    'q032-b100-view': ([6175, 95, -5835], [6215, 60, -5735]),
    # Q-033 campus C7: Mountbatten B53, Zepler B59, Gower B60, B1, B16
    'q033-photo-zepler': ([6200, 59, -5850], [6170, 64, -5885]),
    'q033-photo-gower': ([6240, 59, -5945], [6200, 64, -5932]),
    'q033-top': ([6200, 165, -5905], [6200, 50, -5904]),
    'q033-nw': ([6080, 90, -5830], [6160, 66, -5900]),
    # Q-034 campus C8: Shackleton B44, Physics B5/B46, Psychology 44A
    'q034-photo-shackleton': ([6120, 56, -5530], [6090, 62, -5560]),
    'q034-top': ([6060, 160, -5590], [6060, 50, -5589]),
    'q034-gardens': ([6110, 64, -5650], [6050, 60, -5590]),
    # Q-035 campus C9: Maths B54 tower, Murray B58, Turner Sims B52, Health B48, B39, B56
    'q035-photo-maths': ([6140, 57, -5735], [6090, 70, -5765]),
    'q035-photo-turnersims': ([6140, 56, -5695], [6100, 56, -5722]),
    'q035-top': ([6075, 165, -5765], [6075, 50, -5764]),
    'q035-sw': ([6000, 85, -5650], [6080, 62, -5760]),
    # Q-036 campus C10: uni houses — Chamberlain Rd 8-58, Hartley Ave 17-31, University Rd 26/28
    'q036-photo-chamberlain': ([6058, 53, -5469], [6082, 54, -5451]),
    'q036-hartley': ([6445, 51, -5450], [6430, 53, -5470]),
    'q036-top-chamberlain': ([6080, 140, -5475], [6080, 50, -5474]),
    'q036-backs': ([6090, 75, -5520], [6070, 55, -5480]),
    # Q-037 Faraday site cleared + campus overview
    'q037-faraday-site': ([6545, 62, -5600], [6495, 48, -5650]),
    'q037-campus-ne': ([6560, 130, -5380], [6250, 55, -5680]),
    'q037-campus-sw': ([5940, 130, -5990], [6250, 55, -5680]),
    'q037-campus-top': ([6250, 330, -5680], [6250, 50, -5679]),
    # Seed Civic Centre aerial (approx) — refine after Q-002 survey
    'civic-aerial': ([5652, 90, -2492], [5652, 40, -2492]),
    # Q-003 pipeline proof: granite kerb on Portswood Rd SW edge near Broadlands
    'portswood-kerb-proof-se': ([7102, 30, -5518], [7093, 26, -5525]),
    'portswood-kerb-proof-nw': ([7086, 30, -5532], [7093, 26, -5525]),
    'portswood-kerb-proof-top': ([7093, 42, -5525], [7093, 26, -5525]),
    # Q-004 streetscape coverage
    'portswood-r0-se': ([7110, 32, -5510], [7095, 26, -5525]),
    'portswood-r0-nw': ([7080, 32, -5540], [7095, 26, -5525]),
    'portswood-r0-top': ([7095, 55, -5525], [7095, 26, -5525]),
    # Q-010 first terrace façade (Portswood Rd SW)
    'portswood-facade1-se': ([7105, 32, -5518], [7088, 30, -5530]),
    'portswood-facade1-street': ([7100, 30, -5530], [7088, 30, -5530]),
    'portswood-facade1-top': ([7088, 48, -5530], [7088, 30, -5530]),
    # Q-013 streetscape width + kerbs
    'portswood-q013-se': ([7112, 34, -5508], [7097, 26, -5521]),
    'portswood-q013-nw': ([7082, 34, -5536], [7097, 26, -5521]),
    'portswood-q013-top': ([7097, 58, -5521], [7097, 26, -5521]),
    # Q-012 next terrace façade (SW of façade_1b)
    'portswood-facade2-se': ([7095, 32, -5525], [7073, 30, -5535]),
    'portswood-facade2-street': ([7090, 30, -5535], [7073, 30, -5535]),
    'portswood-facade2-top': ([7073, 48, -5535], [7073, 30, -5535]),
    # Q-014 Broadlands Rd 20+22 whole properties
    'broadlands-20-22-street': ([7071, 30, -5531], [7101, 32, -5535]),
    'broadlands-20-22-front': ([7104, 31, -5524], [7101, 32, -5538]),
    'broadlands-20-22-top': ([7101, 55, -5545], [7101, 30, -5545]),
    # Q-016 Broadlands Rd 24+26 whole properties (photo camera + plot top)
    'broadlands-24-26-street': ([7071, 30, -5531], [7087, 32, -5538]),
    'broadlands-24-26-front': ([7090, 31, -5528], [7087, 32, -5542]),
    'broadlands-24-26-top': ([7087, 55, -5548], [7087, 30, -5548]),
    # Q-017 Broadlands Rd 28+30 whole properties (photo camera + plot top)
    'broadlands-28-30-street': ([7071, 30, -5531], [7078, 32, -5542]),
    'broadlands-28-30-front': ([7080, 31, -5532], [7078, 32, -5546]),
    'broadlands-28-30-top': ([7078, 55, -5552], [7078, 30, -5552]),
    # Q-018 Broadlands Rd 26-36 terrace (terrace.py): photo camera, front 3/4, rear, top
    'broadlands-26-36-street': ([7071, 29, -5531], [7099, 31, -5521]),
    'broadlands-26-36-front': ([7062, 34, -5527], [7078, 31, -5543]),
    'broadlands-26-36-front-e': ([7096, 33, -5524], [7078, 31, -5542]),
    'broadlands-26-36-rear': ([7072, 42, -5584], [7077, 32, -5553]),
    'broadlands-26-36-top': ([7077, 80, -5558], [7077, 30, -5558]),
    # Broadlands Rd 14-24 terrace A (+ whole north side 14-36)
    'broadlands-14-24-front': ([7090, 34, -5514], [7106, 31, -5532]),
    'broadlands-14-24-front-e': ([7126, 33, -5512], [7106, 31, -5530]),
    'broadlands-14-36-long': ([7128, 31, -5512], [7080, 33, -5540]),
    'broadlands-14-24-rear': ([7104, 42, -5578], [7106, 31, -5545]),
    'broadlands-14-36-top': ([7092, 95, -5552], [7092, 30, -5552]),
    # Q-019 Broadlands Rd 2-12 (terrace C); photo = kartaview-1471277737 camera
    'broadlands-2-12-photo': ([7134, 26, -5505], [7184, 27, -5485]),
    'broadlands-2-12-front': ([7114, 34, -5505], [7135, 31, -5520]),
    'broadlands-2-12-front-e': ([7158, 33, -5503], [7135, 31, -5520]),
    'broadlands-2-12-rear': ([7135, 42, -5577], [7135, 30, -5540]),
    'broadlands-2-12-top': ([7135, 95, -5535], [7135, 30, -5535]),
    # Q-020 Broadlands Rd 40-46 (post-war flats); photo = kartaview-1471277609 camera
    'broadlands-40-46-photo': ([7035, 31, -5546], [7100, 32, -5522]),
    'broadlands-40-46-front': ([7046, 35, -5538], [7051, 33, -5556]),
    'broadlands-40-46-front-w': ([7028, 34, -5544], [7050, 34, -5558]),
    'broadlands-40-46-rear': ([7052, 44, -5596], [7052, 33, -5562]),
    'broadlands-40-46-top': ([7052, 95, -5568], [7052, 30, -5568]),
    # Q-021 Broadlands Rd 48-54 (Victorian pair + hipped semi); photo = kartaview-1471277609
    'broadlands-48-54-photo': ([7035, 31, -5546], [7100, 32, -5522]),
    'broadlands-48-54-front': ([7030, 35, -5540], [7029, 35, -5562]),
    'broadlands-48-54-front-w': ([7008, 34, -5550], [7036, 35, -5562]),
    'broadlands-48-54-rear': ([7030, 45, -5612], [7030, 34, -5570]),
    'broadlands-48-54-top': ([7030, 95, -5578], [7030, 30, -5578]),
    # Q-022 Broadlands Rd 56-62 (two front-gabled pairs); photo = kartaview-1471277529 (heading 112)
    'broadlands-56-62-photo': ([6980, 32, -5569], [7036, 33, -5546]),
    'broadlands-56-62-front': ([7008, 36, -5553], [7008, 37, -5575]),
    'broadlands-56-62-front-w': ([6988, 35, -5558], [7012, 37, -5574]),
    'broadlands-56-62-rear': ([7008, 46, -5614], [7010, 36, -5580]),
    'broadlands-56-62-top': ([7010, 95, -5585], [7010, 30, -5585]),
    # Q-045 ring-1 lanes / driveways (broadlands_ring1_lanes)
    'q045-top-harrison': ([7150, 140, -5705], [7150, 30, -5704]),
    'q045-top-portswood': ([7235, 130, -5480], [7235, 20, -5479]),
    'q045-driveway-w178001289': ([7066, 40, -5712], [7130, 31, -5686]),
    # Q-046 ring-1 main roads (broadlands_ring1_roads)
    'q046-top-portswood-junction': ([7198, 130, -5461], [7198, 25, -5460]),
    'q046-top-mayfield-harrison': ([7150, 130, -5580], [7150, 25, -5579]),
    'q046-street-portswood-n': ([7230, 32, -5440], [7198, 32, -5465]),
}


def main():
    """Capture named views and write a contact sheet.

    @returns: None
    """
    args = sys.argv[1:]
    downscale = pop_downscale(args)
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
            r = v.call('view_capture', {'downscale': downscale, 'close_screen': True})
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
