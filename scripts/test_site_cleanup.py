"""Tests for site_cleanup: retention rules and that apply keeps the manifest tombstones."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import site_cleanup as sc


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        for name, val in (('ROOT', self.root), ('SITE', self.root / 'site'), ('LOG', self.root / 'site/CLEANUP-LOG.txt'),
                          ('MANIFEST', self.root / 'reference/manifest.jsonl')):
            p = mock.patch.object(sc, name, val)
            p.start()
            self.addCleanup(p.stop)
        (self.root / 'site').mkdir()
        (self.root / 'reference').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def _snaps(self, *names):
        for n in names:
            d = self.root / 'backups/regions' / n
            d.mkdir(parents=True)
            (d / 'r.0.0.mca').write_bytes(b'x' * 10)

    def test_snaps_keep_newest_and_open_work(self):
        self._snaps('2026-10-01-000001-Q-001', '2026-10-02-000001-Q-002', '2026-10-03-000001-Q-003',
                    '2026-10-04-000001-Q-004')
        got = {i.path.name for i in sc.plan_region_snaps(keep=1, text='Issue I-9 needs the Q-002 snap')}
        self.assertEqual(got, {'2026-10-01-000001-Q-001', '2026-10-03-000001-Q-003'})

    def test_views_age_and_mention(self):
        v = self.root / 'verification/site/views'
        v.mkdir(parents=True)
        old = time.time() - 30 * 86400
        for n in ('a.png', 'b.png', 'new.png'):
            (v / n).write_bytes(b'x')
        for n in ('a.png', 'b.png'):
            os.utime(v / n, (old, old))
        got = {i.path.name for i in sc.plan_views(days=7, text='see views/b.png')}
        self.assertEqual(got, {'a.png'})

    def test_reference_junk_apply_keeps_row(self):
        f = self.root / 'reference/photos/x/p.jpg'
        f.parent.mkdir(parents=True)
        f.write_bytes(b'jpg')
        row = {'id': 'p1', 'path': 'photos/x/p.jpg', 'url': 'http://u', 'sha256': 'abc', 'useful': 'no', 'notes': 'wrong street'}
        sc.MANIFEST.write_text(json.dumps(row) + '\n')
        items = sc.plan_reference_junk(rows=[row], check_blank=False)
        self.assertEqual(len(items), 1)
        with mock.patch('ref_manifest.MANIFEST', sc.MANIFEST):
            sc.apply_class('reference-junk', items, today='2026-10-20')
        self.assertFalse(f.exists())
        kept = json.loads(sc.MANIFEST.read_text())
        self.assertEqual((kept['url'], kept['sha256'], kept['removed']), ('http://u', 'abc', '2026-10-20'))
        self.assertIn('wrong street', kept['removed_reason'])
        self.assertIn('2026-10-20 reference-junk: removed 1', sc.LOG.read_text())
        self.assertEqual(sc.plan_reference_junk(rows=[kept], check_blank=False), [])

    def test_due(self):
        self.assertEqual(sc.due_reason(), 'never cleaned')
        sc._log(['2026-10-01 views: removed 0 (0 MB)'])
        now = time.mktime(time.strptime('2026-10-05', '%Y-%m-%d'))
        self.assertEqual(sc.due_reason(now), '')
        now = time.mktime(time.strptime('2026-10-20', '%Y-%m-%d'))
        self.assertIn('days ago', sc.due_reason(now))


if __name__ == '__main__':
    unittest.main()
