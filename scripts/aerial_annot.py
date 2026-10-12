#!/usr/bin/env python3
"""Annotated aerial crop: z18 portswood mosaic + OSM outlines (way-id tails) + 10-block MC grid.

  .venv/bin/python scripts/aerial_annot.py x0,z0,x1,z1 out.png [scale] [mosaic.png] [extra.geojson]

mosaic defaults to the portswood z18 3x3; any mosaic-z18-NxN-centre-X-Y.png
works. extra.geojson (EPSG:27700) adds non-building outlines (parking etc.) in blue.
"""
import sys, math, subprocess, re, json
from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent))
from osgb import to_osgb
from osm_footprints import OSMIndex
from PIL import Image, ImageDraw
MOS=sys.argv[4] if len(sys.argv)>4 else 'reference/aerial/portswood-x-broadlands/mosaic-z18-3x3-centre-130063-87836.png'
_m=re.search(r'mosaic-z(\d+)-(\d+)x\d+-centre-(\d+)-(\d+)',MOS)
Z=int(_m[1]); _h=int(_m[2])//2; OX,OY=(int(_m[3])-_h)*256,(int(_m[4])-_h)*256
img=Image.open(MOS).convert('RGB')
def px(pts):
    inp=''.join(f'{e} {n}\n' for e,n in (to_osgb(x,z) for x,z in pts))
    out=subprocess.run(['gdaltransform','-s_srs','EPSG:27700','-t_srs','EPSG:4326'],input=inp.encode(),capture_output=True,check=True).stdout.decode().split('\n')
    res=[]
    for l in out:
        if not l.strip(): continue
        lon,lat=map(float,l.split()[:2]); n=2**Z
        X=(lon+180)/360*n*256; Y=(1-math.log(math.tan(math.radians(lat))+1/math.cos(math.radians(lat)))/math.pi)/2*n*256
        res.append((X-OX,Y-OY))
    return res
x0,z0,x1,z1=map(int,sys.argv[1].split(',')); S=int(sys.argv[3]) if len(sys.argv)>3 else 4
corners=px([(x0,z0),(x1,z0),(x0,z1),(x1,z1)])
xs=[c[0] for c in corners]; ys=[c[1] for c in corners]
box=(min(xs),min(ys),max(xs),max(ys))
crop=img.crop(tuple(int(v) for v in box)); W,H=crop.size
crop=crop.resize((W*S,H*S),Image.LANCZOS); d=ImageDraw.Draw(crop)
def tr(p): return ((p[0]-int(box[0]))*S,(p[1]-int(box[1]))*S)
for ring,p in OSMIndex().buildings:
    r=ring[0]
    if not any(x0<=x<=x1 and z0<=z<=z1 for x,z in r): continue
    pp=[tr(q) for q in px(r)]; d.line(pp+[pp[0]],fill=(255,0,0),width=1)
    c=tr(px([(sum(v[0] for v in r[:-1])/(len(r)-1),sum(v[1] for v in r[:-1])/(len(r)-1))])[0]); d.text(c,p.get('osm_way_id','')[-3:],fill=(255,255,0))
if len(sys.argv)>5:
    from osgb import load_offsets; o=load_offsets()
    for f in json.load(open(sys.argv[5]))['features']:
        g=f['geometry']; pr=f['properties']
        if not g or g['type'] not in ('Polygon','MultiPolygon') or pr.get('building'): continue
        for poly in ([g['coordinates']] if g['type']=='Polygon' else g['coordinates']):
            r=[(e-o['OFFSET_E'],o['OFFSET_N']-n) for e,n in poly[0]]
            if not any(x0<=x<=x1 and z0<=z<=z1 for x,z in r): continue
            pp=[tr(q) for q in px(r)]; d.line(pp,fill=(60,140,255),width=2)
            lab=pr.get('amenity') or pr.get('landuse') or pr.get('natural') or pr.get('leisure') or ''
            d.text(pp[0],lab[:4]+(pr.get('osm_way_id') or '')[-3:],fill=(60,140,255))
# grid every 10 blocks in x (yellow) labels
for gx in range(x0-x0%10+10,x1,10):
    a,b=px([(gx,z0),(gx,z1)]); d.line([tr(a),tr(b)],fill=(0,255,255),width=1); d.text(tr(a),str(gx),fill=(0,255,255))
for gz in range(z0-z0%10+10,z1,10):
    a,b=px([(x0,gz),(x1,gz)]); d.line([tr(a),tr(b)],fill=(0,255,0),width=1); d.text(tr(a),str(gz),fill=(0,255,0))
crop.save(sys.argv[2]); print(crop.size)
