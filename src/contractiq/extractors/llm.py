"""LLM extractor: Anthropic tool use with a forced, schema-validated output.

How it works
------------
1. The document is cut into chunks on page boundaries; each page is marked ``[[PAGE n]]``.
2. Each chunk is sent with a single tool, ``record_extraction``, whose input schema is
   generated from the Pydantic models in ``schema.py``. ``tool_choice`` forces the model
   to answer through that tool, so the reply is structured data, not prose.
3. The reply is validated with Pydantic. On a validation error the model gets one retry
   with the error message; if it still fails, valid items are salvaged one by one and the
   rest are counted in ``warnings`` (nothing is dropped silently).
4. Chunk results are merged and de-duplicated. The pipeline then runs the *grounding
   check*: every quoted ``evidence`` string must appear in the page text, otherwise the item
   is flagged ``grounded=False``.

The client is injectable (anything with ``.messages.create``), which is how the unit tests
exercise this whole path without a network or an API key.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from ..schema import (
    ChunkResult, Clin, ContractTerms, Deliverable, EvaluationFactor, Extraction, KeyDate, MoneyItem, Requirement,
)

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_CHARS = 24_000      # per chunk, about 6,000 tokens of document text
MAX_TOKENS = 8_192      # output budget per chunk
TOOL_NAME = "record_extraction"

SYSTEM_PROMPT = """You extract structured compliance data from a US federal solicitation (RFP, RFQ or contract).
The text is marked with [[PAGE n]] lines. Report only what the text states; never guess or add outside knowledge.

Rules:
- evidence: copy the exact words from the document (a sentence or a short passage). Do not paraphrase, merge or fix typos.
- page: the number from the nearest [[PAGE n]] marker above the evidence.
- requirements: every sentence that imposes an obligation, including prohibitions and conditions written without a
  modal verb (for example "Hazardous materials are prohibited..."). Set party to who must act: contractor, offeror
  (proposal instructions), government (obligations on the Government), or unspecified. Do NOT report statements that
  only describe how the Government will evaluate or decide, background text, or definitions.
- obligation: the modal word actually used (shall, must, will, should) or "required" when none is used.
- category: choose the single best fit from the allowed values.
- key_dates: dated events (issue, questions due, site visit, proposals due, award, start). date must be ISO YYYY-MM-DD
  and only when the full date is written; otherwise leave it empty and put the text in raw.
- amounts: dollar figures with their meaning (ceiling, not-to-exceed, minimum guarantee, threshold, insurance, bond...).
- clins, deliverables (CDRL items), evaluation_factors (with subfactors and the stated relative importance).
- terms: fill a field only if this part of the document states it. contract_type: use short codes such as FFP, T&M, CPFF.
- If this part of the document contains nothing for a list, return it empty. Always answer by calling the tool."""


# ---------------------------------------------------------------------------
# Client and tool definition
# ---------------------------------------------------------------------------
def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env reader (KEY=VALUE lines). Real environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def make_client():
    load_dotenv()
    try:
        import anthropic
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise RuntimeError("LLM mode needs the Anthropic SDK: pip install 'contractiq[llm]'") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key, "
                           "or use the default rules mode, which needs no key.")
    return anthropic.Anthropic()


def _inline_refs(node: Any, defs: dict) -> Any:
    """Replace {"$ref": "#/$defs/X"} with the definition itself; drop noisy keys."""
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline_refs(defs[node["$ref"].split("/")[-1]], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k not in {"$defs", "title"}}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


def tool_definition() -> dict:
    schema = ChunkResult.model_json_schema()
    return {
        "name": TOOL_NAME,
        "description": "Record everything this part of the solicitation states. Call exactly once.",
        "input_schema": _inline_refs(schema, schema.get("$defs", {})),
    }


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------
def chunk_pages(pages: list[str], max_chars: int = MAX_CHARS) -> list[tuple[int, int, str]]:
    """Group whole pages into chunks. Returns (first_page, last_page, text) with [[PAGE n]] markers."""
    chunks, cur, cur_len, first = [], [], 0, 1
    for n, text in enumerate(pages, start=1):
        piece = f"[[PAGE {n}]]\n{text.strip()}\n"
        if cur and cur_len + len(piece) > max_chars:
            chunks.append((first, n - 1, "\n".join(cur)))
            cur, cur_len, first = [], 0, n
        cur.append(piece)
        cur_len += len(piece)
    if cur:
        chunks.append((first, len(pages), "\n".join(cur)))
    return chunks


def estimate(pages: list[str], max_chars: int = MAX_CHARS) -> dict:
    """Rough size of an LLM run without calling anything (about 4 characters per token)."""
    chunks = chunk_pages(pages, max_chars)
    chars = sum(len(c[2]) for c in chunks) + len(SYSTEM_PROMPT) * len(chunks)
    return {"calls": len(chunks), "approx_input_tokens": chars // 4}


# ---------------------------------------------------------------------------
# One chunk
# ---------------------------------------------------------------------------
def _tool_use(response) -> Any | None:
    for block in getattr(response, "content", None) or []:
        kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if kind == "tool_use":
            return block
    return None


def _get(block, key):
    return block.get(key) if isinstance(block, dict) else getattr(block, key)


_LISTS = {"requirements": "RequirementIn", "key_dates": "KeyDateIn", "amounts": "MoneyItemIn", "clins": "ClinIn",
          "deliverables": "DeliverableIn", "evaluation_factors": "EvaluationFactorIn"}


def _salvage(raw: dict) -> tuple[ChunkResult, int]:
    """Keep every list item that validates on its own. Returns (result, number dropped)."""
    from .. import schema

    dropped, kept = 0, {}
    if not isinstance(raw, dict):
        return ChunkResult(), 1
    try:
        kept["terms"] = schema.TermsIn.model_validate(raw.get("terms") or {})
    except ValidationError:
        dropped += 1
    for field, model_name in _LISTS.items():
        model = getattr(schema, model_name)
        items = raw.get(field)
        good = []
        for item in items if isinstance(items, list) else []:
            try:
                good.append(model.model_validate(item))
            except ValidationError:
                dropped += 1
        kept[field] = good
    return ChunkResult(**kept), dropped


def _call_chunk(client, model: str, text: str, warnings: list[str], label: str) -> ChunkResult:
    tool = tool_definition()
    messages: list[dict] = [{"role": "user", "content": text}]
    result: ChunkResult | None = None
    raw: Any = {}
    for attempt in (1, 2):
        resp = client.messages.create(
            model=model, max_tokens=MAX_TOKENS, system=SYSTEM_PROMPT, tools=[tool],
            tool_choice={"type": "tool", "name": TOOL_NAME}, messages=messages)
        if getattr(resp, "stop_reason", None) == "max_tokens":
            warnings.append(f"{label}: the model ran out of output space; some items may be missing. "
                            "Re-run with a smaller chunk size.")
        block = _tool_use(resp)
        if block is None:
            warnings.append(f"{label}: the model did not call the extraction tool; nothing was recorded.")
            return ChunkResult()
        raw = _get(block, "input")
        try:
            return ChunkResult.model_validate(raw)
        except ValidationError as err:
            if attempt == 2:
                break
            messages.append({"role": "assistant", "content": [
                {"type": "tool_use", "id": _get(block, "id"), "name": TOOL_NAME, "input": raw}]})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": _get(block, "id"), "is_error": True,
                 "content": f"Validation failed. Fix these problems and call the tool again:\n{str(err)[:1500]}"}]})
    result, dropped = _salvage(raw)
    warnings.append(f"{label}: {dropped} item(s) failed validation twice and were dropped.")
    return result


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
def _key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _iso_or_empty(s: str) -> str:
    try:
        return date.fromisoformat(s).isoformat() if s else ""
    except ValueError:
        return ""


def _merge(results: list[ChunkResult]) -> Extraction:
    ex = Extraction()
    terms = ContractTerms()
    seen_req: set[str] = set()
    seen_date: set[tuple] = set()
    seen_amt: set[tuple] = set()
    clins: dict[str, Clin] = {}
    cdrls: dict[str, Deliverable] = {}
    factors: dict[str, EvaluationFactor] = {}

    for res in results:
        for field in type(res.terms).model_fields:
            if not getattr(terms, field) and getattr(res.terms, field):
                setattr(terms, field, getattr(res.terms, field).strip())
        for r in res.requirements:
            k = _key(r.text)
            if k in seen_req:
                continue
            seen_req.add(k)
            ex.requirements.append(Requirement(
                text=r.text.strip(), evidence=r.evidence.strip(), page=r.page, obligation=r.obligation,
                party=r.party, mandatory=r.obligation != "should", category=r.category, section=r.section,
                source="llm"))
        for d in res.key_dates:
            iso = _iso_or_empty(d.date)
            k = (d.label.lower(), iso or d.raw.lower())
            if k not in seen_date:
                seen_date.add(k)
                ex.key_dates.append(KeyDate(label=d.label, date=iso, time=d.time, raw=d.raw,
                                            evidence=d.evidence, page=d.page))
        for a in res.amounts:
            k = (a.amount, a.label.lower())
            if k not in seen_amt:
                seen_amt.add(k)
                terms.amounts.append(MoneyItem(label=a.label, amount=a.amount, raw=a.raw, evidence=a.evidence, page=a.page))
        for c in res.clins:
            clins.setdefault(c.number.strip(), Clin(number=c.number.strip(), description=c.description, type=c.type,
                                                    evidence=c.evidence, page=c.page))
        for d in res.deliverables:
            cdrls.setdefault(d.id.strip().upper(), Deliverable(id=d.id.strip().upper(), title=d.title,
                                                               frequency=d.frequency, due=d.due,
                                                               evidence=d.evidence, page=d.page))
        for f in res.evaluation_factors:
            cur = factors.get(_key(f.name))
            if cur is None:
                factors[_key(f.name)] = EvaluationFactor(name=f.name.strip(), importance=f.importance,
                                                         subfactors=list(dict.fromkeys(f.subfactors)),
                                                         evidence=f.evidence, page=f.page)
            else:
                cur.importance = cur.importance or f.importance
                cur.subfactors = list(dict.fromkeys([*cur.subfactors, *f.subfactors]))
    ex.terms = terms
    ex.clins = list(clins.values())
    ex.deliverables = list(cdrls.values())
    ex.evaluation_factors = list(factors.values())
    return ex


# ---------------------------------------------------------------------------
def extract(pages: list[str], *, client=None, model: str | None = None, progress=None,
            max_chars: int = MAX_CHARS) -> tuple[Extraction, str]:
    model = model or os.environ.get("CONTRACTIQ_MODEL") or DEFAULT_MODEL
    client = client or make_client()
    chunks = chunk_pages(pages, max_chars)
    results: list[ChunkResult] = []
    warnings: list[str] = []
    errors: list[str] = []
    for i, (first, last, text) in enumerate(chunks, start=1):
        label = f"pages {first}-{last}" if first != last else f"page {first}"
        if progress:
            progress(i, len(chunks))
        try:
            results.append(_call_chunk(client, model, text, warnings, label))
        except Exception as e:  # network, auth, rate limit after SDK retries
            errors.append(f"{label}: {type(e).__name__}: {str(e)[:200]}")
    if errors and not results:
        raise RuntimeError("Every request failed. First error: " + errors[0])
    ex = _merge(results)
    ex.warnings.extend(warnings)
    ex.warnings.extend(f"Request failed, so this part is missing. {e}" for e in errors)
    return ex, model


def dump_schema() -> str:  # handy for docs and debugging
    return json.dumps(tool_definition(), indent=2)
