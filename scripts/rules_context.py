"""Classify QUEUE items and format context-specific reading lists (token budget).

Canonical prose lives in site/RULES-CONTEXT.txt; this module is what
site_handoff.py uses to inject RULES READING into the SESSION BRIEF.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from script_env import ROOT  # noqa: E402
RULES_INDEX = ROOT / 'site' / 'RULES-CONTEXT.txt'

# Explicit override in queue text: RULES: foliage
RULES_TAG = re.compile(r'\bRULES:\s*([a-z]+)\b', re.I)


class WorkContext(str, Enum):
    """Primary reading context for one queue item."""

    SESSION = 'session'
    TOOLING = 'tooling'
    SOURCES = 'sources'
    GROUND = 'ground'
    FOLIAGE = 'foliage'
    PROPERTY = 'property'
    TERRACE = 'terrace'
    CAMPUS = 'campus'


@dataclass(frozen=True)
class ReadingItem:
    """One file the agent should read (or a slice of it)."""

    path: str
    note: str


@dataclass(frozen=True)
class ContextPlan:
    """Resolved reading plan for a queue item."""

    context: WorkContext
    process_slices: tuple[str, ...]
    readings: tuple[ReadingItem, ...]
    detect_note: str


_ALWAYS = (
    ReadingItem('rules/radial-good-enough.md', 'every live edit'),
    ReadingItem('rules/geocraft-accuracy.md', 'every live edit'),
)
_IMAGERY = (
    ReadingItem('rules/reference-token-budget.md', 'before any ref fetch/Read'),
)


def _blob(item: dict) -> str:
    """Concatenate queue item lines for keyword detection.

    @param item: queue item dict with ``lines`` or ``text``
    @returns: uppercased search blob
    """
    parts = item.get('lines') or [item.get('text', '')]
    return ' '.join(parts).upper()


def _tag_override(blob: str) -> WorkContext | None:
    """Parse ``RULES: context`` from queue text.

    @param blob: uppercased queue blob
    @returns: WorkContext if tag present and valid
    """
    m = RULES_TAG.search(blob)
    if not m:
        return None
    key = m.group(1).lower()
    try:
        return WorkContext(key)
    except ValueError:
        return None


def detect_context(item: dict) -> tuple[WorkContext, str]:
    """Guess primary work context from queue item text.

    @param item: queue item dict
    @returns: (context, short reason for SESSION BRIEF)
    """
    tagged = _tag_override(_blob(item))
    if tagged is not None:
        return tagged, 'RULES: tag in queue text'

    b = _blob(item)
    if any(k in b for k in ('SETUP:', 'TOOLING', 'SCRIPTS/COVERAGE', 'Q-038', 'NO WORLD', 'TESTS ONLY')):
        return WorkContext.TOOLING, 'tooling / coverage scripts keywords'
    if any(k in b for k in ('CELL_SOURCES', 'SOURCES PASS', 'SOURCES.TXT', 'SOURCES —', 'SOURCES—')):
        return WorkContext.SOURCES, 'cell sources pass'
    if 'CELL_SOURCES.PY' in b or ('SOURCES' in b and '--WRITE' in b):
        return WorkContext.SOURCES, 'cell_sources --write'

    if any(k in b for k in ('BUILD_CELL_FOLIAGE', 'FOLIAGE LAST', 'FOLIAGE PASS', 'FOLIAGE.')):
        return WorkContext.FOLIAGE, 'foliage-last cell pass'
    if any(k in b for k in ('TERRACE.PY', 'TERRACE-BUILDS', 'BROADLANDS_RD', ' BROADLANDS ')):
        return WorkContext.TERRACE, 'terrace generator / Broadlands'
    if any(k in b for k in ('FAÇADE', 'FACADE', 'FRONTAGE SURVEY', 'WHOLE PROPERTY', 'OSM_FOOTPRINTS.PY FRONTAGE')):
        return WorkContext.PROPERTY, 'whole-property / frontage survey'
    if 'CAMPUS.PY' in b or re.search(r'\bCAMPUS\b', b) and 'HIGHFIELD' in b:
        return WorkContext.CAMPUS, 'campus building script'

    if 'CELL ' in b or re.search(r'\bCELL\s+-?\d+', b):
        if any(k in b for k in (
            'GROUNDS', 'TIDY', 'OPENS', 'CLEARS', 'PATH', 'FOOTWAY', 'GAP', 'MICRO',
            'SURFACE', 'FINISH', 'PARCEL', 'SIGNOFF', 'COVERAGE.PY', 'ROAD:', 'PROP:',
            'Q-05', 'HIGHFIELD_Q', 'GROUND_',
        )):
            return WorkContext.GROUND, 'cell ground / parcel batch'
        return WorkContext.GROUND, 'CELL item (default ground, not property)'

    if any(k in b for k in ('STREETSCAPE', 'KERB', 'RING ', 'PAVEMENT')):
        return WorkContext.GROUND, 'streetscape / kerb work'

    return WorkContext.PROPERTY, 'default (whole-property bar)'


def _process_slices(ctx: WorkContext) -> tuple[str, ...]:
    """PROCESS.txt section ids to read for a context.

    @param ctx: primary work context
    @returns: human-readable slice labels
    """
    base = ('§2 cadence', '§2a region snap when needed', '§6–§7 session/handoff')
    if ctx == WorkContext.TOOLING:
        return ('§2c coverage CLI', '§6–§7 if closing a stage')
    if ctx == WorkContext.SOURCES:
        return ('§2b refs', '§2e step 1b sources', 'reference/LOGGING.txt §8')
    if ctx in (WorkContext.GROUND, WorkContext.FOLIAGE):
        extra = ('§2c', '§2e')
        if ctx == WorkContext.FOLIAGE:
            extra = extra + ('§2e step 5 layered passes',)
        return base + extra
    if ctx == WorkContext.PROPERTY:
        return base + ('§2b', '§2c', '§2d-i newer than OSM', '§3 checklist as needed')
    if ctx == WorkContext.TERRACE:
        return base + ('§2b', '§2c', '§2d')
    if ctx == WorkContext.CAMPUS:
        return base + ('§2b', '§2c', '§2d')
    return base


def _readings_for(ctx: WorkContext, cell_sources_rel: str | None) -> tuple[ReadingItem, ...]:
    """Expand reading list for a context.

    @param ctx: primary work context
    @param cell_sources_rel: repo-relative path to *-SOURCES.txt if any
    @returns: ordered unique readings
    """
    out: list[ReadingItem] = []
    seen: set[str] = set()

    def add(*items: ReadingItem) -> None:
        for it in items:
            if it.path in seen:
                continue
            seen.add(it.path)
            out.append(it)

    if ctx == WorkContext.SESSION:
        add(ReadingItem('site/RULES-CONTEXT.txt', '§0 anti-reread'))
        return tuple(out)

    if ctx == WorkContext.TOOLING:
        add(ReadingItem('site/RULES-CONTEXT.txt', '§0 anti-reread'))
        return tuple(out)

    add(*_ALWAYS)
    add(ReadingItem('site/RULES-CONTEXT.txt', '§0 anti-reread'))

    if ctx == WorkContext.SOURCES:
        add(*_IMAGERY)
        if cell_sources_rel:
            add(ReadingItem(cell_sources_rel, 'before imagery; TOKEN NOTES inside'))
        return tuple(out)

    if ctx in (WorkContext.GROUND, WorkContext.FOLIAGE):
        add(ReadingItem('site/CRAFTSMANSHIP.txt', 'Processed ground + good-enough only'))
        if ctx == WorkContext.FOLIAGE:
            add(ReadingItem('site/FOLIAGE.txt', 'full'))
        else:
            add(ReadingItem('site/FOLIAGE.txt', 'skim unless placing trees'))
        add(ReadingItem('site/HIGHFIELD-ZONES.txt', 'only if HIGHFIELD grounds in item'))
        add(*_IMAGERY)
        if cell_sources_rel:
            add(ReadingItem(cell_sources_rel, 'imagery ids; do not repeat sources pass'))
        return tuple(out)

    if ctx == WorkContext.PROPERTY:
        add(
            ReadingItem('rules/frontage-and-evidence.md', 'before house/plot plan'),
            ReadingItem('site/CRAFTSMANSHIP.txt', 'full'),
            *_IMAGERY,
        )
        if cell_sources_rel:
            add(ReadingItem(cell_sources_rel, 'before imagery'))
        return tuple(out)

    if ctx == WorkContext.TERRACE:
        add(
            ReadingItem('rules/frontage-and-evidence.md', 'before plan'),
            ReadingItem('site/CRAFTSMANSHIP.txt', 'full'),
            ReadingItem('rules/terrace-builds.md', 'generator mandatory'),
            *_IMAGERY,
        )
        if cell_sources_rel:
            add(ReadingItem(cell_sources_rel, 'before imagery'))
        return tuple(out)

    if ctx == WorkContext.CAMPUS:
        add(
            ReadingItem(
                'rules/frontage-and-evidence.md',
                'footprint/plot sections if OSM homes',
            ),
            *_IMAGERY,
        )
        if cell_sources_rel:
            add(ReadingItem(cell_sources_rel, 'before imagery'))
        return tuple(out)

    return tuple(out)


def plan_for_item(item: dict, cell_sources_rel: str | None = None) -> ContextPlan:
    """Build the full reading plan for one queue item.

    @param item: queue item dict
    @param cell_sources_rel: optional repo-relative cell SOURCES path
    @returns: ContextPlan for brief injection
    """
    ctx, note = detect_context(item)
    return ContextPlan(
        context=ctx,
        process_slices=_process_slices(ctx),
        readings=_readings_for(ctx, cell_sources_rel),
        detect_note=note,
    )


_DONE_HINTS: dict[WorkContext, str] = {
    WorkContext.TOOLING: 'Tests/docs only; no live apply unless item says so.',
    WorkContext.SOURCES: 'Write SOURCES file; one imagery judge pass; TOKEN NOTES in file.',
    WorkContext.GROUND: 'Apply → readback → signoff touched parcels → status --write → gaps.',
    WorkContext.FOLIAGE: (
        'build_cell_foliage dry-run then SITE_OWNER --apply; script signs in-cell open/gap.'
    ),
    WorkContext.PROPERTY: (
        'Whole property on OSM footprint; osm_footprints check; photo + aerial contact views.'
    ),
    WorkContext.TERRACE: 'terrace.py generator; re-apply same build name; no _b geometry patches.',
    WorkContext.CAMPUS: 'campus.py pattern; walks on dry-run plan before first apply.',
    WorkContext.SESSION: 'Lock + handoff only.',
}


def format_rules_brief(plan: ContextPlan) -> str:
    """Format RULES READING block for SESSION BRIEF.

    @param plan: resolved context plan
    @returns: multi-line string (no trailing newline required)
    """
    lines = [
        f'RULES CONTEXT: {plan.context.value} ({plan.detect_note})',
        '  Index: site/RULES-CONTEXT.txt — read each path below once this chat; grep slices later.',
        '',
        '  PROCESS.txt slices (sed -n / grep — not the whole file):',
    ]
    for sl in plan.process_slices:
        lines.append(f'    - {sl}')
    lines.append('')
    lines.append('  Read now (this item):')
    for r in plan.readings:
        lines.append(f'    - {r.path}  — {r.note}')
    hint = _DONE_HINTS.get(plan.context)
    if hint:
        lines.append('')
        lines.append(f'  Done bar (this context): {hint}')
    return '\n'.join(lines)


def format_starter_rules_line(plan: ContextPlan) -> str:
    """One-line pointer for the boot starter (avoids listing every rules file).

    @param plan: resolved context plan
    @returns: single sentence for starter_text
    """
    names = [r.path for r in plan.readings if r.path.endswith('.md')]
    if not names:
        return (
            f'Rules: context={plan.context.value} — follow RULES READING in SESSION BRIEF '
            f'(site/RULES-CONTEXT.txt). Read PROCESS slices listed there, not all of PROCESS.txt.'
        )
    head = ', '.join(Path(p).name for p in names[:4])
    extra = '…' if len(names) > 4 else ''
    return (
        f'Rules: context={plan.context.value} — read {head}{extra} and any site/*.txt '
        f'listed under RULES READING in the SESSION BRIEF (once per chat).'
    )
