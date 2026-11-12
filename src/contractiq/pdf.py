"""Read a document into pages of text, then into logical blocks (paragraphs, rows, headings).

Two things matter for extraction quality and are handled here:

* Running headers and footers ("Page 3", agency banners) are removed so they are
  never mistaken for content.
* Wrapped lines are joined back into paragraphs, and a paragraph that runs over a
  page break stays in one piece (it is credited to the page where it starts).
"""
from __future__ import annotations

import io
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_TEXT_SUFFIXES = {".txt", ".md"}


def read_pages(source: str | Path | bytes, name: str = "") -> list[str]:
    """Return the text of each page. `source` is a path, or raw PDF bytes (then pass `name`)."""
    if isinstance(source, (bytes, bytearray)):
        suffix = Path(name).suffix.lower()
        if suffix in _TEXT_SUFFIXES:
            pages = bytes(source).decode("utf-8", errors="replace").split("\f")
        else:
            pages = _pdf_pages(io.BytesIO(bytes(source)))
    else:
        path = Path(source)
        if path.suffix.lower() in _TEXT_SUFFIXES:
            pages = path.read_text(encoding="utf-8", errors="replace").split("\f")
        else:
            pages = _pdf_pages(str(path))
    return strip_repeated_lines(pages)


def _pdf_pages(src) -> list[str]:
    import pdfplumber

    with pdfplumber.open(src) as pdf:
        return [(pg.extract_text() or "") for pg in pdf.pages]


def strip_repeated_lines(pages: list[str]) -> list[str]:
    """Drop lines that repeat at the top or bottom of most pages (headers, footers, page numbers)."""
    n = len(pages)
    if n < 3:
        return pages

    def key(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip().lower())

    def edge_indexes(lines: list[str]) -> list[int]:
        idx = [i for i, ln in enumerate(lines) if ln.strip()]
        return idx[:2] + idx[-2:]

    counts: Counter[str] = Counter()
    split = [p.splitlines() for p in pages]
    for lines in split:
        counts.update({key(lines[i]) for i in edge_indexes(lines)})
    threshold = max(2, math.ceil(0.6 * n))
    out = []
    for lines in split:
        drop = {i for i in edge_indexes(lines) if counts[key(lines[i])] >= threshold}
        out.append("\n".join(ln for i, ln in enumerate(lines) if i not in drop))
    return out


# ---------------------------------------------------------------------------
@dataclass
class Block:
    page: int          # 1-based page where the block starts
    text: str
    kind: str = "text"  # text | ref | section | clin | factor | subfactor | cdrl | label
    ref: str = ""       # paragraph reference such as C.3.2
    letter: str = ""    # solicitation section letter (A-M) this block sits in, if known


_RULES = [
    ("section", re.compile(r"^SECTION\s+([A-Z])\b", re.I)),
    ("clin", re.compile(r"^CLIN\s+\d{4}", re.I)),
    ("subfactor", re.compile(r"^Sub-?factor\s+\d", re.I)),
    ("factor", re.compile(r"^Factor\s+\d", re.I)),
    ("cdrl", re.compile(r"^(?:[A-Z]\d{3}[A-Z]?\s*\||ID\s*\|)")),
    ("ref", re.compile(r"^([A-Z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)+)\s+(?=[A-Z(\"])")),
    ("label", re.compile(r"^[A-Z][A-Za-z/\- ]{2,40}:\s+\S")),
]


_SINGLE_LINE = {"label", "clin", "factor", "subfactor", "cdrl", "section"}


def to_blocks(pages: list[str]) -> list[Block]:
    blocks: list[Block] = []
    cur: Block | None = None
    letter = ""

    def flush():
        nonlocal cur
        if cur and cur.text.strip():
            cur.text = " ".join(cur.text.split())
            blocks.append(cur)
        cur = None

    for pno, text in enumerate(pages, start=1):
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            kind = next((k for k, rx in _RULES if rx.match(line)), None)
            if kind:
                flush()
                ref = ""
                if kind == "section":
                    letter = _RULES[0][1].match(line).group(1).upper()
                elif kind == "ref":
                    ref = _RULES[5][1].match(line).group(1)
                    if re.match(r"[A-Z]\.", ref):
                        letter = ref[0]
                cur = Block(page=pno, text=line, kind=kind, ref=ref, letter=letter)
            elif cur is None or (cur.kind in _SINGLE_LINE and line[0].isupper()):
                # one-line items (labelled fields, CLIN/CDRL rows, factors) are not continued by a
                # line that starts a new capitalised phrase, e.g. the next heading
                flush()
                cur = Block(page=pno, text=line, kind="text", letter=letter)
            else:
                cur.text += " " + line
        # a block may continue onto the next page, so it is not flushed here
    flush()
    return blocks
