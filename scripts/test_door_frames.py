"""Door-frame guard: a door needs a jamb each side and a lintel (user, 2026-10-16)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from site_kit import Plan, door_frame_issues  # noqa: E402

DOOR = 'dark_oak_door[facing=north,half={},hinge=left,open=false]'


def wall_plan(missing=()):
    """Wall row along x at z=0, y 49..51, a north-facing door at x=5."""
    p = Plan('t')
    for x in range(3, 8):
        for y in (49, 50, 51):
            if (x, y) not in missing:
                p.set(x, y, 0, 'bricks')
    p.set(5, 49, 0, DOOR.format('lower'))
    p.set(5, 50, 0, DOOR.format('upper'))
    return p


class TestDoorFrames(unittest.TestCase):
    def test_framed_door_is_clean(self):
        self.assertEqual(door_frame_issues(wall_plan(), lambda x, y, z: None), [])

    def test_open_side_is_reported_at_both_heights(self):
        p = wall_plan(missing={(6, 49), (6, 50)})
        got = door_frame_issues(p, lambda x, y, z: None)
        self.assertEqual({g[3] for g in got}, {'jamb east'})
        self.assertEqual(len(got), 2)

    def test_missing_lintel_is_reported(self):
        got = door_frame_issues(wall_plan(missing={(5, 51)}), lambda x, y, z: None)
        self.assertEqual([g[3] for g in got], ['lintel'])

    def test_live_world_fills_in_cells_the_plan_does_not_set(self):
        p = wall_plan(missing={(4, 49), (4, 50)})
        self.assertEqual(len(door_frame_issues(p, lambda x, y, z: None)), 2)
        self.assertEqual(door_frame_issues(p, lambda x, y, z: 'minecraft:stone'), [])


if __name__ == '__main__':
    unittest.main()
