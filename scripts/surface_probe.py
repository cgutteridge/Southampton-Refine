"""Read-only helpers for finding the ground surface in a saved column.

Shared by the ground, trees and foliage tools. Nothing here writes to the world.
"""
from __future__ import annotations

from site_kit import World

# Small plants: counted as air when finding the surface, and by the ground clear step.
PLANTS = (
    'short_grass', 'tall_grass', 'fern', 'large_fern', 'flower', 'poppy', 'dandelion', 'daisy',
    'cornflower', 'allium', 'azure_bluet', 'oxeye_daisy', 'red_tulip', 'white_tulip',
)
JUNK_ABOVE = ('_log', 'leaves', '_carpet', 'sapling')


def short_id(block: str) -> str:
    """Block id without ``minecraft:`` or ``[state]``."""
    return (block or 'minecraft:air').split('[')[0].replace('minecraft:', '')


def is_water(block: str) -> bool:
    """Plain water block (waterlogged stairs and leaves are not water)."""
    return (block or '').split('[')[0] == 'minecraft:water'


def is_tree_or_plant_block(block: str) -> bool:
    """Logs, leaves, carpet, saplings and small plants: vegetation, not ground."""
    short = short_id(block)
    return 'sapling' in short or any(j in block for j in JUNK_ABOVE) or short in PLANTS


def surface_y(w: World, x: int, z: int, top: int = 110) -> tuple[int, str] | None:
    """Top ground block of a column, skipping air, plants, logs, leaves and marker wool.

    @returns: (y, short block id), or None for an empty column. Water counts as a surface.
    """
    y = top
    while y > 30:
        b = w.block(x, y, z) or 'minecraft:air'
        if is_water(b):
            return y, short_id(b)
        if b.endswith('air'):
            y -= 1
            continue
        if any(p in b for p in PLANTS) or 'leaves' in b or '_log' in b:
            y -= 1
            continue
        if 'wool' in b and y > 80:
            y -= 1
            continue
        return y, short_id(b)
    return None
