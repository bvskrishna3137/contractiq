#!/usr/bin/env python3
"""Build the FICTIONAL sample solicitation and its hand-written answer key.

Everything in the sample (agency, numbers, dates, text) is invented for this
project. It is *not* a real solicitation. Each page carries a banner saying so.

The document and the answer key come from the same structured source below, so
they cannot drift apart. Page numbers in the answer key are read back from the
finished PDF, and the script fails if any quoted evidence is not found there.

    python tools/make_sample_rfp.py

writes samples/fictional_rfp.pdf and samples/gold.json (deterministic output).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pdfplumber  # noqa: E402
from reportlab.lib.enums import TA_LEFT  # noqa: E402
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.lib.units import inch  # noqa: E402
from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer  # noqa: E402

from contractiq.schema import (  # noqa: E402
    Clin, ContractTerms, Deliverable, EvaluationFactor, Extraction, KeyDate, MoneyItem, Requirement,
)

SOL = "FX-SAMPLE-26-R-0042"
BANNER = "FICTIONAL SAMPLE DOCUMENT - invented for the ContractIQ demo. Not a real solicitation."


@dataclass
class R:
    """A requirement sentence together with its answer-key labels."""
    text: str
    cat: str
    party: str = "contractor"
    obl: str = "shall"
    mand: bool = True


# ---------------------------------------------------------------------------
# Document source. ("kind", ...) blocks, rendered in order.
# ---------------------------------------------------------------------------
DOC: list[tuple] = [
    ("title", "REQUEST FOR PROPOSALS"),
    ("subtitle", "Integrated Facilities Maintenance Services"),
    ("line", f"Solicitation Number: {SOL}"),
    ("line", "Title: Integrated Facilities Maintenance Services, Riverbend Campus"),
    ("line", "Issuing Agency: Example Federal Agency, Office of Facilities"),
    ("line", "NAICS Code: 561210 (Facilities Support Services)"),
    ("line", "Set-Aside: Total Small Business Set-Aside"),
    ("line", "Period of Performance: One 12-month base period and four 12-month option periods"),
    ("line", "Place of Performance: Riverbend Campus, Example City, TX"),
    ("h2", "Key Dates"),
    ("line", "Issue date: December 1, 2026"),
    ("line", "Pre-proposal site visit: December 9, 2026, 10:00 AM CT"),
    ("line", "Questions due: December 15, 2026, 4:00 PM CT"),
    ("line", "Proposals due: January 22, 2027, 2:00 PM CT"),
    ("line", "Anticipated award: March 1, 2027"),
    ("note", "This sample is entirely fictional. The agency, place, numbers and dates were invented to "
             "exercise the extractor and do not describe any real procurement."),
    ("pb",),

    ("h1", "SECTION B - SUPPLIES OR SERVICES AND PRICES"),
    ("para", "B.1", ["Contract type. This is a hybrid contract. CLINs 0001, 0002, 0004 and 0005 are "
                     "Firm-Fixed-Price (FFP). CLIN 0003 is Time-and-Materials (T&M)."]),
    ("para", "B.2", ["Contract line items (CLINs) are listed below."]),
    ("line", "CLIN 0001 - Base facility maintenance services (monthly) - Type: FFP"),
    ("line", "CLIN 0002 - Grounds and custodial services (monthly) - Type: FFP"),
    ("line", "CLIN 0003 - Unscheduled repairs and emergency response - Type: T&M"),
    ("line", "CLIN 0004 - Transition-in services (one time) - Type: FFP"),
    ("line", "CLIN 0005 - Data items (CDRLs) - Type: NSP"),
    ("para", "B.3", ["The ceiling for CLIN 0003 is $250,000 per period of performance (not-to-exceed). "
                     "The Government guarantees a minimum of $50,000 in orders under CLIN 0003 during the base period."]),
    ("para", "B.4", [R("Offerors shall propose a fixed monthly price for CLINs 0001 and 0002 and fully burdened "
                       "hourly labor rates for CLIN 0003.", "cost_price", "offeror")]),
    ("pb",),

    ("h1", "SECTION C - STATEMENT OF WORK"),
    ("h2", "C.1 Scope"),
    ("para", "C.1", [R("The Contractor shall provide all labor, supervision, materials and equipment necessary to "
                       "perform facilities maintenance at the Riverbend Campus, comprising 14 buildings and "
                       "approximately 620,000 square feet.", "technical")]),
    ("h2", "C.2 General requirements"),
    ("para", "C.2.1", [R("The Contractor shall provide a full-time on-site Program Manager who is authorized to make "
                         "binding decisions on behalf of the Contractor.", "management")]),
    ("para", "C.2.2", [R("The Program Manager must be available by telephone 24 hours a day, 7 days a week.",
                         "management", "contractor", "must")]),
    ("para", "C.2.3", [R("The Contractor shall maintain a Quality Control Plan (QCP) and shall submit it to the "
                         "Contracting Officer within 30 days after award.", "management")]),
    ("para", "C.2.4", [R("The Contractor shall inspect each building monthly.", "technical"), " ",
                       R("The Contractor shall record all findings in the Computerized Maintenance Management "
                         "System (CMMS).", "technical")]),
    ("h2", "C.3 Maintenance services"),
    ("para", "C.3.1", [R("The Contractor shall perform preventive maintenance on HVAC, electrical, plumbing and "
                         "fire-protection systems in accordance with manufacturer recommendations and the approved "
                         "Preventive Maintenance Schedule (CDRL A003).", "technical")]),
    ("para", "C.3.2", [R("The Contractor shall respond to emergency service calls within 1 hour of notification "
                         "and shall restore critical systems within 4 hours.", "technical")]),
    ("para", "C.3.3", [R("Routine service calls shall be completed within 3 business days.", "technical")]),
    ("para", "C.3.4", [R("Emergency calls will be answered by a live dispatcher at all hours.", "technical",
                         "contractor", "will")]),
    ("para", "C.3.5", [R("The Government shall provide office space, utilities and access to the CMMS for the "
                         "Contractor's on-site staff.", "other", "government")]),
    ("para", "C.3.6", ["Nothing in this section shall be construed to require the Contractor to perform capital "
                       "construction or renovation."]),
    ("h2", "C.4 Grounds and custodial services"),
    ("para", "C.4.1", [R("The Contractor shall: (a) mow and edge all lawns at least weekly during the growing season; "
                         "(b) clear snow and ice from walkways and parking areas within 6 hours of the end of a "
                         "weather event; and (c) empty trash receptacles daily.", "technical")]),
    ("para", "C.4.2", [R("Custodial supplies must be environmentally preferable products in accordance with EPA "
                         "guidelines.", "technical", "contractor", "must")]),
    ("para", "C.4.3", [R("Hazardous materials are prohibited on site without prior written approval from the "
                         "Contracting Officer.", "technical")]),
    ("para", "C.4.4", [R("The Contractor shall obtain written approval from the Contracting Officer's "
                         "Representative (COR) before beginning any single repair expected to exceed $5,000.",
                         "cost_price")]),
    ("h2", "C.5 Reporting"),
    ("para", "C.5.1", [R("The Contractor shall submit the Monthly Status Report (CDRL A001) by the fifth business "
                         "day of each month.", "deliverable")]),
    ("para", "C.5.2", [R("The Contractor shall report any injury, property damage or safety incident to the COR "
                         "within 24 hours using the Incident Report (CDRL A004).", "deliverable")]),
    ("para", "C.5.3", [R("The Contractor should also provide an Annual Energy Report (CDRL A006) within 30 days "
                         "after the end of each period of performance.", "deliverable", "contractor", "should",
                         False)]),
    ("pb",),

    ("h1", "SECTION F - DELIVERIES OR PERFORMANCE"),
    ("para", "F.1", ["The period of performance begins on 04/01/2027 and consists of one 12-month base period "
                     "and four 12-month option periods."]),
    ("para", "F.2", [R("The Contractor shall submit the Transition Plan (CDRL A005) within 10 days after award.",
                       "deliverable")]),
    ("para", "F.3", [R("Deliverables shall be submitted electronically in Microsoft Office or Adobe PDF format.",
                       "deliverable")]),
    ("h2", "F.4 Contract Data Requirements List (CDRL)"),
    ("line", "ID | Title | Frequency | Due"),
    ("line", "A001 | Monthly Status Report | Monthly | 5th business day of each month"),
    ("line", "A002 | Quality Control Plan | Once | 30 days after award"),
    ("line", "A003 | Preventive Maintenance Schedule | Annually | 15 days before each period"),
    ("line", "A004 | Incident Report | As required | Within 24 hours of the incident"),
    ("line", "A005 | Transition Plan | Once | 10 days after award"),
    ("line", "A006 | Annual Energy Report | Annually | 30 days after each period"),
    ("pb",),

    ("h1", "SECTION H - SPECIAL CONTRACT REQUIREMENTS"),
    ("para", "H.1", [R("All Contractor personnel shall undergo a background check before being granted unescorted "
                       "access to the Riverbend Campus.", "security")]),
    ("para", "H.2", [R("Contractor personnel must be U.S. citizens or lawful permanent residents.", "security",
                       "contractor", "must")]),
    ("para", "H.3", [R("Each employee must wear a Government-issued identification badge at all times while on "
                       "the campus.", "security", "contractor", "must")]),
    ("para", "H.4", [R("A satisfactory background check is a condition of site access for every employee.",
                       "security", "contractor", "required")]),
    ("para", "H.5", [R("The Contractor shall maintain general liability insurance of at least $2.5 million per "
                       "occurrence.", "legal_clause")]),
    ("para", "H.6", [R("The Contractor shall furnish a performance bond of $1,000,000 within 15 days after award.",
                       "legal_clause")]),
    ("para", "H.7", [R("The Contractor shall comply with the Service Contract Labor Standards (FAR 52.222-41) and "
                       "the wage determination attached to this solicitation.", "legal_clause")]),
    ("pb",),

    ("h1", "SECTION L - INSTRUCTIONS TO OFFERORS"),
    ("para", "L.1", [R("Proposals shall be received no later than 2:00 PM Central Time on January 22, 2027.",
                       "proposal_instruction", "offeror")]),
    ("para", "L.2", [R("Offerors must submit proposals electronically through the Example Agency Proposal Portal.",
                       "proposal_instruction", "offeror", "must"), " Late proposals will not be considered."]),
    ("para", "L.3", [R("Offerors are required to submit proposals in four separate volumes: Volume I, Technical "
                       "Approach; Volume II, Management and Staffing Plan; Volume III, Past Performance; and "
                       "Volume IV, Price.", "proposal_instruction", "offeror", "required")]),
    ("para", "L.4", [R("Volume I shall not exceed 25 pages, excluding resumes and cover pages.",
                       "proposal_instruction", "offeror")]),
    ("para", "L.5", [R("Offerors shall provide at least three past performance references for contracts of similar "
                       "size and scope completed within the last five years.", "past_performance", "offeror")]),
    ("para", "L.6", [R("Questions about this solicitation must be submitted in writing by December 15, 2026, "
                       "4:00 PM CT.", "proposal_instruction", "offeror", "must")]),
    ("para", "L.7", ["A pre-proposal site visit will be held on December 9, 2026 at 10:00 AM CT. Attendance is "
                     "strongly encouraged but not mandatory."]),
    ("pb",),

    ("h1", "SECTION M - EVALUATION FACTORS FOR AWARD"),
    ("para", "M.1", ["Award will be made on a best-value basis using the tradeoff process. Proposals will be "
                     "evaluated on the following factors:"]),
    ("line", "Factor 1 – Technical Approach"),
    ("line", "Subfactor 1.1 – Preventive Maintenance Approach"),
    ("line", "Subfactor 1.2 – Emergency Response and Continuity"),
    ("line", "Factor 2 – Management and Staffing Plan"),
    ("line", "Subfactor 2.1 – Program Manager Qualifications"),
    ("line", "Subfactor 2.2 – Transition-In Plan"),
    ("line", "Factor 3 – Past Performance"),
    ("line", "Factor 4 – Price"),
    ("para", "M.2", ["Factor 1 is significantly more important than Factor 2. Factor 2 is more important than "
                     "Factor 3. Factors 1, 2 and 3, when combined, are significantly more important than "
                     "Factor 4 (Price)."]),
    ("para", "M.3", [R("Offerors must receive an acceptable rating on Factor 1 to be eligible for award.", "other",
                       "offeror", "must")]),
    ("para", "M.4", ["Past performance will be evaluated based on the references provided by the Offeror and other "
                     "information available to the Government."]),
]

# ---------------------------------------------------------------------------
# Answer key items that are not requirement sentences. `evidence` must appear
# verbatim in the PDF (checked when the key is built).
# ---------------------------------------------------------------------------
TERMS = ContractTerms(
    solicitation_number=SOL,
    title="Integrated Facilities Maintenance Services, Riverbend Campus",
    agency="Example Federal Agency, Office of Facilities",
    contract_type="FFP; T&M",
    naics="561210",
    set_aside="Total Small Business Set-Aside",
    period_of_performance="One 12-month base period and four 12-month option periods",
    place_of_performance="Riverbend Campus, Example City, TX",
)

# (label, iso date, time, raw date, evidence)
KEY_DATES = [
    ("Issue date", "2026-12-01", "", "December 1, 2026", "Issue date: December 1, 2026"),
    ("Site visit", "2026-12-09", "10:00 AM CT", "December 9, 2026", "Pre-proposal site visit: December 9, 2026, 10:00 AM CT"),
    ("Questions due", "2026-12-15", "4:00 PM CT", "December 15, 2026", "Questions due: December 15, 2026, 4:00 PM CT"),
    ("Proposals due", "2027-01-22", "2:00 PM CT", "January 22, 2027", "Proposals due: January 22, 2027, 2:00 PM CT"),
    ("Anticipated award", "2027-03-01", "", "March 1, 2027", "Anticipated award: March 1, 2027"),
    ("Contract start", "2027-04-01", "", "04/01/2027", "begins on 04/01/2027"),
]

# (label, amount, raw, evidence)
AMOUNTS = [
    ("ceiling", 250000, "$250,000", "The ceiling for CLIN 0003 is $250,000 per period of performance (not-to-exceed)."),
    ("minimum guarantee", 50000, "$50,000", "guarantees a minimum of $50,000 in orders under CLIN 0003"),
    ("approval threshold", 5000, "$5,000", "any single repair expected to exceed $5,000"),
    ("insurance", 2500000, "$2.5 million", "general liability insurance of at least $2.5 million per occurrence"),
    ("bond", 1000000, "$1,000,000", "performance bond of $1,000,000"),
]

CLINS = [
    ("0001", "Base facility maintenance services (monthly)", "FFP"),
    ("0002", "Grounds and custodial services (monthly)", "FFP"),
    ("0003", "Unscheduled repairs and emergency response", "T&M"),
    ("0004", "Transition-in services (one time)", "FFP"),
    ("0005", "Data items (CDRLs)", "NSP"),
]

CDRLS = [
    ("A001", "Monthly Status Report", "Monthly", "5th business day of each month"),
    ("A002", "Quality Control Plan", "Once", "30 days after award"),
    ("A003", "Preventive Maintenance Schedule", "Annually", "15 days before each period"),
    ("A004", "Incident Report", "As required", "Within 24 hours of the incident"),
    ("A005", "Transition Plan", "Once", "10 days after award"),
    ("A006", "Annual Energy Report", "Annually", "30 days after each period"),
]

FACTORS = [
    ("Technical Approach", "significantly more important than Factor 2",
     ["Preventive Maintenance Approach", "Emergency Response and Continuity"], "Factor 1 – Technical Approach"),
    ("Management and Staffing Plan", "more important than Factor 3",
     ["Program Manager Qualifications", "Transition-In Plan"], "Factor 2 – Management and Staffing Plan"),
    ("Past Performance", "", [], "Factor 3 – Past Performance"),
    ("Price", "", [], "Factor 4 – Price"),
]


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------
def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_pdf(path: Path) -> None:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=7)
    styles = {
        "title": ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=26, leading=30, spaceBefore=40, spaceAfter=6),
        "subtitle": ParagraphStyle("s", parent=base, fontSize=15, leading=19, spaceAfter=24),
        "h1": ParagraphStyle("h1", parent=base, fontName="Helvetica-Bold", fontSize=13, leading=17, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base, fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=8, spaceAfter=5),
        "line": ParagraphStyle("l", parent=base, spaceAfter=3),
        "note": ParagraphStyle("n", parent=base, fontName="Helvetica-Oblique", fontSize=9, textColor="#555555", spaceBefore=24),
        "para": base,
    }
    story = []
    for blk in DOC:
        kind = blk[0]
        if kind == "pb":
            story.append(PageBreak())
        elif kind == "para":
            text = blk[1] + " " + "".join(p.text if isinstance(p, R) else p for p in blk[2])
            story.append(KeepTogether([Paragraph(_esc(text), styles["para"])]))
        else:
            story.append(Paragraph(_esc(blk[1]), styles[kind]))
    story.append(Spacer(1, 1))

    def decorate(canv, doc):
        canv.saveState()
        canv.setFont("Helvetica-Oblique", 8)
        canv.setFillColorRGB(0.65, 0.1, 0.1)
        canv.drawString(inch, letter[1] - 0.55 * inch, BANNER)
        canv.setFillColorRGB(0.35, 0.35, 0.35)
        canv.setFont("Helvetica", 8)
        canv.drawString(inch, 0.55 * inch, f"{SOL}")
        canv.drawRightString(letter[0] - inch, 0.55 * inch, f"Page {doc.page}")
        canv.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=letter, leftMargin=inch, rightMargin=inch, topMargin=0.95 * inch,
                            bottomMargin=0.9 * inch, title="Fictional sample RFP (ContractIQ demo)",
                            author="ContractIQ sample generator", invariant=1)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)


# ---------------------------------------------------------------------------
# Answer key
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    return " ".join(s.split())


def build_gold(pdf: Path) -> Extraction:
    with pdfplumber.open(pdf) as p:
        pages = [_norm(pg.extract_text() or "") for pg in p.pages]

    def page_of(quote: str) -> int:
        q = _norm(quote)
        hits = [i + 1 for i, t in enumerate(pages) if q in t]
        if not hits:
            raise SystemExit(f"Evidence not found in PDF: {quote!r}")
        return hits[0]

    reqs: list[Requirement] = []
    for blk in DOC:
        if blk[0] != "para":
            continue
        for part in blk[2]:
            if isinstance(part, R):
                reqs.append(Requirement(
                    id=f"R-{len(reqs) + 1:03d}", text=part.text, evidence=part.text, page=page_of(part.text),
                    obligation=part.obl, party=part.party, mandatory=part.mand, category=part.cat,
                    section=blk[1], source="rules"))

    ex = Extraction(
        terms=TERMS.model_copy(update={"amounts": [
            MoneyItem(label=l, amount=a, raw=r, evidence=e, page=page_of(e)) for l, a, r, e in AMOUNTS]}),
        key_dates=[KeyDate(label=l, date=d, time=t, raw=r, evidence=e, page=page_of(e)) for l, d, t, r, e in KEY_DATES],
        requirements=reqs,
        evaluation_factors=[EvaluationFactor(name=n, importance=imp, subfactors=subs, evidence=ev, page=page_of(ev))
                            for n, imp, subs, ev in FACTORS],
        deliverables=[Deliverable(id=i, title=t, frequency=f, due=d, evidence=f"{i} | {t} | {f} | {d}",
                                  page=page_of(f"{i} | {t} | {f} | {d}")) for i, t, f, d in CDRLS],
        clins=[Clin(number=n, description=d, type=t, evidence=f"CLIN {n} - {d} - Type: {t}",
                    page=page_of(f"CLIN {n} - {d} - Type: {t}")) for n, d, t in CLINS],
    )
    ex.metadata.source_file = "fictional_rfp.pdf"
    ex.metadata.page_count = len(pages)
    return ex


def main() -> None:
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    pdf = out / "fictional_rfp.pdf"
    build_pdf(pdf)
    gold = build_gold(pdf)
    data = gold.model_dump(exclude={"metadata": {"generated_at"}})
    (out / "gold.json").write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {pdf.relative_to(ROOT)} ({gold.metadata.page_count} pages) and samples/gold.json")
    print(gold.stats())


if __name__ == "__main__":
    main()
