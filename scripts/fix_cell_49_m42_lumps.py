#!/usr/bin/env python3
"""I-057 cell 49,-42 follow-up: Farm House (w173807219) rear door at (6291,44,-5305) opened onto the wall of the neighbouring
construction building w590171653; the rule is now in build_cell_49_m42_lumps.doors (rear door needs open ground). Walls it up."""
import argparse, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from site_kit import Plan, apply
import build_cell_49_m42_lumps as B
p = Plan('cell_49_m42_lumps_fix')
for y in (44, 45):
    p.set(6291, y, -5305, 'bricks')
ap = argparse.ArgumentParser(); ap.add_argument('--apply', action='store_true'); a = ap.parse_args()
apply(p, dry=not a.apply, modifies=B.MODIFIES + (B.NAME,))
