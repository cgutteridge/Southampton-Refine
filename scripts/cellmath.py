"""128x128 coverage-cell maths and direction tables, in one place.

A cell (tx, tz) covers blocks x in [tx*128, tx*128+127], z in [tz*128, tz*128+127]. North is -Z.
Pure functions, no world access.
"""
from __future__ import annotations

CELL = 128
ORIGIN_CELL = (48, -44)         # radial focus: Highfield campus centre (site/COVERAGE.txt)

N4 = ((1, 0), (-1, 0), (0, 1), (0, -1))
N8 = tuple((dx, dz) for dx in (-1, 0, 1) for dz in (-1, 0, 1) if dx or dz)
DIRS = {'N': (0, -1), 'S': (0, 1), 'W': (-1, 0), 'E': (1, 0)}
OPP = {'N': 'S', 'S': 'N', 'W': 'E', 'E': 'W'}


def parse_cell(spec: str) -> tuple[int, int]:
    """Parse ``tx,tz``.

    @param spec: comma-separated cell indices
    @returns: (tx, tz)
    @raises SystemExit: on bad input
    """
    parts = [p.strip() for p in str(spec).split(',')]
    if len(parts) != 2:
        raise SystemExit(f'expected tx,tz got {spec!r}')
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        raise SystemExit(f'expected tx,tz got {spec!r}') from None


def cell_of(x: int, z: int) -> tuple[int, int]:
    """Cell key of a block column: (floor(x / 128), floor(z / 128))."""
    return x // CELL, z // CELL


def bounds(cell: tuple[int, int], margin: int = 0) -> tuple[int, int, int, int]:
    """Inclusive (x0, z0, x1, z1) of a cell, grown by ``margin`` blocks on every side."""
    x0, z0 = cell[0] * CELL, cell[1] * CELL
    return x0 - margin, z0 - margin, x0 + CELL - 1 + margin, z0 + CELL - 1 + margin


def ring_distance(cell: tuple[int, int], origin: tuple[int, int] = ORIGIN_CELL) -> int:
    """Chebyshev ring number of a cell around ``origin``."""
    return max(abs(cell[0] - origin[0]), abs(cell[1] - origin[1]))


def ring_cells(r: int, origin: tuple[int, int] = ORIGIN_CELL) -> list[tuple[int, int]]:
    """Cells of Chebyshev ring r: north centre first, then clockwise.

    Order: top edge from the centre column eastward, down the east side, back along the bottom,
    up the west side, finishing the top edge.
    """
    ox, oz = origin
    if r == 0:
        return [origin]
    return ([(ox + dx, oz - r) for dx in range(0, r + 1)]
            + [(ox + r, oz + dz) for dz in range(-r + 1, r + 1)]
            + [(ox + dx, oz + r) for dx in range(r - 1, -r - 1, -1)]
            + [(ox - r, oz + dz) for dz in range(r - 1, -r - 1, -1)]
            + [(ox + dx, oz - r) for dx in range(-r + 1, 0)])
