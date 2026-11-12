"""Check that each extracted item's quoted evidence really appears in the document.

This is the guard against an LLM inventing text: a quote that cannot be found is
flagged `grounded=False` and reported in `warnings`, and the UI/exports show it.
Comparison ignores case, spacing and punctuation so line wraps and curly quotes
do not cause false alarms.
"""
from __future__ import annotations

import re

from .schema import Extraction


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def ground(ex: Extraction, pages: list[str]) -> int:
    """Set `grounded` (and correct `page`) on every evidence item. Returns the number ungrounded."""
    norm = [_norm(p) for p in pages]
    bad = 0
    for item in ex.evidence_items():
        q = _norm(item.evidence)
        if len(q) < 4:
            item.grounded = False
            bad += 1
            continue
        start = (item.page - 1) if item.page and 1 <= item.page <= len(pages) else 0
        order = [start] + [i for i in range(len(pages)) if i != start]
        found = next((i for i in order if q in norm[i]), None)
        if found is None:  # a quote that runs over a page break
            found = next((i for i in order if i + 1 < len(norm) and q in norm[i] + norm[i + 1]), None)
        if found is None:
            item.grounded = False
            bad += 1
        else:
            item.grounded = True
            item.page = found + 1
    if bad:
        ex.warnings.append(f"{bad} item(s) quote text that was not found in the document; check the 'grounded' flag.")
    return bad
