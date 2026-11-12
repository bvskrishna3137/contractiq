"""End-to-end: file in, validated `Extraction` out."""
from __future__ import annotations

from pathlib import Path

from . import __version__
from .grounding import ground
from .pdf import read_pages
from .schema import Extraction


def run(source: str | Path | bytes, *, name: str = "", mode: str = "rules", model: str | None = None,
        client=None, progress=None) -> Extraction:
    """Extract from a PDF/text file (path or bytes). `mode` is "rules" (offline) or "llm"."""
    if mode not in {"rules", "llm"}:
        raise ValueError("mode must be 'rules' or 'llm'")
    pages = read_pages(source, name=name)
    label = name or (Path(source).name if not isinstance(source, (bytes, bytearray)) else "upload")
    return run_pages(pages, source_name=label, mode=mode, model=model, client=client, progress=progress)


def run_pages(pages: list[str], *, source_name: str = "", mode: str = "rules", model: str | None = None,
              client=None, progress=None) -> Extraction:
    empty = [i + 1 for i, p in enumerate(pages) if len(p.strip()) < 20]
    if mode == "llm":
        from .extractors import llm
        ex, used_model = llm.extract(pages, client=client, model=model, progress=progress)
    else:
        from .extractors import rules
        ex, used_model = rules.extract(pages), ""
    if empty and len(empty) == len(pages):
        ex.warnings.append("No text could be read. This looks like a scanned PDF; run OCR first (for example ocrmypdf).")
    elif empty:
        ex.warnings.append(f"Page(s) {', '.join(map(str, empty))} contain almost no text (scanned or image-only?).")
    ground(ex, pages)
    for i, r in enumerate(ex.requirements, start=1):
        r.id = f"R-{i:03d}"
    ex.requirements.sort(key=lambda r: (r.page or 0, r.id))
    for i, r in enumerate(ex.requirements, start=1):
        r.id = f"R-{i:03d}"
    ex.metadata.source_file = source_name
    ex.metadata.page_count = len(pages)
    ex.metadata.mode = mode  # type: ignore[assignment]
    ex.metadata.model = used_model
    ex.metadata.contractiq_version = __version__
    return ex
