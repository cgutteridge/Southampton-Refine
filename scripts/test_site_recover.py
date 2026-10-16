"""Tests for the stage state machine (site_stages + site_kit.apply), site_recover.py and the
fail-closed mask undo. Everything runs against a fake world, fake MCP client and temp dirs:
no Minecraft, no real site/ files, no lock claim, no world write."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import mask_undo
import pass_mask as pm
import restore_structure_backup as rsb
import site_kit
import site_lock
import site_recover as sr
import site_stages

AIR = 'minecraft:air'
CELL = (48, -44)
X0, Z0 = 6150, -5600


class View:
    def __init__(self, blocks):
        self.blocks = blocks

    def block(self, x, y, z):
        return self.blocks.get((x, y, z), AIR)


class FakePaced:
    """Fake MCP client over a dict world. Class attributes are reset per test."""
    world = {}
    structures = {}
    calls = []
    stage_at_fill = []
    fill_limit = None        # abort (raise) after this many fill calls have been applied
    skip_fills = False       # fills silently do nothing (readback mismatch)
    abort_on_save = False    # raise on server_save_all_worlds (after the writes, before the readback)
    stage_reader = None

    def __init__(self, *a, **k):
        pass

    def call(self, name, args):
        FakePaced.calls.append(name)
        if name == 'server_save_all_worlds' and FakePaced.abort_on_save:
            raise RuntimeError('server died')
        return {'content': []}

    def text(self, name, args):
        FakePaced.calls.append(name)
        if name == 'structure_save_from_world':
            FakePaced.structures[args['name']] = dict(FakePaced.world)
            return 'saved'
        if name == 'structure_load_to_world':
            FakePaced.world.clear()
            FakePaced.world.update(FakePaced.structures[args['name']])
            return 'loaded'
        if name == 'block_fill_batch':
            if FakePaced.stage_reader:
                FakePaced.stage_at_fill.append(FakePaced.stage_reader())
            for f in args['fills']:
                if FakePaced.fill_limit is not None and FakePaced.fills_done >= FakePaced.fill_limit:
                    raise RuntimeError('server died mid-apply')
                a, b = f['from'], f['to']
                if not FakePaced.skip_fills:
                    for x in range(a[0], b[0] + 1):
                        for y in range(a[1], b[1] + 1):
                            for z in range(a[2], b[2] + 1):
                                FakePaced.world[(x, y, z)] = f['block']
                FakePaced.fills_done += 1
            return 'filled'
        return ''


FakePaced.fills_done = 0


def make_plan(name='p'):
    plan = site_kit.Plan(name)
    plan.fill((X0, 60, Z0), (X0 + 1, 60, Z0), 'minecraft:stone')
    plan.fill((X0, 61, Z0), (X0 + 1, 61, Z0), 'minecraft:oak_log')
    return plan


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        for d in ('out', 'cells', 'snaps', 'masks'):
            (t / d).mkdir()
        FakePaced.world = {(X0, 60, Z0): 'minecraft:dirt'}
        FakePaced.structures, FakePaced.calls, FakePaced.stage_at_fill = {}, [], []
        FakePaced.fill_limit, FakePaced.fills_done = None, 0
        FakePaced.skip_fills = FakePaced.abort_on_save = False
        FakePaced.stage_reader = None
        self.t = t
        patches = [
            mock.patch.object(site_kit, 'OUT', t / 'out'),
            mock.patch.object(site_stages, 'CELLS', t / 'cells'),
            mock.patch.object(site_stages, 'SNAPSHOTS', t / 'snaps'),
            mock.patch.object(site_lock, 'LOCK', t / 'LOCK.json'),
            mock.patch.object(site_kit, 'World', lambda region=None: View(FakePaced.world)),
            mock.patch.object(site_kit, '_bring_player', lambda *a, **k: None),
            mock.patch.object(site_kit, 'built_cells', lambda exclude=(), **kw: {}),
            mock.patch('mc_paced.Paced', FakePaced),
            mock.patch('osm_footprints.guard', lambda cells: {'outside': {}, 'blind': []}),
            mock.patch('roof_lint.ridge_jogs', lambda cells: []),
            mock.patch('time.sleep', lambda s: None),
            mock.patch.dict(os.environ, {'SITE_OWNER': 'alice'}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def stages(self, cell=CELL):
        return json.loads(site_stages.stage_path(cell).read_text())['stages']

    def set_lock(self, owner='alice', age_min=0):
        hb = time.time() - age_min * 60
        site_lock.LOCK.write_text(json.dumps({'owner': owner, 'task': 't', 'claimed': hb, 'heartbeat': hb,
                                              'claimed_at': 'x', 'heartbeat_at': 'x'}))

    def run_apply(self, plan=None, **kw):
        with mock.patch.object(site_lock, 'check', lambda owner=None: None):
            return site_kit.apply(plan or make_plan(), **kw)


class TestStateMachine(Base):
    def test_applying_before_writes_applied_after(self):
        FakePaced.stage_reader = lambda: self.stages()['feature-p']['status']
        self.run_apply()
        self.assertEqual(FakePaced.stage_at_fill, ['applying'] * len(FakePaced.stage_at_fill))
        self.assertTrue(FakePaced.stage_at_fill)
        e = self.stages()['feature-p']
        self.assertEqual(e['status'], 'applied')
        self.assertEqual(e['plan'], 'p')
        self.assertEqual(e['readback']['mismatches'], 0)

    def test_entry_records_what_recovery_needs(self):
        FakePaced.abort_on_save = True
        with self.assertRaises(RuntimeError):
            self.run_apply(stage='trees', cell=CELL)
        e = self.stages()['trees']
        self.assertEqual(e['status'], 'applying')
        self.assertEqual(e['owner'], 'alice')
        self.assertEqual(e['structure']['name'], 'southampton_refine:before_p')
        self.assertEqual(e['structure']['from'], [X0 - 1, 60, Z0 - 1])
        self.assertTrue(Path(e['planned']).exists())
        self.assertIn('started', e)

    def test_abort_mid_apply_leaves_applying(self):
        FakePaced.fill_limit = 1
        with self.assertRaises(RuntimeError):
            self.run_apply()
        self.assertEqual(self.stages()['feature-p']['status'], 'applying')

    def test_reapply_takes_a_fresh_structure_backup(self):
        self.run_apply()
        FakePaced.world[(X0, 60, Z0)] = 'minecraft:coal_block'
        FakePaced.abort_on_save = True
        with self.assertRaises(RuntimeError):
            self.run_apply()
        name = self.stages()['feature-p']['structure']['name']
        self.assertNotEqual(name, 'southampton_refine:before_p')          # the first-time one is the original Geocraft
        self.assertEqual(FakePaced.structures[name][(X0, 60, Z0)], 'minecraft:coal_block')

    def test_strict_readback_mismatch_raises_and_stays_applying(self):
        FakePaced.skip_fills = True
        with self.assertRaises(SystemExit):
            self.run_apply(strict=True)
        self.assertEqual(self.stages()['feature-p']['status'], 'applying')

    def test_mismatch_without_strict_is_recorded(self):
        FakePaced.skip_fills = True
        self.run_apply()
        self.assertEqual(self.stages()['feature-p']['status'], 'applied-with-mismatches')

    def test_hand_written_final_entry_replaces_cleanly(self):
        """Layer scripts overwrite the entry after apply(); an earlier 'applying' leaves no residue."""
        self.run_apply(stage='decor', cell=CELL)
        data = json.loads(site_stages.stage_path(CELL).read_text())
        data['stages']['decor'] = {'status': 'applied', 'plan': 'p', 'blocks': 4}
        site_stages.write(CELL, data)
        self.assertEqual(site_stages.in_flight(self.stages()), [])

    def test_dry_run_writes_no_stage(self):
        self.run_apply(dry=True)
        self.assertFalse(site_stages.stage_path(CELL).exists())


class Aborted(Base):
    """An apply that died after (some of) its writes, plus a lock that has gone stale."""

    def abort(self, **kw):
        FakePaced.world.update(kw.pop('world', {}))
        for k, v in kw.items():
            setattr(FakePaced, k, v)
        with self.assertRaises(RuntimeError):
            self.run_apply(stage='trees', cell=CELL)

    def recover(self, **kw):
        return sr.recover(CELL, apply=kw.pop('apply', True), flush=lambda: None, **kw)


class TestRecover(Aborted):
    def test_world_matches_plan_marks_applied_and_releases_stale_lock(self):
        self.abort(abort_on_save=True)                   # all fills landed, died before the readback
        self.set_lock('alice', age_min=200)
        res = self.recover()
        self.assertEqual(res['action'], 'applied')
        e = self.stages()['trees']
        self.assertEqual(e['status'], 'applied')
        self.assertIn('recovered', e)
        self.assertFalse(site_lock.LOCK.exists())

    def test_world_differs_restores_recorded_structure_and_rolls_back(self):
        before = dict(FakePaced.world)
        self.abort(fill_limit=1)                         # first box written, second never
        self.assertNotEqual(FakePaced.world, before)
        name = self.stages()['trees']['structure']['name']
        self.set_lock('alice', age_min=200)
        loaded = []

        def loader(struct_name, origin):
            loaded.append((struct_name, origin))
            return rsb.load_structure(struct_name, origin, m=FakePaced())
        res = self.recover(loader=loader, snapshot_check=lambda s, p: 0)
        self.assertEqual(res['action'], 'rolled-back')
        self.assertEqual(loaded, [(name, [X0 - 1, 60, Z0 - 1])])
        self.assertEqual(FakePaced.world, before)
        e = self.stages()['trees']
        self.assertEqual(e['status'], 'rolled-back')
        self.assertFalse(site_lock.LOCK.exists())

    def test_rolled_back_is_not_done_and_reappears(self):
        import site_handoff as H
        self.abort(fill_limit=1)
        self.set_lock('alice', age_min=200)
        self.recover(loader=lambda n, o: rsb.load_structure(n, o, m=FakePaced()))
        with mock.patch.object(H, 'SITE', self.t):
            self.assertIn('trees', H.cell_gaps(CELL, features=False)['layers'])

    def test_dry_run_changes_nothing(self):
        self.abort(fill_limit=1)
        self.set_lock('alice', age_min=200)
        res = self.recover(apply=False, loader=lambda n, o: self.fail('must not load'))
        self.assertEqual(res['action'], 'would-rolled-back')
        self.assertEqual(self.stages()['trees']['status'], 'applying')
        self.assertTrue(site_lock.LOCK.exists())

    def test_fresh_lock_is_never_taken_over(self):
        self.abort(fill_limit=1)
        for owner in ('alice', 'bob'):
            self.set_lock(owner, age_min=5)
            before = site_lock.LOCK.read_text()
            res = self.recover(loader=lambda n, o: self.fail('must not load'))
            self.assertEqual(res['action'], 'unsure')
            self.assertEqual(site_lock.LOCK.read_text(), before)
            self.assertEqual(self.stages()['trees']['status'], 'applying')

    def test_stale_lock_of_another_owner_is_not_ours_to_clear(self):
        self.abort(fill_limit=1)
        self.set_lock('bob', age_min=300)
        before = site_lock.LOCK.read_text()
        res = self.recover(loader=lambda n, o: self.fail('must not load'))
        self.assertEqual(res['action'], 'unsure')
        self.assertEqual(site_lock.LOCK.read_text(), before)

    def test_unsure_when_flush_fails_or_plan_missing(self):
        self.abort(fill_limit=1)
        self.set_lock('alice', age_min=200)

        def boom():
            raise RuntimeError('no server')
        res = sr.recover(CELL, apply=True, flush=boom, loader=lambda n, o: self.fail('must not load'))
        self.assertEqual(res['action'], 'unsure')
        Path(self.stages()['trees']['planned']).unlink()
        res = self.recover(loader=lambda n, o: self.fail('must not load'))
        self.assertEqual(res['action'], 'unsure')
        self.assertEqual(self.stages()['trees']['status'], 'applying')

    def test_snapshot_mismatch_after_restore_fails_closed(self):
        self.abort(fill_limit=1)
        data = json.loads(site_stages.stage_path(CELL).read_text())
        data['stages']['trees']['snapshot'] = 'backups/regions/x'
        site_stages.write(CELL, data)
        self.set_lock('alice', age_min=200)
        before = json.loads(site_lock.LOCK.read_text())
        res = self.recover(loader=lambda n, o: rsb.load_structure(n, o, m=FakePaced()),
                           snapshot_check=lambda s, p: 3)
        self.assertEqual(res['action'], 'failed')
        self.assertEqual(self.stages()['trees']['status'], 'applying')
        self.assertEqual(json.loads(site_lock.LOCK.read_text()), before)      # original (stale) lock put back

    def test_status_lists_stale_lock_and_in_flight(self):
        self.abort(fill_limit=1)
        self.set_lock('alice', age_min=200)
        st = sr.status()
        self.assertEqual(st['lock']['state'], 'stale')
        self.assertEqual([(f['cell'], f['stage']) for f in st['in_flight']], [(CELL, 'trees')])
        self.assertEqual(sr.main(['status']), 1)


class TestUndoPaths(Aborted):
    def _undo_setup(self):
        """Trees stage re-applied (and aborted) after a mask undo; the pre-undo world had trees."""
        trees = {(X0, 60, Z0): 'minecraft:oak_log', (X0 + 1, 61, Z0): 'minecraft:oak_leaves'}
        bare = {(X0, 60, Z0): 'minecraft:dirt'}
        FakePaced.structures['ns:before_undo'] = dict(trees)
        FakePaced.world.clear()
        FakePaced.world.update(bare)                         # world after the undo
        mask = pm.build_mask('trees', CELL, 'tp', {(X0 + 1, 61, Z0): 'minecraft:oak_leaves'}, lambda p: True)
        backup = self.t / 'masks' / 'undone' / 'u.mask.json'
        backup.parent.mkdir()
        backup.write_text(json.dumps(mask))
        self.abort(fill_limit=1)
        data = json.loads(site_stages.stage_path(CELL).read_text())
        data['stages']['trees']['previous'] = {'status': 'undone', 'undo_snapshot': {
            'structure': {'name': 'ns:before_undo', 'from': [X0 - 1, 60, Z0 - 1], 'to': [X0 + 2, 61, Z0 + 1]},
            'snapshot': None, 'planned': None, 'mask_backup': str(backup)}}
        site_stages.write(CELL, data)
        self.set_lock('alice', age_min=200)
        return trees, backup

    def test_reapply_aborted_after_undo_restores_the_before_undo_snapshot(self):
        trees, backup = self._undo_setup()
        loaded = []

        def loader(n, o):
            loaded.append(n)
            return rsb.load_structure(n, o, m=FakePaced())
        with mock.patch('pass_mask.mask_path', lambda p, c, d=None: self.t / 'masks' / f'{p}-{c[0]}_{c[1]}.mask.json'):
            res = self.recover(loader=loader, snapshot_check=lambda s, p: 0)
        self.assertEqual(res['action'], 'rolled-back')
        self.assertEqual(loaded, ['southampton_refine:before_p', 'ns:before_undo'])    # apply first, then pre-undo
        self.assertEqual(FakePaced.world, trees)                                       # not left bare
        e = self.stages()['trees']
        self.assertEqual(e['status'], 'rolled-back')
        self.assertEqual(e['recovered']['used_undo_snapshot']['name'], 'ns:before_undo')
        self.assertTrue((self.t / 'masks' / 'trees-48_-44.mask.json').exists())        # mask put back

    def test_aborted_undo_that_matches_finishes_the_bookkeeping(self):
        mask = pm.build_mask('trees', CELL, 'tp', {(X0, 61, Z0): 'minecraft:oak_leaves'}, lambda p: True)
        mpath = self.t / 'masks' / 'trees-48_-44.mask.json'
        mpath.write_text(json.dumps(mask))
        plan = site_kit.Plan('p_trees_undo')
        plan.set(X0, 61, Z0, 'air')
        FakePaced.world[(X0, 61, Z0)] = 'minecraft:oak_leaves'
        FakePaced.abort_on_save = True
        with mock.patch.object(site_lock, 'check', lambda owner=None: None), self.assertRaises(RuntimeError):
            site_kit.apply(plan, stage='trees-undo', cell=CELL, strict=True, meta={'kind': 'undo', 'pass': 'trees'})
        self.set_lock('alice', age_min=200)
        mp = lambda p, c, d=None: self.t / 'masks' / f'{p}-{c[0]}_{c[1]}.mask.json'
        with mock.patch.object(mask_undo, 'mask_path', mp):
            res = self.recover()
        self.assertEqual(res['action'], 'applied')
        self.assertFalse(mpath.exists())
        self.assertTrue((self.t / 'masks' / 'undone' / 'p_trees_undo.mask.json').exists())
        s = self.stages()
        self.assertEqual(s['trees-undo']['status'], 'applied')
        self.assertEqual(s['trees']['status'], 'undone')
        self.assertEqual(s['trees']['undo_snapshot']['structure']['name'], s['trees-undo']['structure']['name'])


class TestUndoFailsClosed(Base):
    def setUp(self):
        super().setUp()
        self.mask = pm.build_mask('trees', CELL, 'tp', {(X0, 61, Z0): 'minecraft:oak_leaves',
                                                        (X0 + 1, 61, Z0): 'minecraft:oak_leaves'}, lambda p: True)
        self.mpath = pm.write_mask(self.mask, self.t / 'masks')
        for p in (mock.patch.object(mask_undo, 'mask_path', lambda pn, c, d=None: self.mpath),
                  mock.patch.object(mask_undo, 'shared_positions', lambda m: set()),
                  mock.patch.object(mask_undo, 'World', lambda: View(FakePaced.world)),
                  mock.patch.object(mask_undo, 'ignored_builds', lambda c: ())):
            p.start()
            self.addCleanup(p.stop)

    def test_conflict_raises_instead_of_returning(self):
        FakePaced.world[(X0, 61, Z0)] = 'minecraft:oak_leaves'          # the other position is already air
        with self.assertRaises(SystemExit):
            mask_undo.run(CELL, 'trees', live=False)
        with self.assertRaises(SystemExit):
            mask_undo.run(CELL, 'trees', live=True)
        self.assertTrue(self.mpath.exists())                             # mask kept: a caller cannot carry on over it
        self.assertFalse(site_stages.stage_path(CELL).exists())

    def test_live_flush_failure_raises(self):
        FakePaced.abort_on_save = True
        with self.assertRaises(SystemExit):
            mask_undo.run(CELL, 'trees', live=True)

    def test_live_undo_readback_mismatch_raises_and_keeps_mask(self):
        FakePaced.world.update({(X0, 61, Z0): 'minecraft:oak_leaves', (X0 + 1, 61, Z0): 'minecraft:oak_leaves'})
        FakePaced.skip_fills = True
        with mock.patch('subprocess.run'), mock.patch.object(site_lock, 'check', lambda owner=None: None), \
                mock.patch.object(mask_undo, 'plan_name', lambda tx, tz, s: f'u_{s}', create=True), \
                mock.patch('ground_layer.cell_bbox_str', lambda c, m=0: '0,0,1,1'):
            with self.assertRaises(SystemExit):
                mask_undo.run(CELL, 'trees', live=True)
        self.assertTrue(self.mpath.exists())
        self.assertEqual(self.stages()['trees-undo']['status'], 'applying')

    def test_clean_live_undo_archives_the_mask(self):
        FakePaced.world.update({(X0, 61, Z0): 'minecraft:oak_leaves', (X0 + 1, 61, Z0): 'minecraft:oak_leaves'})
        with mock.patch('subprocess.run'), mock.patch.object(site_lock, 'check', lambda owner=None: None), \
                mock.patch.object(mask_undo, 'plan_name', lambda tx, tz, s: f'u_{s}', create=True), \
                mock.patch('ground_layer.cell_bbox_str', lambda c, m=0: '0,0,1,1'):
            self.assertEqual(mask_undo.run(CELL, 'trees', live=True), 0)
        self.assertFalse(self.mpath.exists())
        self.assertEqual(self.stages()['trees']['status'], 'undone')


if __name__ == '__main__':
    unittest.main()
