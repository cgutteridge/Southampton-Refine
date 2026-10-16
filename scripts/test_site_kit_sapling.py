"""Plan guard: sapling blocks are forbidden."""
from __future__ import annotations

import unittest

from site_kit import Plan


class TestSaplingGuard(unittest.TestCase):
    def test_set_rejects_sapling(self):
        p = Plan('test')
        with self.assertRaises(SystemExit):
            p.set(0, 64, 0, 'oak_sapling')

    def test_set_allows_with_flag(self):
        p = Plan('test')
        p.allow_saplings = True
        p.set(0, 64, 0, 'oak_sapling')
        self.assertIn((0, 64, 0), p.cells)


if __name__ == '__main__':
    unittest.main()
