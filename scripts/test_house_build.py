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


if __name__ == '__main__':
    unittest.main()
