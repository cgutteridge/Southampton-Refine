"""site_status: parsing, layer aliases, the run log and the morning report (temp files only)."""
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import site_status as ss


class TestSiteStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.saved = (ss.CELLS, ss.MARKER, ss.LOCK, ss.RUN_LOG)
        ss.CELLS, ss.MARKER, ss.LOCK, ss.RUN_LOG = d / 'cells', d / 'cur.json', d / 'LOCK.json', d / 'RUN-LOG.md'
        ss.CELLS.mkdir()
        ss.MARKER.write_text(json.dumps({'tx': 47, 'tz': -45}))

    def tearDown(self):
        ss.CELLS, ss.MARKER, ss.LOCK, ss.RUN_LOG = self.saved
        self.tmp.cleanup()

    def cell(self, tx, tz, stages):
        (ss.CELLS / f'{tx}_{tz}-STAGES.json').write_text(json.dumps({'cell': f'{tx},{tz}', 'stages': stages}))

    def test_stamps_and_rings(self):
        self.assertEqual(ss.parse_stamp('2026-10-15 19:03:18'), datetime(2026, 10, 15, 19, 3, 18))
        self.assertEqual(ss.parse_stamp('2026-10-15 19:03'), datetime(2026, 10, 15, 19, 3))
        self.assertIsNone(ss.parse_stamp('never'))
        self.assertEqual([ss.ring(c) for c in [(48, -44), (47, -45), (50, -42), (51, -41)]], [0, 1, 2, 3])

    def test_layer_aliases_pick_the_latest_and_verified_counts(self):
        sts = {'ground': {'status': 'applied', 'readback': {'checked': '2026-10-14 10:00'}},
               'ground-layer': {'status': 'applied-with-mismatches', 'readback': {'checked': '2026-10-15 10:00'}},
               'trees': {'status': 'verified'}, 'decor': {'status': 'undone'}}
        self.assertEqual(ss.layer_status(sts, 'ground'), 'applied-with-mismatches')
        self.assertEqual(ss.layer_marks(sts), 'ground ⚠ trees ✓ decor –')
        self.assertFalse(ss.layers_applied(sts))
        sts['ground-layer'] = {'status': 'applied', 'readback': {'checked': '2026-10-16 10:00'}}
        sts['decor'] = {'status': 'applied'}
        self.assertTrue(ss.layers_applied(sts))

    def test_events_since_and_dedupe(self):
        one = {'status': 'applied', 'blocks': 5, 'readback': {'checked': '2026-10-15 19:03:18', 'mismatches': 0}}
        self.cell(47, -45, {'feature_x': one, 'feature-x': one, 'trees': {'status': 'applied', 'blocks': 9,
                 'readback': {'checked': '2026-10-14 08:00', 'mismatches': 0}}})
        ev = ss.events(ss.load_stages(), datetime(2026, 10, 15, 17, 0))
        self.assertEqual(len(ev), 1)
        self.assertEqual(ev[0]['blocks'], 5)
        self.assertEqual(len(ss.events(ss.load_stages())), 2)

    def test_status_flags_problems_and_marker(self):
        self.cell(47, -45, {'ground-layer': {'status': 'applying'}, 'trees': {'status': 'applied'}, 'decor': {'status': 'applied'}})
        out = ss.cmd_status(ss.load_stages())
        self.assertIn('MARKER (where work is): 47,-45', out)
        self.assertIn('▶  47,-45', out)
        self.assertIn('ground !', out)
        self.assertIn('⚠ ground-layer', out)

    def test_log_then_morning_lists_eye_items(self):
        self.cell(47, -45, {'ground-layer': {'status': 'applied', 'blocks': 3, 'readback': {'checked': '2026-10-16 10:09', 'mismatches': 0}},
                            'trees': {'status': 'applied'}, 'decor': {'status': 'applied'}})
        ss.main(['log', '--cell', '47,-45', '--did', 'plaza lawn applied', '--look', '6139,-5742: oak',
                 '--problem', 'strip under Building 2 still paved'])
        text = ss.RUN_LOG.read_text()
        self.assertIn('— cell 47,-45', text)
        self.assertIn('Layers now: ground ✓ trees ✓ decor ✓  (all applied)', text)
        out = ss.cmd_morning(ss.load_stages(), datetime(2000, 1, 1))
        self.assertIn('NEEDS YOUR EYE:', out)
        self.assertIn('6139,-5742: oak', out)
        self.assertIn('strip under Building 2 still paved', out)
        future = ss.cmd_morning(ss.load_stages(), datetime(2999, 1, 1))
        self.assertIn('no run-log entries', future)


if __name__ == '__main__':
    unittest.main()
