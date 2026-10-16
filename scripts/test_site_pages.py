"""site_pages: media matching only links existing files; status classification; issue lookup (temp files only)."""
import tempfile
import unittest
from pathlib import Path

import site_pages as sp


class TestSitePages(unittest.TestCase):
    def test_find_media_links_only_existing_matching_images(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for n in ['highfield_47_m45_ground-preview.png', 'highfield_47_m45_ground-kinds.png', 'cmp-47_m45-strip.png',
                      'other.png', 'cell_marker_47_m45-preview.png', 'highfield_47_m45_notes.txt', 'extra.png',
                      'highfield_48_m44_ground-preview.png']:
                (d / n).write_bytes(b'x')
            sts = {'ground-layer': {'plan': 'highfield_47_m45_ground'}}
            got = {f.name: g for g, f in sp.find_media((47, -45), sts, d, {'extra.png': ['47,-45']})}
            self.assertEqual(set(got), {'highfield_47_m45_ground-preview.png', 'highfield_47_m45_ground-kinds.png',
                                        'cmp-47_m45-strip.png', 'extra.png'})
            self.assertEqual(got['highfield_47_m45_ground-kinds.png'], 'highfield_47_m45_ground')
            self.assertEqual(got['cmp-47_m45-strip.png'], 'Comparisons and extras')
            self.assertEqual(sp.find_media((47, -45), sts, d / 'missing'), [])

    def test_classify(self):
        done = {n: {'status': 'applied'} for n in ('ground-layer', 'trees', 'decor')}
        none = {'in_flight': [], 'layers': [], 'trees_stale': False, 'features': []}
        self.assertEqual(sp.classify((1, 1), done, none, (9, 9), ''), 'Completed')
        self.assertEqual(sp.classify((1, 1), done, none, (1, 1), ''), 'In progress')
        self.assertEqual(sp.classify((1, 1), done, {**none, 'features': [1]}, None, ''), 'Built, items remaining')
        self.assertEqual(sp.classify((1, 1), {}, {**none, 'layers': ['decor']}, None, ''), 'Layers incomplete')
        self.assertEqual(sp.classify((1, 1), done, {**none, 'in_flight': ['x']}, None, ''), 'In progress')
        self.assertEqual(sp.classify((1, 1), done, none, None, 'task on 1,1'), 'In progress')

    def test_issue_lookup_matches_whole_cell_ids(self):
        with tempfile.TemporaryDirectory() as d:
            old = sp.ISSUES
            sp.ISSUES = Path(d) / 'ISSUES.txt'
            sp.ISSUES.write_text('I-001  M  A  open  mentions 47,-45 here\n  more\nI-002  M  B  open  cell 147,-45 not it\nI-003  M  C  open  cell 47,-455\n')
            try:
                self.assertEqual([t.split()[0] for t, _ in sp.issues_for((47, -45))], ['I-001'])
            finally:
                sp.ISSUES = old


if __name__ == '__main__':
    unittest.main()
