import json
import tempfile
import unittest
from pathlib import Path

import house_build as H

SPECS = sorted((Path(__file__).resolve().parent.parent / 'site/builds').glob('*.json'))


class SpecTest(unittest.TestCase):
    def test_all_committed_specs_load(self):
        self.assertTrue(SPECS)
        for p in SPECS:
            with self.subTest(spec=p.name):
                spec = H.load_spec(p)
                self.assertEqual(spec['name'], p.stem)

    def write(self, spec):
        f = Path(tempfile.mkdtemp()) / 's.json'
        f.write_text(json.dumps(spec))
        return f

    def test_missing_key_and_unknown_label_are_refused(self):
        good = {'name': 'x', 'ways': {'1': 'A'}, 'roofs': {'A': 'brick'},
                'groups': [{'nos': ['A'], 'front': 'S'}]}
        spec = H.load_spec(self.write(good))
        self.assertEqual((spec['step_max'], spec['ledge_stair'], spec['keep_edits'], spec['floor_min']), (4, False, False, None))
        for bad in ({k: v for k, v in good.items() if k != 'roofs'},
                    {**good, 'groups': [{'nos': ['B'], 'front': 'S'}]},
                    {**good, 'groups': [{'nos': ['A'], 'front': 'X'}]}):
            with self.assertRaises(SystemExit):
                H.load_spec(self.write(bad))


class DoorFrameTest(unittest.TestCase):
    def build(self, walls, door_frame=True):
        b = H.Build.__new__(H.Build)
        b.spec = {'door_frame': door_frame}
        h = type('h', (), {})()
        h.walls = set(walls)
        b.owner = {c: 0 for c in walls}               # nothing stands in front of the wall
        return b, h

    def test_door_prefers_cell_with_wall_each_side(self):
        # front N: a step at x=2 means (2,0) has air to its west; (4,0) sits in a straight run
        walls = [(2, 0), (3, 0), (4, 0), (5, 0), (6, 0)]
        b, h = self.build(walls)
        self.assertEqual(sorted(b.framed(h, walls, 'N')), [(3, 0), (4, 0), (5, 0)])

    def test_notch_then_unchanged_fallback(self):
        walls = [(0, 0), (1, 0)]
        b, h = self.build(walls)
        self.assertEqual(b.framed(h, walls, 'N'), walls)    # no cell has both neighbours: keep the old pick
        b, h = self.build(walls, door_frame=False)
        self.assertEqual(b.framed(h, walls, 'N'), walls)


if __name__ == '__main__':
    unittest.main()
