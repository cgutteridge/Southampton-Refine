#!/bin/bash
# OPTIONAL — not part of handoff. Prefer one-shot in Terminal:
#   python3 scripts/aerial_mosaic.py --at X,Z --place … --dir aerial/… --add
# Use this only if you want the agent to download Hub tiles itself.
cd "$(dirname "$0")/.." || exit 1
echo "Southampton Refine — optional ref_fetch_agent (Ctrl+C to stop)"
echo
exec python3 scripts/ref_fetch_agent.py
