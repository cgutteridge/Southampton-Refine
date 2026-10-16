"""Shared script preamble: ``from script_env import ROOT`` replaces the per-file path boilerplate.

Scripts live in scripts/, which Python puts on sys.path when one is run (or imported from a sibling), so
no sys.path.insert is needed any more.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / 'scripts'


def make_parser(doc: str | None, **kw) -> argparse.ArgumentParser:
    """ArgumentParser that shows the module docstring verbatim as its description."""
    return argparse.ArgumentParser(description=doc, formatter_class=argparse.RawDescriptionHelpFormatter, **kw)
