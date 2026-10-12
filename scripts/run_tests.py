#!/usr/bin/env python3
"""Run stdlib unit tests for scripts in this repository (no Minecraft required).

  python3 scripts/run_tests.py

Exits 0 when all tests pass, 1 otherwise. Use before handoff or in CI.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


def main() -> int:
    """Discover and run all ``test_*.py`` modules under ``scripts/``.

    @returns: process exit code (0 success, 1 if any test failed)
    """
    scripts = Path(__file__).resolve().parent
    suite = unittest.TestLoader().discover(str(scripts), pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
