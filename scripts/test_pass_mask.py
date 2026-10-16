"""Unit tests for scripts/pass_mask.py (no Minecraft, no world writes)."""
import json
import tempfile
import unittest
from pathlib import Path

import pass_mask as pm


def _air(_pos):
    return True


class TestCellBounds(unittest.TestCase):
    """Cell edges and clipping."""

    def test_bounds_48_m44(self):
        """Cell 48,-44 spans x 6144..6271 and z -5632..-5505."""
        self.assertEqual(pm.cell_bounds(48, -44), (6144, -5632, 6271, -5505))

    def test_clip_drops_outside_and_counts(self):
        """Placements past the cell edge are dropped, not written across."""
        placements = {(6144, 64, -5600): 'minecraft:oak_leaves', (6272, 64, -5600): 'minecraft:oak_leaves'}
        kept, dropped = pm.clip_to_cell(placements, 48, -44)
        self.assertEqual(list(kept), [(6144, 64, -5600)])
        self.assertEqual(dropped, 1)


class TestOverhangMask(unittest.TestCase):
    """A tree mask may cross the cell edge; undo removes those blocks too."""

    def test_overhang_is_recorded_and_undone(self):
        placements = {(6271, 70, -5600): 'minecraft:oak_log', (6272, 72, -5600): 'minecraft:oak_leaves',
                      (6273, 72, -5600): 'minecraft:oak_leaves'}
        mask = pm.build_mask('trees', (48, -44), 'p', placements, _air)
        self.assertEqual(mask['count'], 3)
        self.assertEqual(mask['outside_cell'], 2)
        self.assertEqual(pm.mask_placements(mask), placements)
        to_air, conflicts = pm.plan_undo(mask, lambda pos: placements[pos])
        self.assertEqual(sorted(to_air), sorted(placements))
        self.assertEqual(conflicts, [])
        self.assertEqual(mask, pm.build_mask('trees', (48, -44), 'p', placements, _air, created=mask['created']))


    def test_undo_keeps_blocks_another_mask_also_owns(self):
        a = {(6272, 72, -5600): 'minecraft:oak_leaves', (6273, 72, -5600): 'minecraft:oak_leaves'}
        b = {(6273, 72, -5600): 'minecraft:oak_leaves', (6274, 72, -5600): 'minecraft:oak_leaves'}
        ma = pm.build_mask('trees', (48, -44), 'p', a, _air)
        mb = pm.build_mask('trees', (49, -44), 'q', b, _air)
        with tempfile.TemporaryDirectory() as tmp:
            pm.write_mask(ma, Path(tmp))
            pm.write_mask(mb, Path(tmp))
            shared = pm.shared_positions(ma, Path(tmp))
            self.assertEqual(shared, {(6273, 72, -5600)})
            to_air, _ = pm.plan_undo(ma, lambda pos: 'minecraft:oak_leaves', shared)
            self.assertEqual(to_air, [(6272, 72, -5600)])
            self.assertEqual(pm.shared_positions(mb, Path(tmp)), {(6273, 72, -5600)})


class TestRuns(unittest.TestCase):
    """Run-length encoding round trip."""

    def test_round_trip(self):
        """Encode then decode gives back the same placements."""
        placements = {
            (0, 64, 0): 'minecraft:oak_leaves',
            (0, 65, 0): 'minecraft:oak_leaves',
            (1, 64, 0): 'minecraft:fern',
            (1, 64, 2): 'minecraft:oak_leaves',
        }
        bbox = pm._box_of(placements)
        palette, runs = pm.encode_runs(placements, bbox)
        self.assertEqual(palette[0], 'minecraft:air')
        self.assertEqual(pm.decode_runs(palette, pm._runs_copy(runs), bbox), placements)

    def test_order_is_x_then_z_then_y(self):
        """The first run covers the lowest y at x0, z0 and then climbs y."""
        bbox = [0, 0, 0, 0, 1, 1]
        palette, runs = pm.encode_runs({(0, 1, 1): 'minecraft:fern'}, bbox)
        # order: (0,0,0) (0,1,0) (0,0,1) (0,1,1): only the last is placed
        self.assertEqual(runs, [[0, 3], [1, 1]])


class TestBuildAndVerify(unittest.TestCase):
    """Mask build, file round trip and integrity."""

    def setUp(self):
        self.placements = {
            (6150, 70, -5600): 'minecraft:oak_leaves',
            (6150, 71, -5600): 'minecraft:oak_leaves',
            (6151, 70, -5600): 'minecraft:fern',
        }

    def test_build_fields(self):
        """Mask carries the documented fields and a valid digest."""
        mask = pm.build_mask('trees', (48, -44), 'highfield_48_m44_trees', self.placements, _air,
                             created='2026-10-14T00:00:00+00:00')
        self.assertEqual(mask['count'], 3)
        self.assertEqual(mask['bbox'], [6150, 70, -5600, 6151, 71, -5600])
        self.assertEqual(mask['offset'], [6150, 70, -5600])
        self.assertEqual(mask['size'], [2, 2, 1])
        self.assertTrue(mask['air_only'])
        self.assertEqual(mask['outside_cell'], 0)
        self.assertTrue(pm.verify_integrity(mask))

    def test_plan_time_air_check_refuses_solid(self):
        """A placement onto a solid block stops the build."""
        solid = {(6150, 70, -5600)}
        with self.assertRaises(ValueError):
            pm.build_mask('trees', (48, -44), 'p', self.placements, lambda p: p not in solid)

    def test_bad_pass_name(self):
        """Only trees and decor write masks."""
        with self.assertRaises(ValueError):
            pm.build_mask('ground', (48, -44), 'p', self.placements, _air)

    def test_file_round_trip(self):
        """Write then read gives an identical mask that still verifies."""
        mask = pm.build_mask('decor', (48, -44), 'p', self.placements, _air)
        with tempfile.TemporaryDirectory() as tmp:
            path = pm.write_mask(mask, Path(tmp))
            self.assertEqual(path.name, 'decor-48_-44.mask.json')
            loaded = pm.read_mask(path)
        self.assertEqual(loaded, json.loads(json.dumps(mask)))
        self.assertTrue(pm.verify_integrity(loaded))

    def test_tampered_mask_fails_integrity(self):
        """Changing a stored run breaks the digest."""
        mask = pm.build_mask('trees', (48, -44), 'p', self.placements, _air)
        mask['palette'][1] = 'minecraft:stone'
        self.assertFalse(pm.verify_integrity(mask))

    def test_empty_mask(self):
        """A pass that placed nothing still builds and verifies."""
        mask = pm.build_mask('decor', (48, -44), 'p', {}, _air)
        self.assertEqual(mask['count'], 0)
        self.assertEqual(pm.mask_placements(mask), {})
        self.assertTrue(pm.verify_integrity(mask))


class TestPlanUndo(unittest.TestCase):
    """Undo planning is read-only and stops on any conflict."""

    def setUp(self):
        self.placements = {(6150, 70, -5600): 'minecraft:oak_leaves', (6151, 70, -5600): 'minecraft:fern'}
        self.mask = pm.build_mask('trees', (48, -44), 'p', self.placements, _air)

    def test_clean_world_plans_all_positions(self):
        """Live world matches the mask: every placed position goes to air."""
        live = dict(self.placements)
        to_air, conflicts = pm.plan_undo(self.mask, lambda p: live.get(p, 'minecraft:air'))
        self.assertEqual(sorted(to_air), sorted(self.placements))
        self.assertEqual(conflicts, [])

    def test_changed_block_is_conflict(self):
        """A block changed since the pass stops the undo with a conflict list."""
        live = dict(self.placements)
        live[(6151, 70, -5600)] = 'minecraft:stone'
        to_air, conflicts = pm.plan_undo(self.mask, lambda p: live.get(p, 'minecraft:air'))
        self.assertEqual(conflicts, [((6151, 70, -5600), 'minecraft:fern', 'minecraft:stone')])
        self.assertEqual(to_air, [(6150, 70, -5600)])

    def test_undo_refuses_bad_mask(self):
        """A mask that fails its digest is not planned at all."""
        self.mask['sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            pm.plan_undo(self.mask, lambda p: 'minecraft:air')


class TestOverlap(unittest.TestCase):
    """A ground plan that touches a masked position must be caught."""

    def test_overlap_found(self):
        """Only positions the mask owns are reported."""
        mask = pm.build_mask('trees', (48, -44), 'p', {(6150, 70, -5600): 'minecraft:oak_leaves'}, _air)
        planned = {(6150, 70, -5600): 'minecraft:grass_block', (6150, 69, -5600): 'minecraft:grass_block'}
        self.assertEqual(pm.masked_overlaps(planned, mask), [(6150, 70, -5600)])

    def test_no_overlap(self):
        """A plan clear of the mask reports nothing."""
        mask = pm.build_mask('decor', (48, -44), 'p', {(6150, 70, -5600): 'minecraft:fern'}, _air)
        self.assertEqual(pm.masked_overlaps({(6160, 70, -5600): 'minecraft:grass_block'}, mask), [])


if __name__ == '__main__':
    unittest.main()
