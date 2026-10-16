#!/usr/bin/env python3
"""Unit tests for scripts/site_handoff.py: definition of done and atomic `end` (I-046, I-049, I-057).

Temp SITE dir only; the real site/ is never touched, no Minecraft, no OSM.

  python3 -m unittest scripts/test_site_handoff.py
"""
import contextlib
import io
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_handoff as H  # noqa: E402

QUEUE_TEXT = '''SOUTHAMPTON REFINE — QUEUE

[ ] Q-001  CELL 1,1 (r=0) layered passes: ground, trees, decor. RULES: ground.
           Auto-queued.

[ ] Q-002  CELL 2,2 (r=1) layered passes: ground, trees, decor. RULES: ground.
           Auto-queued.
'''
HANDOFF_TEXT = '''head
------------------------------------------------------------------------
Q-001 STARTER (copy into a fresh session)
------------------------------------------------------------------------
old
------------------------------------------------------------------------
GENERIC BOOT PROMPT
'''


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.site = Path(self.tmp.name)
        (self.site / 'cells').mkdir()
        (self.site / 'QUEUE.txt').write_text(QUEUE_TEXT)
        (self.site / 'HANDOFF.txt').write_text(HANDOFF_TEXT)
        patches = [mock.patch.object(H, n, v) for n, v in dict(
            SITE=self.site, QUEUE=self.site / 'QUEUE.txt', HANDOFF=self.site / 'HANDOFF.txt',
            PENDING=self.site / '.handoff-pending.json', GOOGLE_REVIEW=self.site / 'GOOGLE-REVIEW.txt', LOCK=self.site / 'LOCK.json',
            QUEUE_DONE=self.site / 'archive' / 'QUEUE-done.txt').items()]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def stages(self, cell, **st):
        (self.site / 'cells' / f'{cell[0]}_{cell[1]}-STAGES.json').write_text(json.dumps({'stages': st}))


APPLIED = {k: {'status': 'applied'} for k in ('ground', 'trees', 'decor')}


class DoneTest(Base):
    def test_done_needs_layers_current_trees_and_no_residue(self):
        self.stages((1, 1), **APPLIED)
        with mock.patch('pass_mask.trees_rule_current', return_value=True), \
                mock.patch.object(H, 'residual_features', return_value=[]):
            self.assertTrue(H.layers_done((1, 1)))
        with mock.patch('pass_mask.trees_rule_current', return_value=True), \
                mock.patch.object(H, 'residual_features', return_value=[{'kind': 'lumps'}]):
            self.assertFalse(H.layers_done((1, 1)))      # finished cell with a residual lump is re-queued
        with mock.patch('pass_mask.trees_rule_current', return_value=False), \
                mock.patch.object(H, 'residual_features', return_value=[]):
            self.assertFalse(H.layers_done((1, 1)))      # old tree mask
            self.assertTrue(H.cell_gaps((1, 1))['trees_stale'])

    def test_applying_stage_is_not_done_and_reported_first(self):
        """An aborted apply leaves 'applying': never done, listed as 'in-flight: <plan>' by next --plan."""
        st = dict(APPLIED)
        st['decor'] = {'status': 'applying', 'plan': 'highfield_1_1_decor'}
        self.stages((1, 1), **st)
        with mock.patch('pass_mask.trees_rule_current', return_value=True), \
                mock.patch.object(H, 'residual_features', return_value=[]):
            g = H.cell_gaps((1, 1))
            self.assertEqual(g['in_flight'], ['in-flight: highfield_1_1_decor'])
            self.assertEqual(g['layers'], ['decor'])
            self.assertFalse(H.layers_done((1, 1)))
        with mock.patch('pass_mask.trees_rule_current', return_value=True), \
                mock.patch.object(H, 'residual_features', return_value=[]), \
                mock.patch.object(H, 'ring_cells', return_value=[(1, 1)]), \
                mock.patch('sys.stdout', new=io.StringIO()) as out:
            H.cmd_plan([])
        self.assertIn('in-flight: highfield_1_1_decor', out.getvalue())

    def test_missing_layer_short_circuits_scan(self):
        self.stages((1, 1), ground={'status': 'verified'})
        with mock.patch.object(H, 'residual_features', side_effect=AssertionError('no scan')):
            self.assertFalse(H.layers_done((1, 1)))
            self.assertEqual(H.cell_gaps((1, 1), features=False)['layers'], ['trees', 'decor'])

    def test_next_cell_requeues_finished_cell_with_residue(self):
        cells = {(48, -44): [], (48, -45): [{'kind': 'lumps', 'label': 'x', 'refs': ['unmapped'], 'bbox': (0, 0, 9, 9)}]}
        for c in cells:
            self.stages(c, **APPLIED)
        with mock.patch('pass_mask.trees_rule_current', return_value=True), \
                mock.patch.object(H, 'residual_features', side_effect=lambda c, idx=None: cells.get(c, [])):
            self.assertEqual(H.next_cell(max_ring=1), (48, -45, 1))
            plan = H.requeue_plan(max_ring=1)
        self.assertEqual([(t, z) for t, z, *_ in plan], [(48, -45)])

    def test_queue_items_for_residue_and_stale_trees(self):
        feat = {'kind': 'lumps', 'label': 'Hartley Avenue (2 unrefined Geocraft building(s), 1 not in OSM)',
                'street': 'Hartley Avenue', 'refs': ['w1'], 'bbox': (6400, -5500, 6430, -5480)}
        gaps = {'layers': [], 'trees_stale': True, 'features': [feat]}
        with mock.patch.object(H, 'next_cell', return_value=(48, -44, 0)), \
                mock.patch.object(H, 'cell_gaps', return_value=gaps), \
                mock.patch.object(H, 'lidar_lumps', return_value=[]):
            first = H.advance_to_next_cell()
        self.assertIn('FEATURE Hartley Avenue', first['text'])
        ids = [(i['id'], 'TREES re-run' in i['text']) for i in H._queue_items() if i['id'] > 'Q-002']
        self.assertEqual([t for _i, t in ids], [False, True])


REVIEW_TEXT = '''head
 ring  cell      bld  status
  r0   1,1        4  done
  r1   2,2        2  features
  r1   3,3        8  todo
'''


class GoogleReviewTest(Base):
    def setUp(self):
        super().setUp()
        (self.site / 'GOOGLE-REVIEW.txt').write_text(REVIEW_TEXT)

    def test_first_row_not_done_is_next(self):
        self.assertEqual(H.next_google_review()['cell'], (2, 2))
        H.set_google_review_status((2, 2), 'done')
        self.assertEqual(H.next_google_review()['cell'], (3, 3))
        self.assertIn('  r1   3,3        8  todo', (self.site / 'GOOGLE-REVIEW.txt').read_text())

    def test_bad_status_word_is_refused(self):
        with self.assertRaises(ValueError):
            H.set_google_review_status((2, 2), 'finished')

    def test_review_item_is_queued_above_the_new_cell_items(self):
        gaps = {'layers': ['ground'], 'trees_stale': False, 'features': [], 'trees_over_roof': []}
        with mock.patch.object(H, 'next_cell', return_value=(4, 4, 2)), \
                mock.patch.object(H, 'cell_gaps', return_value=gaps):
            first = H.advance_to_next_cell()
            H.advance_to_next_cell()            # the review item is open: not queued twice
        self.assertIn('GOOGLE REVIEW cell 2,2', first['text'])
        self.assertEqual(H.google_review_cell(first), (2, 2))
        texts = [i['text'] for i in H._queue_items() if i['id'] > 'Q-002']
        self.assertTrue(texts[0].startswith('GOOGLE REVIEW'))
        self.assertEqual(sum('GOOGLE REVIEW' in t for t in texts), 1)
        self.assertTrue(any('layered passes' in t for t in texts))

    def test_end_of_review_chat_sets_the_row(self):
        gaps = {'layers': [], 'trees_stale': False, 'features': [], 'trees_over_roof': []}
        with mock.patch.object(H, 'next_cell', return_value=None), \
                mock.patch.object(H, 'cell_gaps', return_value=gaps):
            first = H.advance_to_next_cell()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                mock.patch('site_archive.run'):
            H.main(['end', first['id'], '--summary', 's', '--skip-say', '--skip-view', '--review-status', 'look'])
            self.assertEqual(H.next_google_review()['status'], 'look')
            self.assertEqual(H.cmd_end([first['id'], '--summary', 's', '--skip-say', '--skip-view']), 0)
        self.assertEqual(H.next_google_review()['cell'], (3, 3))


class LidarGapsTest(Base):
    LUMP = {'bbox': [10, 10, 20, 20], 'centre': [15, 15], 'storeys': 2, 'roof': 'pitched', 'ridge_axis': 'x', 'trees_over': 12}

    def test_trees_over_roof_open_until_resolved(self):
        self.assertEqual(H.trees_over_roof_open((1, 1), lumps=[self.LUMP]), [self.LUMP])
        self.stages((1, 1), lidar={'trees_over_roof_resolved': [{'bbox': [5, 5, 30, 30], 'reason': 'crown kept'}]})
        self.assertEqual(H.trees_over_roof_open((1, 1), lumps=[self.LUMP]), [])
        self.assertEqual(H.trees_over_roof_open((1, 1), lumps=[dict(self.LUMP, trees_over=0)]), [])

    def test_open_tree_over_roof_keeps_a_cell_not_done(self):
        self.stages((1, 1), **APPLIED)
        with mock.patch('pass_mask.trees_rule_current', return_value=True), \
                mock.patch.object(H, 'residual_features', return_value=[]), \
                mock.patch.object(H, 'lidar_lumps', return_value=[self.LUMP]):
            self.assertFalse(H.layers_done((1, 1)))
            self.assertEqual(H.cell_gaps((1, 1))['trees_over_roof'], [self.LUMP])

    def test_feature_item_shows_lidar_storeys_roof_ridge(self):
        feat = {'kind': 'building', 'label': 'Hartley Avenue', 'street': 'x', 'refs': ['w1'], 'bbox': (0, 0, 40, 40)}
        gaps = {'layers': [], 'trees_stale': False, 'features': [feat], 'trees_over_roof': []}
        with mock.patch.object(H, 'next_cell', return_value=(1, 1, 0)), \
                mock.patch.object(H, 'cell_gaps', return_value=gaps), \
                mock.patch.object(H, 'lidar_lumps', return_value=[self.LUMP]):
            first = H.advance_to_next_cell()
        blob = ' '.join(first['lines'])
        self.assertIn('2 storeys (estimate), roof pitched, ridge axis x', blob)

    def test_open_tree_over_roof_is_queued(self):
        gaps = {'layers': [], 'trees_stale': False, 'features': [], 'trees_over_roof': [self.LUMP]}
        with mock.patch.object(H, 'next_cell', return_value=(1, 1, 0)), \
                mock.patch.object(H, 'cell_gaps', return_value=gaps):
            first = H.advance_to_next_cell()
        self.assertIn('TREES OVER ROOF 1', first['text'])


class EndTest(Base):
    def run_end(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()), \
                mock.patch('site_archive.run'):
            rc = H.main(['end', *args, '--summary', 's', '--skip-say', '--skip-view'])
        return rc, out.getvalue()

    def test_end_ticks_releases_and_arms_next(self):
        (self.site / 'LOCK.json').write_text(json.dumps({'owner': 'me', 'task': 'Q-001 …', 'heartbeat': time.time()}))
        H.set_pending('Q-000', {'id': 'Q-001', 'text': 'stale'})
        rc, _ = self.run_end('Q-001')
        self.assertEqual(rc, 0)
        self.assertFalse((self.site / 'LOCK.json').exists())
        self.assertIn('[x] Q-001', H.QUEUE.read_text())
        self.assertIn('[ ] Q-002', H.QUEUE.read_text())
        pend = H.read_pending()
        self.assertEqual((pend['done'], pend['next']), ('Q-001', 'Q-002'))

    def test_end_without_id_uses_lock_task(self):
        (self.site / 'LOCK.json').write_text(json.dumps({'owner': 'me', 'task': 'Q-002 stuff', 'heartbeat': time.time()}))
        self.run_end()
        self.assertIn('[x] Q-002', H.QUEUE.read_text())
        self.assertEqual(H.read_pending()['next'], 'Q-001')

    def test_state_changes_survive_a_later_crash(self):
        (self.site / 'LOCK.json').write_text(json.dumps({'owner': 'me', 'task': 'Q-001', 'heartbeat': time.time()}))
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                mock.patch('site_archive.run', side_effect=IndexError('boom')):
            rc = H.main(['end', 'Q-001', '--summary', 's', '--skip-say', '--skip-view'])
        self.assertEqual(rc, 0)
        self.assertFalse((self.site / 'LOCK.json').exists())
        self.assertIn('[x] Q-001', H.QUEUE.read_text())
        self.assertEqual(H.read_pending()['next'], 'Q-002')

    def test_last_item_leaves_no_next(self):
        H.QUEUE.write_text(QUEUE_TEXT.replace('[ ] Q-002', '[x] Q-002'))
        self.run_end('Q-001')
        self.assertIsNone(H.read_pending()['next'])


if __name__ == '__main__':
    unittest.main()
