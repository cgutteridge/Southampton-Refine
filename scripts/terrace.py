"""Victorian bay-fronted terrace generator: whole properties for site_kit Plans.

Written 11 Oct 2026 (Claude) after the Q-014..Q-017 Cursor builds failed visual
review (jagged OSM extrusions, slab roofs that read as flat, no bays). One
module so every Broadlands-type terrace is built the same way.

Model (Minecraft-squared, not diamond-traced):
  - A terrace on a diagonal street is a row of axis-aligned houses. Each house
    spans party wall Pw..Pe (shared columns, 4 or 5 blocks pitch so the row
    keeps up with the real ~4.5 m frontage) and its front wall row `f`
    steps back to follow the street line.
  - Main block rows f..f-7, two storeys: floor b, ground-floor air b+1..b+3,
    first floor b+4, first-floor air b+5..b+6, eaves stair at b+7, ridge b+10
    (45 deg slate, the real pitch of these roofs; ridge parallel to street).
  - Two-storey rear outrigger (rows f-8..f-11) on the door side, own gable
    roof running back from the main roof; one-block side return beside it.
  - Ground-floor bay (glass, plinth, tiled hood) and door with a white hood.
  - Inside: floors + one straight stair along the hall, nothing else.
  - Front garden to the back of the pavement; back garden to the rear lane.
    Back gardens follow a block stair (see snap_slope); the houses stay squared.
The roof is one heightfield over the whole terrace (max of every gable), so
stepped neighbours meet with brick gable steps instead of holes.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# Broadlands Road north side, nos 2–36. OSM long edges are 21.4–22.5° east of
# north; aerial fence lines on q041-aerial-gardens.png run the same way.
# Nearest even stair (not a 15° Bresenham) is 1 east per 3 north.
BROADLANDS_N_SLOPE = (1, -3)

# |dx|:|dz| in {0, 1:4, 1:3, 1:2, 1:1} and the swapped mirrors, signs applied later.
_FRIENDLY = ((0, 1), (1, 4), (1, 3), (1, 2), (1, 1), (2, 1), (3, 1), (4, 1), (1, 0))


def snap_slope(dx: float, dz: float) -> tuple[int, int]:
    """Snap a plot direction to an even block stair.

    Allowed slopes are 0, 1:4, 1:3, 1:2, 1:1 and their mirrors (about 0, 14,
    18, 27, 45, 63, 72, 76 and 90 degrees). Exact 15° steps are uneven on a
    block grid, so they are not candidates.

    @param dx: easting of the direction from the house toward the rear boundary
    @param dz: Minecraft dz of that same direction (negative is north)
    @returns: (sx, sz) in lowest terms, signs matching dx and dz
    """
    if dx == 0 and dz == 0:
        raise ValueError('plot direction is zero')
    ang = math.atan2(dx, dz)
    best, best_d = (0, 1), 1e9
    for a, b in _FRIENDLY:
        sxs = (0,) if a == 0 else (a, -a)
        szs = (0,) if b == 0 else (b, -b)
        for sx in sxs:
            for sz in szs:
                if sx == 0 and sz == 0:
                    continue
                d = abs(math.atan2(sx, sz) - ang)
                d = min(d, 2 * math.pi - d)
                if d < best_d:
                    best_d, best = d, (sx, sz)
    return best


def line_x(x0: int, z0: int, z: int, slope: tuple[int, int]) -> int:
    """Column where the party line through (x0, z0) sits at row z.

    Toward the rear the line steps `slope` evenly (a run of blocks, then one
    column over). On the street side of z0 it stays on x0, so the squared
    house wall remains the boundary.

    @param x0: party-wall column at the anchor
    @param z0: anchor row (back of the yard wall)
    @param z: row to evaluate
    @param slope: (dx, dz) from snap_slope, pointing toward the rear
    @returns: block column of the line
    """
    sx, sz = slope
    if sz == 0 or (z - z0) * sz < 0:
        return x0
    return x0 + (sx * (z - z0)) // sz


def passage_xs(z: int, west_pe: int, west_rear: int, east_pw: int, east_rear: int,
               slope: tuple[int, int]) -> range:
    """Columns strictly between two terraces' outer plot lines at row z.

    @param z: row
    @param west_pe: east end-wall column of the western terrace
    @param west_rear: back-wall row of that end house
    @param east_pw: west end-wall column of the eastern terrace
    @param east_rear: back-wall row of that end house
    @param slope: shared plot slope
    @returns: open interval between the two lines (empty if they touch)
    """
    xl = line_x(west_pe, west_rear, z, slope)
    xr = line_x(east_pw, east_rear, z, slope)
    if xr < xl:
        xl, xr = xr, xl
    return range(xl + 1, xr)

SLATE = 'deepslate_tile'
ROOF_FULL = {SLATE: 'deepslate_tiles', 'granite': 'granite'}   # roof material -> full block
TILE = 'granite'           # bay hoods: red-brown tile
WHITE = 'smooth_quartz'
FLOOR = 'spruce_planks'


@dataclass
class House:
    no: str
    pw: int                 # west party/end wall column
    pe: int                 # east party/end wall column
    f: int                  # front wall row (z)
    b: int                  # ground-floor floor Y (= garden/pavement level)
    door: str               # 'W' or 'E': door side (outrigger on the same side)
    wall: str = 'bricks'
    door_block: str = 'spruce_door'
    front_boundary: str = 'wall'     # 'wall' | 'hedge'
    shed: bool = False
    tree: bool = False
    roof: str = SLATE                # 'granite' = red clay tiles (aerial colour)
    out_storeys: int = 2             # 1 = single-storey rear outrigger (LIDAR), gable at b+4
    plot: tuple | None = None        # (dx, dz) party line toward the rear; None = terrace slope
    # filled in by layout()
    cols: list = field(default_factory=list)

    @property
    def inner(self):
        return list(range(self.pw + 1, self.pe))

    @property
    def door_col(self):
        return self.inner[0] if self.door == 'W' else self.inner[-1]

    @property
    def bay_cols(self):
        return [c for c in self.inner if c != self.door_col]

    @property
    def outrigger(self):
        """(x0, x1) wall columns of the outrigger (inclusive)."""
        n = 3 if len(self.inner) == 4 else 2      # 4 cols for 5-pitch, 3 for 4-pitch
        return (self.pe - n, self.pe) if self.door == 'E' else (self.pw, self.pw + n)

    @property
    def side_return(self):
        o0, o1 = self.outrigger
        return [c for c in self.inner if not (o0 <= c <= o1)]

    def rows_main(self):
        return range(self.f - 7, self.f + 1)

    def rows_out(self):
        return range(self.f - 11, self.f - 7)


def _stair(mat, facing, half='bottom'):
    return f'{mat}_stairs[facing={facing},half={half}]'


class Terrace:
    def __init__(self, plan, houses, ground_y, pav_row, lane_row, x_range, pristine=None,
                 plot_slope=(0, -1), gore=None, gore_reach=18, street=None, restore_west=False):
        """ground_y(x,z)->int pristine ground; pav_row(x)->northmost pavement row;
        lane_row(x)->southmost rear-lane row; x_range=(x0,x1) columns this build owns.

        plot_slope is the back-garden party line (houses stay squared). gore is
        'E', 'W' or 'EW': unowned non-street cells beside that end, out to the
        lane, are given to the end house. restore_west keeps a lawn on the
        columns the shear left west of the new plot, so a neighbour parcel
        that those columns belong to stays touched.
        """
        self.p, self.H = plan, houses
        self.ground_y, self.pav_row, self.lane_row = ground_y, pav_row, lane_row
        self.x0, self.x1 = x_range
        self.pristine = pristine
        self.plot_slope = plot_slope
        self.gore, self.gore_reach, self.street = gore, gore_reach, street
        self.restore_west = restore_west
        self.walls = {}      # (x,z) -> (house, material)
        self.roof = {}       # (x,z) -> (h, facing|None, house)
        self._lane = {}
        self.plots = None    # (x, z) -> house, set by build()
        self.gore_cells = set()

    # --- helpers -------------------------------------------------------------
    def owner(self, x, z):
        """House whose plot contains column (x,z) (party columns -> west house)."""
        for h in self.H:
            if h.pw <= x < h.pe or (x == h.pe and h is self.H[-1]):
                return h
        return None

    def front_row(self, x):
        h = self.owner(x, 0)
        return h.f

    def set(self, x, y, z, s):
        self.p.set(x, y, z, s)

    # --- plot geometry (houses squared; back gardens follow plot_slope) ------
    def slope_of(self, h):
        """Party-line step for one house, toward the rear boundary."""
        return h.plot if h.plot is not None else self.plot_slope

    def rear_z(self, h):
        """Back wall of the outrigger. The garden stair starts beyond this row."""
        return h.f - 11

    def lane(self, x):
        """Cached lane_row, or None where the helper cannot see a lane."""
        if x not in self._lane:
            try:
                self._lane[x] = self.lane_row(x)
            except SystemExit:
                self._lane[x] = None
        return self._lane[x]

    def _shared_anchor(self, left, right, slope):
        a, b = self.rear_z(left), self.rear_z(right)
        if slope[1] < 0:
            return min(a, b)
        if slope[1] > 0:
            return max(a, b)
        return a

    def _bound_x(self, h, z, side):
        """Column of h's west or east plot line at row z."""
        i, sl = self.H.index(h), self.slope_of(h)
        if side == 'W' and i > 0 and self.H[i - 1].pe == h.pw and self.slope_of(self.H[i - 1]) == sl:
            z0 = self._shared_anchor(self.H[i - 1], h, sl)
            return line_x(h.pw, z0, z, sl)
        if side == 'E' and i + 1 < len(self.H) and h.pe == self.H[i + 1].pw and self.slope_of(self.H[i + 1]) == sl:
            z0 = self._shared_anchor(h, self.H[i + 1], sl)
            return line_x(h.pe, z0, z, sl)
        x0 = h.pw if side == 'W' else h.pe
        return line_x(x0, self.rear_z(h), z, sl)

    def span(self, h, z):
        """Columns of h's plot at row z. The shared east line belongs to the next house."""
        xw, xe = self._bound_x(h, z, 'W'), self._bound_x(h, z, 'E')
        if xw > xe:
            xw, xe = xe, xw
        return range(xw, xe + 1 if h is self.H[-1] else xe)

    def _on_fence_line(self, h, x, z):
        """True if (x,z) carries h's party fence: its west line, the last house's east line,
        and one join post per step so the stepped runs meet edge to edge, not at a corner.
        Join posts sit inside h's own plot, so neighbours never fence the same column twice."""
        xs = list(self.span(h, z))
        if not xs or x not in xs:
            return False
        if x == xs[0] or (h is self.H[-1] and x == xs[-1]):
            return True
        near = (z - 1, z + 1)
        west = self._bound_x(h, z, 'W')
        if west < x <= max(self._bound_x(h, zz, 'W') for zz in near):
            return True
        if h is self.H[-1]:
            east = self._bound_x(h, z, 'E')
            return min(self._bound_x(h, zz, 'E') for zz in near) <= x < east
        return False

    def _back_garden(self, h):
        """Back-garden columns (not the squared yard), clipped to the lane."""
        sl = self.slope_of(h)
        step = -1 if sl[1] <= 0 else 1
        cells, z = [], self.rear_z(h) + step
        for _ in range(64):
            hit = False
            for x in self.span(h, z):
                lane = self.lane(x)
                if lane is None:
                    continue
                if step < 0 and z <= lane:
                    continue
                if step > 0 and z >= lane:
                    continue
                cells.append((x, z))
                hit = True
            if not hit:
                break
            z += step
        return cells

    def _column_cells(self, h):
        """Squared house + front garden, then the angled back garden."""
        cells = []
        for x in self.span(h, self.rear_z(h)):
            try:
                z_front = self.pav_row(x) - 1
            except SystemExit:
                continue
            cells.extend((x, z) for z in range(self.rear_z(h), z_front + 1))
        cells.extend(self._back_garden(h))
        return cells

    def _fill_gore(self, plots):
        """Give the end house the non-street wedge beside its plot, out to the lane."""
        from collections import deque
        sides = self.gore or ''
        q = deque()
        if 'E' in sides:
            h = self.H[-1]
            for (x, z), hh in plots.items():
                if hh is h and z < self.rear_z(h):
                    q.append((x, z, 0, h, 1))
        if 'W' in sides:
            h = self.H[0]
            for (x, z), hh in plots.items():
                if hh is h and z < self.rear_z(h):
                    q.append((x, z, 0, h, -1))
        seen = set(plots)
        while q:
            x, z, dist, h, dx = q.popleft()
            for nx, nz, nd in ((x + dx, z, dist + 1), (x, z - 1, dist + 1), (x, z + 1, dist + 1)):
                if nd > self.gore_reach or (nx, nz) in seen or nz >= self.rear_z(h):
                    continue
                if self.street(nx, nz):
                    continue
                end = self._bound_x(h, nz, 'E' if dx > 0 else 'W')
                if dx > 0 and nx <= end:
                    continue
                if dx < 0 and nx >= end:
                    continue
                seen.add((nx, nz))
                plots[(nx, nz)] = h
                self.gore_cells.add((nx, nz))
                q.append((nx, nz, nd, h, dx))

    def _compute_plots(self):
        plots = {}
        for h in self.H:
            for c in self._column_cells(h):
                plots[c] = h
        if self.gore and self.street:
            self._fill_gore(plots)
        return plots

    def _lay(self, h, x, z):
        y = self.surface_y(h, x, z)
        for yy in range(h.b - 2, y):
            self.set(x, yy, z, 'dirt')
        self.set(x, y, z, 'grass_block')
        for yy in range(y + 1, h.b + 16):
            self.set(x, yy, z, 'air')

    # --- 1. ground: clear the plot volume, lay garden surfaces ----------------
    def ground(self):
        if self.plots is None:
            self.plots = self._compute_plots()
        for (x, z), h in self.plots.items():
            self._lay(h, x, z)

    def surface_y(self, h, x, z):
        """Front garden and yard at floor level; lawn steps up gently toward the
        rear lane following the pristine LIDAR ground (never more than +3)."""
        if z >= h.f - 13:
            return h.b
        n = (h.f - 14) - z                    # rows into the lawn
        want = min(self.ground_y(x, z) - 1, h.b + 3)
        return max(h.b, min(want, h.b + 1 + n // 6))

    # --- 2. house shells -----------------------------------------------------
    def shells(self):
        for h in self.H:
            o0, o1 = h.outrigger
            for z in h.rows_main():
                for x in range(h.pw, h.pe + 1):
                    if x in (h.pw, h.pe) or z in (h.f, h.f - 7):
                        self.walls[(x, z)] = self._mat(h, x, z)
            for z in h.rows_out():
                for x in range(o0, o1 + 1):
                    if x in (o0, o1) or z == h.f - 11:
                        self.walls[(x, z)] = self._mat(h, x, z)
        for (x, z), mat in self.walls.items():
            hs = [h for h in self.H if self._covers(h, x, z)]
            b = min(h.b for h in hs)
            top = b + max(self._wall_h(h, x, z) for h in hs)
            for y in range(b - 1, top + 1):
                self.set(x, y, z, mat if y >= b else 'stone')
        # floors + interior air (+ attic air up to the roof)
        for h in self.H:
            for x, z in self._interior(h):
                self.set(x, h.b - 1, z, 'stone')
                self.set(x, h.b, z, FLOOR)
                for y in range(h.b + 1, h.b + 16):
                    self.set(x, y, z, 'air')
                if h.out_storeys == 2 or h.f - 7 <= z:
                    self.set(x, h.b + 4, z, FLOOR)

    def _wall_h(self, h, x, z):
        """Wall top above floor: 6 (two storeys) or 3 for a single-storey outrigger."""
        if h.out_storeys == 2 or (h.pw <= x <= h.pe and h.f - 7 <= z <= h.f):
            return 6
        return 3

    def _covers(self, h, x, z):
        o0, o1 = h.outrigger
        return ((h.pw <= x <= h.pe and h.f - 7 <= z <= h.f) or
                (o0 <= x <= o1 and h.f - 11 <= z <= h.f - 7))

    def _interior(self, h):
        o0, o1 = h.outrigger
        cells = [(x, z) for x in h.inner for z in range(h.f - 6, h.f)]
        cells += [(x, z) for x in range(o0 + 1, o1) for z in range(h.f - 10, h.f - 6)]
        return cells

    def _mat(self, h, x, z):
        """Party columns shared by two houses are brick unless only one house is there."""
        if x in (h.pw, h.pe):
            others = [o for o in self.H if o is not h and self._covers(o, x, z)]
            if others and any(o.wall != h.wall for o in others):
                return 'bricks'
        return h.wall

    # --- 3. openings, bay, porch, stair ---------------------------------------
    def openings(self):
        for h in self.H:
            b, f = h.b, h.f
            # front door + white hood
            d = h.door_col
            self.set(d, b + 1, f, f'{h.door_block}[facing=south,half=lower,hinge={"left" if h.door == "W" else "right"},open=false]')
            self.set(d, b + 2, f, f'{h.door_block}[facing=south,half=upper,hinge={"left" if h.door == "W" else "right"},open=false]')
            self.set(d, b + 3, f, WHITE)
            self.set(d, b + 3, f + 1, 'smooth_quartz_slab[type=top]')
            self.set(d, b, f + 1, 'polished_andesite')
            # ground-floor bay: open the wall behind it, glass box one row out
            for x in h.bay_cols:
                for y in range(b + 1, b + 4):
                    self.set(x, y, f, 'air')
                self.set(x, b, f + 1, FLOOR)
                self.set(x, b + 1, f + 1, h.wall)
                self.set(x, b + 2, f + 1, 'glass')
                self.set(x, b + 3, f + 1, 'glass')
                self.set(x, b + 4, f + 1, _stair(TILE, 'north'))
            # first floor front: window over the bay (all but the column next to the
            # door) + a small one over the door; white sill band under them
            bay = h.bay_cols
            ff = [c for c in bay if abs(c - d) > 1] + [d]
            for x in ff:
                self.set(x, b + 4, f, WHITE)
                for y in (b + 5, b + 6):
                    self.set(x, y, f, 'glass_pane[east=true,west=true]')
            # rear: back door from the main block into the side return, window above
            sr = h.side_return
            r = f - 7
            for i, x in enumerate(sr):
                if i == 0:
                    self.set(x, b + 1, r, f'{h.door_block}[facing=north,half=lower,hinge=left,open=false]')
                    self.set(x, b + 2, r, f'{h.door_block}[facing=north,half=upper,hinge=left,open=false]')
                else:
                    for y in (b + 2, b + 3):
                        self.set(x, y, r, 'glass_pane[east=true,west=true]')
                for y in (b + 5, b + 6):
                    self.set(x, y, r, 'glass_pane[east=true,west=true]')
            # main block <-> outrigger openings (ground + first floor)
            o0, o1 = h.outrigger
            ff = (b + 5, b + 6) if h.out_storeys == 2 else ()
            for x in range(o0 + 1, o1):
                for y in (b + 1, b + 2) + ff:
                    self.set(x, y, r, 'air')
            # outrigger: side windows onto the side return, rear gable windows
            side = o0 if h.door == 'E' else o1
            for y in (b + 2,) + ff:
                self.set(side, y, f - 9, 'glass_pane[north=true,south=true]')
            back = list(range(o0 + 1, o1))
            for x in back:
                for y in (b + 2, b + 3):
                    self.set(x, y, f - 11, 'glass_pane[east=true,west=true]')
            for y in ff:
                self.set(back[0], y, f - 11, 'glass_pane[east=true,west=true]')
            # stair along the hall (door column), rising toward the back
            # four treads b+1..b+4 (the last one sits in the first-floor plane), landing at f-6
            for i, z in enumerate((f - 2, f - 3, f - 4, f - 5)):
                self.set(d, b + 1 + i, z, _stair('spruce', 'north'))
            for z in (f - 2, f - 3, f - 4):       # open stairwell: headroom over every tread
                self.set(d, b + 4, z, 'air')
            # side return + yard paving
            for x in sr:
                for z in range(f - 11, f - 7):
                    self.set(x, b, z, 'smooth_stone')

    # --- 4. roof heightfield ---------------------------------------------------
    def roofs(self):
        R = {}
        def put(x, z, hgt, facing, h, prio):
            cur = R.get((x, z))
            if cur is None or (hgt, prio) > (cur[0], cur[3]):
                R[(x, z)] = (hgt, facing, h, prio)
        for h in self.H:
            e = h.b + 7
            for x in range(h.pw, h.pe + 1):
                for z in h.rows_main():
                    df, dr = h.f - z, z - (h.f - 7)
                    put(x, z, e + min(df, dr), 'north' if df < dr else 'south', h, 1)
            o0, o1 = h.outrigger
            eo = e if h.out_storeys == 2 else h.b + 4
            for x in range(o0, o1 + 1):
                for z in range(h.f - 11, h.f - 3):
                    dw, de = x - o0, o1 - x
                    put(x, z, eo + min(dw, de), None if dw == de else ('east' if dw < de else 'west'), h, 0)
        self.roof = R
        for (x, z), (hgt, facing, h, _) in R.items():
            if facing:
                self.set(x, hgt, z, _stair(h.roof, facing))
            else:
                self.set(x, hgt, z, f'{h.roof}_slab[type=bottom]')
                self.set(x, hgt - 1, z, ROOF_FULL[h.roof])
            # gable / party walls rise to meet the roof
            if (x, z) in self.walls:
                for y in range(h.b + 7, hgt):
                    if self.p.get(x, y, z) in (None, 'minecraft:air'):
                        self.set(x, y, z, self.walls[(x, z)])
        # chimney stacks on every party/end wall at that wall's highest ridge
        done = set()
        for h in self.H:
            for x in (h.pw, h.pe):
                if x in done:
                    continue
                done.add(x)
                top = max(R[(x, z)][0] for z in range(h.f - 7, h.f + 1))
                zs = [z for z in range(h.f - 7, h.f + 1) if R[(x, z)][0] == top]
                for z in zs:
                    for y in range(top, top + 2):
                        self.set(x, y, z, 'bricks')
                    self.set(x, top + 2, z, 'flower_pot')

    # --- 5. gardens -----------------------------------------------------------
    def gardens(self):
        for h in self.H:
            f, b = h.f, h.b
            # front: boundary at the back of the pavement, gate gap at the path
            for x in range(h.pw, h.pe + 1):
                if x == h.pe and h is not self.H[-1]:
                    continue
                zb = self.pav_row(x) - 1
                # close diagonal steps of the boundary line against the column to the west
                zw = self.pav_row(x - 1) - 1 if x > self.x0 else zb
                for zz in range(min(zb, zw), max(zb, zw) + 1):
                    if zz != zb and x != h.door_col:
                        self.set(x, b + 1, zz, 'oak_leaves[persistent=true]' if h.front_boundary == 'hedge' else 'bricks')
                if x != h.door_col:
                    if h.front_boundary == 'hedge':
                        self.set(x, b + 1, zb, 'oak_leaves[persistent=true]')
                        self.set(x, b + 2, zb, 'oak_leaves[persistent=true]')
                    else:
                        self.set(x, b + 1, zb, h.wall if h.wall == 'bricks' else 'bricks')
                # side divider between front gardens (low wall on the party line)
                if x == h.pw and h is not self.H[0]:
                    for z in range(self._front_of(x) + 1, zb):
                        self.set(x, b + 1, z, 'bricks')
            for z in range(f + 1, self.pav_row(h.door_col) - 1):
                if self.p.get(h.door_col, b, z) != 'minecraft:polished_andesite':
                    self.set(h.door_col, b, z, 'polished_andesite')
            # yard wall on the squared party line, only beside the outrigger
            for x in (h.pw, h.pe):
                if x == h.pe and h is not self.H[-1]:
                    continue
                for z in range(f - 11, f - 7):
                    if self._wall_any(x, z):
                        continue
                    y = self._top(x, z)
                    self.set(x, y + 1, z, 'bricks')
                    self.set(x, y + 2, z, 'bricks')
            back = [(x, z) for (x, z), hh in self.plots.items() if hh is h and z < self.rear_z(h)]
            # patio band in the first two garden rows (still on the house width at 1:3)
            for x, z in back:
                if f - 13 <= z <= f - 12 and not self._on_fence_line(h, x, z):
                    self.set(x, b, z, 'smooth_stone')
            # steps up the lawn, on the centre of each garden row
            rows = {}
            for x, z in back:
                rows.setdefault(z, []).append(x)
            for z, xs in rows.items():
                if z >= f - 12:
                    continue
                interior = [x for x in xs if not self._on_fence_line(h, x, z)] or xs
                gx = interior[len(interior) // 2]
                y0, y1 = self._top(gx, z + 1), self._top(gx, z)
                if y1 == y0 + 1:
                    self.set(gx, y1, z, _stair('stone_brick', 'north'))
            # party fences on the stair, rear fence where the plot meets the lane
            for x, z in back:
                if self._on_fence_line(h, x, z) or (x, z) in self.gore_cells and self._borders_street(x, z):
                    self._fence_post(x, z)
            self._close_rear(h, back)
            if h.shed and back:
                self._shed(h, back)
            if h.tree and back:
                self._tree(h, back)

    def _borders_street(self, x, z):
        if not self.street:
            return False
        return any(self.street(x + dx, z + dz) for dx, dz in ((0, -1), (0, 1), (1, 0), (-1, 0)))

    def _fence_post(self, x, z):
        if self._wall_any(x, z):
            return
        y = self._top(x, z)
        self.set(x, y + 1, z, 'spruce_fence')
        self.set(x, y + 2, z, 'spruce_fence')

    def _close_rear(self, h, back):
        """Fence the step where the lane edge jumps a row between columns."""
        edge = {}
        step = -1 if self.slope_of(h)[1] <= 0 else 1
        owned = set(back)
        for x, z in back:
            if (x, z + step) not in self.plots:
                edge.setdefault(x, z)
                if step < 0:
                    edge[x] = min(edge[x], z)
                else:
                    edge[x] = max(edge[x], z)
        for x, z in edge.items():
            self._fence_post(x, z)
            if x - 1 not in edge:
                continue
            a, c = edge[x], edge[x - 1]
            for zz in range(min(a, c), max(a, c) + 1):
                if (x, zz) in owned:
                    self._fence_post(x, zz)

    def _shed(self, h, back):
        """Pale shed by the lane, inside the angled plot (aerial: roofs at the bottom)."""
        step = -1 if self.slope_of(h)[1] <= 0 else 1
        z_lane = min(z for _, z in back) if step < 0 else max(z for _, z in back)
        zs = [z_lane - step * i for i in (1, 2, 3)]
        xs = sorted({x for x, z in back if z == zs[-1] and not self._on_fence_line(h, x, z)})
        if len(xs) < 2:
            return
        x0 = xs[0]
        cols = (x0, x0 + 1)
        y = max(self._top(x, z) for x in cols for z in zs if (x, z) in self.plots)
        for x in cols:
            for z in zs:
                if (x, z) not in self.plots:
                    continue
                for yy in range(self._top(x, z) + 1, y + 1):
                    self.set(x, yy, z, 'dirt')
                self.set(x, y + 1, z, 'spruce_planks')
                self.set(x, y + 2, z, 'spruce_planks')
                self.set(x, y + 3, z, 'spruce_slab[type=bottom]')
        door_z = zs[-1]
        self.set(x0, y + 1, door_z, 'spruce_door[facing=south,half=lower,hinge=left,open=false]')
        self.set(x0, y + 2, door_z, 'spruce_door[facing=south,half=upper,hinge=left,open=false]')

    def _tree(self, h, back):
        """Crown mid-plot, on a column that stays inside the angled garden."""
        zs = sorted({z for _, z in back})
        z = zs[len(zs) // 2]
        xs = sorted(x for x, zz in back if zz == z and not self._on_fence_line(h, x, z)) or \
            sorted(x for x, zz in back if zz == z)
        x = xs[len(xs) // 2]
        y = self._top(x, z)
        for i in range(1, 6):
            self.set(x, y + i, z, 'oak_log')
        for dx in range(-2, 3):
            for dz in range(-2, 3):
                for dy in range(4, 8):
                    if abs(dx) + abs(dz) + max(0, dy - 6) * 2 <= 3 and not (dx == dz == 0 and dy < 6):
                        xx, zz = x + dx, z + dz
                        if self.p.get(xx, y + dy, zz) in (None, 'minecraft:air'):
                            self.set(xx, y + dy, zz, 'oak_leaves[persistent=true]')

    def release_west(self):
        """Keep a lawn west of the sheared plot so a neighbour parcel stays touched.

        Broadlands Road 44's signed plot includes the old north-south strip west
        of no. 36. Dropping those columns lapses the sign-off. The lawn stays
        until that neighbour is rebuilt on its own angle. Only the westernmost
        terrace sets restore_west.
        """
        if not self.restore_west or self.plots is None:
            return
        from site_kit import built_cells
        owned = built_cells(exclude={self.p.name}, within=self.p.cells)
        h = self.H[0]
        sl = self.slope_of(h)
        step = -1 if sl[1] <= 0 else 1
        lane0 = self.lane(self.x0)
        if lane0 is None:
            return
        # From the back wall out to the lane at the west wall. Rows the sheared
        # plot never reaches still count: the neighbour parcel keeps the old tail.
        if step < 0:
            z_lo, z_hi = lane0 + 1, self.rear_z(h) - 1
        else:
            z_lo, z_hi = self.rear_z(h) + 1, lane0 - 1
        if z_lo > z_hi:
            return
        for z in range(z_lo, z_hi + 1):
            xs = [x for (x, zz) in self.plots if zz == z]
            limit = self._bound_x(h, z, 'W')
            if xs:
                limit = min(limit, min(xs))
            for x in range(self.x0, limit):
                if (x, z) in self.plots:
                    continue
                lane = self.lane(x)
                if lane is None:
                    continue
                if step < 0 and z <= lane:
                    continue
                if step > 0 and z >= lane:
                    continue
                if any((x, y, z) in owned for y in range(h.b - 2, h.b + 16)):
                    continue
                self._lay(h, x, z)

    def _front_of(self, x):
        return max(h.f for h in self.H if self._covers(h, x, h.f) or h.pw <= x <= h.pe)

    def _wall_any(self, x, z):
        return (x, z) in self.walls

    def _top(self, x, z):
        for y in range(60, 10, -1):
            s = self.p.get(x, y, z)
            if s and s not in ('minecraft:air',) and 'fence' not in s and 'leaves' not in s:
                return y
        return 27

    # --- 6. connect fences / panes to their planned neighbours ------------------
    def connect(self):
        dirs = {'north': (0, -1), 'south': (0, 1), 'east': (1, 0), 'west': (-1, 0)}
        for (x, y, z), s in list(self.p.cells.items()):
            if s.startswith('minecraft:spruce_fence') and 'gate' not in s:
                props = []
                for k, (dx, dz) in dirs.items():
                    n = self.p.get(x + dx, y, z + dz) or ''
                    ok = 'fence' in n or (n and 'air' not in n and 'leaves' not in n and 'pane' not in n
                                          and 'stairs' not in n and 'slab' not in n and 'door' not in n)
                    props.append(f'{k}={"true" if ok else "false"}')
                self.p.cells[(x, y, z)] = 'minecraft:spruce_fence[' + ','.join(sorted(props)) + ']'

    def build(self):
        self.plots = self._compute_plots()
        self.ground()
        self.shells()
        self.openings()
        self.roofs()
        self.gardens()
        self.release_west()
        self.connect()
