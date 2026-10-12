#!/usr/bin/env python3
"""Unit tests for scripts/site_archive.py (stdlib unittest, temp dirs only).

  python3 -m unittest scripts/test_site_archive.py
"""
from __future__ import annotations

import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import site_archive as sa  # noqa: E402

QUEUE = """\
SOUTHAMPTON REFINE — QUEUE
Mark [x] when done.

[x] Q-001  SETUP: done thing.
           more detail.

[ ] Q-040  BROADLANDS: open thing
           detail.
[-] Q-023  PAUSED thing
           detail.
[x] Q-038  TOOLING: done later.

BACKLOG (do not block setup)
[ ] Q-011  BACKLOG: aerial check
"""

ISSUES = """\
SOUTHAMPTON REFINE — ISSUES
Format: I-nnn  sev  place  status  summary

------------------------------------------------------------------------

I-001  L  SETUP  done  Fixed long ago
  detail one.

I-002  L  SETUP  open  Still open
  detail two.

I-028  M  TOOL fixed  view_capture 429
  detail.

I-005  L  PORTSWOOD  sched  Scheduled
  detail.
"""

REVIEWS = """\
SOUTHAMPTON REFINE — REVIEWS
One dated line per review.

------------------------------------------------------------------------

2026-10-11  First.
            more.

TOKEN NOTES (Q-002)
- note a

2026-10-11  Second.

2026-10-12  Third.
"""


class SiteArchiveTest(unittest.TestCase):
    """End-to-end behaviour of ``run`` on a scratch site directory."""

    def setUp(self):
        """Create a temp site/ with the three fixture files."""
        self._tmp = tempfile.TemporaryDirectory()
        self.site = Path(self._tmp.name)
        for name, text in (('QUEUE.txt', QUEUE), ('ISSUES.txt', ISSUES), ('REVIEWS.txt', REVIEWS)):
            (self.site / name).write_text(text, encoding='utf-8')

    def tearDown(self):
        """Remove the temp site/."""
        self._tmp.cleanup()

    def _run(self, **kw):
        """Run the archiver quietly and return the moved count."""
        return sa.run(site=self.site, out=io.StringIO(), **kw)

    def _read(self, rel):
        """Read a file under the temp site/."""
        return (self.site / rel).read_text(encoding='utf-8')

    def test_queue_moves_only_done_items(self):
        """[x] items move; open, paused and backlog items and headers stay."""
        self._run(keep_reviews=1)
        live, arc = self._read('QUEUE.txt'), self._read('archive/QUEUE-done.txt')
        for qid in ('Q-040', 'Q-023', 'Q-011', 'BACKLOG (do not block setup)'):
            self.assertIn(qid, live)
        for qid in ('Q-001', 'Q-038'):
            self.assertNotIn(qid, live)
            self.assertIn(qid, arc)
        self.assertIn('           more detail.', arc)
        self.assertIn('Done items: site/archive/QUEUE-done.txt', live.splitlines()[2])

    def test_issues_move_done_and_fixed(self):
        """done/fixed issues move with their detail; open and sched stay."""
        self._run(keep_reviews=1)
        live, arc = self._read('ISSUES.txt'), self._read('archive/ISSUES-closed.txt')
        self.assertIn('I-002', live)
        self.assertIn('I-005', live)
        self.assertIn('-----', live)
        self.assertIn('I-001', arc)
        self.assertIn('I-028', arc)
        self.assertIn('  detail one.', arc)
        self.assertNotIn('I-001', live)

    def test_reviews_keep_last_n_with_token_notes(self):
        """Older dated entries move together with their TOKEN NOTES."""
        self._run(keep_reviews=1)
        live, arc = self._read('REVIEWS.txt'), self._read('archive/REVIEWS-archive.txt')
        self.assertIn('Third.', live)
        self.assertNotIn('First.', live)
        self.assertIn('First.', arc)
        self.assertIn('TOKEN NOTES (Q-002)', arc)
        self.assertLess(arc.index('First.'), arc.index('Second.'))

    def test_rerun_is_idempotent(self):
        """A second run moves nothing and changes no file."""
        self._run(keep_reviews=1)
        before = {p: p.read_text() for p in self.site.rglob('*.txt')}
        self.assertEqual(self._run(keep_reviews=1), 0)
        self.assertEqual(before, {p: p.read_text() for p in self.site.rglob('*.txt')})

    def test_interrupted_run_does_not_duplicate(self):
        """If the archive was written but the live file was not, re-run dedupes."""
        self._run(keep_reviews=1)
        (self.site / 'QUEUE.txt').write_text(QUEUE, encoding='utf-8')
        self._run(keep_reviews=1)
        self.assertEqual(self._read('archive/QUEUE-done.txt').count('Q-001'), 1)
        self.assertNotIn('Q-001', self._read('QUEUE.txt'))

    def test_dry_run_writes_nothing(self):
        """--dry-run reports counts but leaves every file untouched."""
        n = self._run(dry=True, keep_reviews=1)
        self.assertEqual(n, 2 + 2 + 2)
        self.assertFalse((self.site / 'archive').exists())
        self.assertEqual(self._read('QUEUE.txt'), QUEUE)

    def test_next_id_sees_archive(self):
        """next-id counts ids that now live only in the archive."""
        (self.site / 'QUEUE.txt').write_text('[x] Q-099  done\n', encoding='utf-8')
        self._run()
        self.assertNotIn('Q-099', self._read('QUEUE.txt'))
        self.assertEqual(sa.next_id('Q', self.site), 'Q-100')
        self.assertEqual(sa.next_id('I', self.site), 'I-029')

    def test_negative_keep_rejected(self):
        """plan_reviews refuses a negative keep count."""
        with self.assertRaises(ValueError):
            sa.plan_reviews(REVIEWS, keep=-1)


if __name__ == '__main__':
    unittest.main()
