#!/usr/bin/env python3
"""Tile view PNGs into one labelled contact sheet, so a review reads ONE image
instead of opening every 1280x800 capture (token budget, 10 Oct 2026).

  python3 scripts/contact_sheet.py OUT.png in1.png in2.png ...

Open a single full-size view only when the sheet shows something worth a
closer look.
"""
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw

MAX_W = 1568      # widest image the model takes in without downscaling
LABEL_H = 18


def make_sheet(paths, out, cols=None):
    """Write a contact sheet of ``paths`` to ``out``.

    @param paths: image file paths (labelled by file stem)
    @param out: output PNG path
    @param cols: column count (default: 2 for <=4 images, else 3)
    @returns: output Path, or None when there are no images
    """
    paths = [Path(p) for p in paths]
    if not paths:
        return None
    cols = cols or (2 if len(paths) <= 4 else 3)
    rows = math.ceil(len(paths) / cols)
    tw = MAX_W // cols
    th = None
    tiles = []
    for p in paths:
        im = Image.open(p).convert('RGB')
        h = round(im.height * tw / im.width)
        th = th or h
        tiles.append((p.stem, im.resize((tw, h))))
    sheet = Image.new('RGB', (tw * cols, (th + LABEL_H) * rows), 'black')
    draw = ImageDraw.Draw(sheet)
    for i, (name, im) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + LABEL_H)
        draw.text((x + 4, y + 3), name, fill='white')
        sheet.paste(im, (x, y + LABEL_H))
    out = Path(out)
    sheet.save(out, optimize=True)
    return out


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        raise SystemExit(2)
    print(make_sheet(sys.argv[2:], sys.argv[1]))
