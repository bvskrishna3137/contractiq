"""Rule-based extractor: regular expressions and a few document-structure heuristics.

Runs offline with no API key. It is the default mode and the baseline that LLM
mode is measured against. It is deliberately simple and *honest about its limits*:
it finds sentences that use "shall / must / will / should / required to", labelled
cover-page fields, dated lines, dollar amounts, CLIN and CDRL rows, and "Factor N"
lists. It misses requirements written without a modal verb and can mis-file
categories; those are the cases an LLM helps with.
"""
from __future__ import annotations

import re
from datetime import date

from ..pdf import Block, to_blocks
from ..schema import (
    Clin, ContractTerms, Deliverable, EvaluationFactor, Extraction, KeyDate, MoneyItem, Requirement,
)

# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[a-z0-9)\"]\.)\s+(?=[A-Z(])")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]


_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE_PATTERNS = [
    (re.compile(rf"\b{_MON}\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(\d{{4}})\b"), "mdy"),
    (re.compile(rf"\b(\d{{1,2}})\s+{_MON}\.?,?\s+(\d{{4}})\b"), "dmy"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "num"),
]
_TIME = re.compile(
    r"\b\d{1,2}(?::\d{2})?\s*[AaPp]\.?[Mm]\.?(?:\s*(?:Central|Eastern|Pacific|Mountain)(?:\s+(?:Standard\s+|Daylight\s+)?Time)?"
    r"|\s*[A-Z]{1,2}T\b)?")


def find_dates(sentence: str) -> list[tuple[str, str]]:
    """Return (iso_date, raw_text) for each parseable date in the sentence."""
    out = []
    for rx, kind in _DATE_PATTERNS:
        for m in rx.finditer(sentence):
            try:
                if kind == "mdy":
                    mo, d, y = _MONTHS[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))
                elif kind == "dmy":
                    d, mo, y = int(m.group(1)), _MONTHS[m.group(2)[:3].lower()], int(m.group(3))
                else:
                    mo, d, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                out.append((date(y, mo, d).isoformat(), m.group(0)))
            except (ValueError, KeyError):
                continue
    return out


# label keyword -> label. Order matters: "pre-proposal site visit" must win over "proposal".
_DATE_LABELS = [
    (re.compile(r"\bquestions?\b|\binquiries\b", re.I), "Questions due"),
    (re.compile(r"site visit|pre-?proposal conference|industry day|bidders? conference", re.I), "Site visit"),
    (re.compile(r"\bproposals?\b|\boffers?\b|\bquotations?\b|\bresponses?\b|\bbids?\b", re.I), "Proposals due"),
    (re.compile(r"\baward", re.I), "Anticipated award"),
    (re.compile(r"\bissue|\bposted\b|\breleased?\b", re.I), "Issue date"),
    (re.compile(r"\bbegin|\bstart|\bcommenc|\beffective\b", re.I), "Contract start"),
]

_CONTRACT_TYPES = [
    ("FFP", r"firm[- ]fixed[- ]price|\bFFP\b"),
    ("FPIF", r"fixed[- ]price[- ]incentive|\bFPIF\b"),
    ("T&M", r"time[- ]and[- ]materials?|\bT&M\b"),
    ("LH", r"labor[- ]hour\b"),
    ("CPFF", r"cost[- ]plus[- ]fixed[- ]fee|\bCPFF\b"),
    ("CPAF", r"cost[- ]plus[- ]award[- ]fee|\bCPAF\b"),
    ("CPIF", r"cost[- ]plus[- ]incentive[- ]fee|\bCPIF\b"),
    ("IDIQ", r"indefinite[- ]delivery|\bIDIQ\b"),
    ("BPA", r"blanket purchase agreement|\bBPA\b"),
]

_LABELLED_TERMS = {
    "solicitation_number": re.compile(r"(?:Solicitation|RFP|RFQ|IFB)\s*(?:Number|No\.?|#)\s*[:\-]\s*(.+)", re.I),
    "title": re.compile(r"(?:Project\s+)?Title\s*:\s*(.+)", re.I),
    "agency": re.compile(r"(?:Issuing\s+(?:Agency|Office)|Agency|Issued\s+by|Contracting\s+Office)\s*:\s*(.+)", re.I),
    "naics": re.compile(r"NAICS(?:\s+Code)?\s*[:\-]\s*(\d{6})", re.I),
    "set_aside": re.compile(r"Set[- ]Aside\s*:\s*(.+)", re.I),
    "period_of_performance": re.compile(r"Period\s+of\s+Performance\s*:\s*(.+)", re.I),
    "place_of_performance": re.compile(r"Place\s+of\s+Performance\s*:\s*(.+)", re.I),
}
_SOL_NUMBER = re.compile(r"\b(?:[A-Z0-9]{2,}-\d{2}-[A-Z]-\d{3,5}|[A-Z0-9]{6}\d{2}[A-Z]\d{4})\b")

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)(?:\s*(million|billion|thousand|[MBK])\b)?", re.I)
_MULT = {"million": 1e6, "m": 1e6, "billion": 1e9, "b": 1e9, "thousand": 1e3, "k": 1e3}
_MONEY_LABELS = [
    (re.compile(r"minimum", re.I), "minimum guarantee"),
    (re.compile(r"ceiling", re.I), "ceiling"),
    (re.compile(r"not[- ]to[- ]exceed|\bNTE\b", re.I), "not-to-exceed"),
    (re.compile(r"insurance", re.I), "insurance"),
    (re.compile(r"\bbond\b", re.I), "bond"),
    (re.compile(r"exceed|threshold|in excess|approval", re.I), "approval threshold"),
]

# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------
_MODAL = re.compile(r"\b(shall|must|will|should)\b|\b(?:is|are)\s+required\s+to\b|\brequired\s+to\b", re.I)
_STRONG_PARTY = [
    ("government", re.compile(r"\bGovernment\b", re.I)),
    ("offeror", re.compile(r"\bOfferors?\b|\bBidders?\b|\bQuoters?\b", re.I)),
    ("contractor", re.compile(r"\bContractors?\b|\bVendors?\b|\bAwardee\b|\bSubcontractors?\b", re.I)),
]
_WEAK_PARTY = [
    ("government", re.compile(r"\bContracting Officer\b|\bCOR\b|\bAgency\b", re.I)),
    ("offeror", re.compile(r"\bProposals?\b|\bVolume\b|\bQuotes?\b", re.I)),
    ("contractor", re.compile(r"\bProgram Manager\b|\bpersonnel\b|\bemployees?\b|\bstaff\b", re.I)),
]
_DEFAULT_PARTY = {"B": "contractor", "C": "contractor", "F": "contractor", "H": "contractor",
                  "L": "offeror", "M": "offeror"}
_DEFAULT_CATEGORY = {"B": "cost_price", "C": "technical", "F": "schedule", "I": "legal_clause",
                     "L": "proposal_instruction"}

_CATEGORY_RULES = [
    ("legal_clause", re.compile(r"\binsurance\b|\bbond\b|\bFAR\b|\bDFARS\b|indemn|liabilit|\bclause\b")),
    ("security", re.compile(r"background|badge|citizen|clearance|security|identification|\bCUI\b", re.I)),
    ("past_performance", re.compile(r"past performance|\breferences?\b", re.I)),
    ("management", re.compile(r"program manager|key personnel|staffing plan", re.I)),
    ("deliverable", re.compile(r"\bCDRL\b.*\b(?:submit|provide|deliver|report)|\b(?:submit|provide|deliver|report)\b.*\bCDRL\b"
                               r"|\bdeliverables?\b", re.I)),
    ("cost_price", re.compile(r"\$\s?\d|\bprice\b|\bpricing\b|\binvoic|\bhourly\b|\blabor rates?\b", re.I)),
]


def _party(prefix: str, letter: str, strong_only: bool) -> tuple[str, bool]:
    """Return (party, explicit). `explicit` is False when it was guessed from the section letter."""
    best: tuple[int, str] | None = None
    for group in (_STRONG_PARTY, _STRONG_PARTY + _WEAK_PARTY):
        for name, rx in group:
            m = rx.search(prefix)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), name)
        if best or strong_only:
            break
    if best:
        return best[1], True
    return _DEFAULT_PARTY.get(letter, "unspecified"), False


def _category(sentence: str, letter: str) -> str:
    for cat, rx in _CATEGORY_RULES:
        if rx.search(sentence):
            return cat
    return _DEFAULT_CATEGORY.get(letter, "other")


def _requirements(blocks: list[Block]) -> list[Requirement]:
    out, seen = [], set()
    for b in blocks:
        if b.kind in {"clin", "factor", "subfactor", "cdrl", "section"}:
            continue
        text = b.text[len(b.ref):].strip() if b.ref else b.text
        for sent in split_sentences(text):
            m = _MODAL.search(sent)
            if not m or len(sent) < 12:
                continue
            word = (m.group(1) or "required").lower()
            prefix = sent[: m.start()]
            party, explicit = _party(prefix, b.letter, strong_only=(word == "will"))
            if word == "will" and not explicit:
                continue  # "Proposals will be evaluated..." describes the Government, not a duty
            if sent in seen:
                continue
            seen.add(sent)
            out.append(Requirement(
                text=sent, evidence=sent, page=b.page, obligation=word, party=party,
                mandatory=word != "should", category=_category(sent, b.letter), section=b.ref, source="rules"))
    return out


# ---------------------------------------------------------------------------
# Other fields
# ---------------------------------------------------------------------------
def _terms(blocks: list[Block], full_text: str) -> ContractTerms:
    t = ContractTerms()
    for b in blocks:
        for field, rx in _LABELLED_TERMS.items():
            if getattr(t, field):
                continue
            m = rx.match(b.text)
            if m:
                setattr(t, field, m.group(1).strip().rstrip("."))
    if not t.solicitation_number:
        m = _SOL_NUMBER.search(full_text[:4000])
        if m:
            t.solicitation_number = m.group(0)
    if not t.naics:
        m = re.search(r"NAICS[^0-9]{0,40}(\d{6})", full_text, re.I)
        if m:
            t.naics = m.group(1)
    found = [code for code, pat in _CONTRACT_TYPES if re.search(pat, full_text, re.I)]
    t.contract_type = "; ".join(found)
    return t


def _key_dates(blocks: list[Block]) -> tuple[list[KeyDate], int]:
    out, seen, skipped = [], set(), 0
    for b in blocks:
        for sent in split_sentences(b.text):
            for iso, raw in find_dates(sent):
                label = next((name for rx, name in _DATE_LABELS if rx.search(sent)), None)
                if not label:
                    skipped += 1
                    continue
                if (label, iso) in seen:
                    continue
                seen.add((label, iso))
                tm = _TIME.search(sent)
                out.append(KeyDate(label=label, date=iso, raw=raw, time=tm.group(0).strip() if tm else "",
                                   evidence=sent, page=b.page))
    return out, skipped


def _amounts(blocks: list[Block]) -> list[MoneyItem]:
    out, seen = [], set()
    for b in blocks:
        for sent in split_sentences(b.text):
            for m in _MONEY.finditer(sent):
                amount = float(m.group(1).replace(",", "")) * _MULT.get((m.group(2) or "").lower(), 1)
                label = next((name for rx, name in _MONEY_LABELS if rx.search(sent)), "amount")
                if (amount, label) in seen:
                    continue
                seen.add((amount, label))
                out.append(MoneyItem(label=label, amount=amount, raw=m.group(0), evidence=sent, page=b.page))
    return out


_CLIN = re.compile(r"^CLIN\s+(\d{4}[A-Z]{0,2})\s*[-–—:]\s*(.+?)(?:\s*[-–—]\s*Type:\s*(.+))?$", re.I)
_CDRL_ROW = re.compile(r"^([A-Z]\d{3}[A-Z]?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(.+)$")
_CDRL_MENTION = re.compile(r"\bCDRL\s+([A-Z]\d{3}[A-Z]?)\b")
_FACTOR = re.compile(r"^Factor\s+(\d+)\s*[-–—:]\s*(.+)$", re.I)
_SUBFACTOR = re.compile(r"^Sub-?factor\s+(\d+)\.\d+\s*[-–—:]\s*(.+)$", re.I)
_IMPORTANCE = re.compile(r"\bFactor\s+(\d+)\s+(?:is|are)\s+(.*?\bimportan(?:t|ce)\b.*?)\s*$", re.I)


def _clins(blocks: list[Block]) -> list[Clin]:
    out, seen = [], set()
    for b in blocks:
        m = _CLIN.match(b.text) if b.kind == "clin" else None
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(Clin(number=m.group(1), description=m.group(2).strip(), type=(m.group(3) or "").strip(),
                            evidence=b.text, page=b.page))
    return out


def _deliverables(blocks: list[Block]) -> list[Deliverable]:
    out, seen = [], set()
    for b in blocks:
        m = _CDRL_ROW.match(b.text) if b.kind == "cdrl" else None
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(Deliverable(id=m.group(1), title=m.group(2), frequency=m.group(3), due=m.group(4),
                                   evidence=b.text, page=b.page))
    for b in blocks:  # ids mentioned in prose but absent from any table
        for sent in split_sentences(b.text):
            for m in _CDRL_MENTION.finditer(sent):
                if m.group(1) not in seen:
                    seen.add(m.group(1))
                    out.append(Deliverable(id=m.group(1), evidence=sent, page=b.page))
    return out


def _factors(blocks: list[Block]) -> list[EvaluationFactor]:
    factors: dict[str, EvaluationFactor] = {}
    for b in blocks:
        m = _FACTOR.match(b.text)
        if m and b.kind == "factor" and m.group(1) not in factors:
            factors[m.group(1)] = EvaluationFactor(name=m.group(2).strip(), evidence=b.text, page=b.page)
    for b in blocks:
        m = _SUBFACTOR.match(b.text)
        if m and m.group(1) in factors:
            factors[m.group(1)].subfactors.append(m.group(2).strip())
    for b in blocks:
        for sent in split_sentences(b.text):
            m = _IMPORTANCE.search(sent)
            if m and m.group(1) in factors and not factors[m.group(1)].importance:
                factors[m.group(1)].importance = m.group(2).strip().rstrip(".")
    return list(factors.values())


# ---------------------------------------------------------------------------
def extract(pages: list[str]) -> Extraction:
    blocks = to_blocks(pages)
    full_text = "\n".join(pages)
    ex = Extraction()
    ex.terms = _terms(blocks, full_text)
    ex.terms.amounts = _amounts(blocks)
    ex.key_dates, skipped = _key_dates(blocks)
    ex.requirements = _requirements(blocks)
    ex.clins = _clins(blocks)
    ex.deliverables = _deliverables(blocks)
    ex.evaluation_factors = _factors(blocks)
    if skipped:
        ex.warnings.append(f"{skipped} date(s) were skipped because no recognisable label (due, award, start...) was nearby.")
    if not ex.requirements:
        ex.warnings.append("No requirement sentences (shall / must / will / should) were found.")
    return ex
