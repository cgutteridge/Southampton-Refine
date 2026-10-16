#!/usr/bin/env python3
"""Prove house_build.py reproduces an old per-run script: plan cells must be identical.

Usage: .venv/bin/python scripts/prove_house_build.py <old script stem in scripts/legacy, e.g. build_granby_grove_q165_51_45> <spec.json>
"""
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / 'legacy'))
import house_build  # noqa: E402

old = importlib.import_module(sys.argv[1]).build()
spec = house_build.load_spec(sys.argv[2])
spec['door_frame'] = False          # old scripts pick doors without the framing rule
new = house_build.build(spec)
a, b = dict(old.cells), dict(new.cells)
diff = {q for q in set(a) | set(b) if a.get(q) != b.get(q)}
print(f'old {len(a)} cells, new {len(b)} cells, differing {len(diff)}')
for q in sorted(diff)[:10]:
    print(q, a.get(q), b.get(q))
sys.exit(1 if diff else 0)
