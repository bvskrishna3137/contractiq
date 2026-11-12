"""Write an Extraction as JSON, CSV or an Excel compliance matrix."""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .schema import Extraction

REQ_COLUMNS = ["ID", "Section", "Page", "Category", "Obligation", "Party", "Mandatory", "Requirement",
               "Grounded", "Proposal reference", "Owner", "Status"]


def to_json(ex: Extraction) -> str:
    return ex.model_dump_json(indent=2)


def _req_rows(ex: Extraction) -> list[list]:
    return [[r.id, r.section, r.page, r.category, r.obligation, r.party, "Yes" if r.mandatory else "No", r.text,
             "Yes" if r.grounded else "NO", "", "", "Not started"] for r in ex.requirements]


def requirements_csv(ex: Extraction) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(REQ_COLUMNS)
    w.writerows(_req_rows(ex))
    return buf.getvalue()


def to_xlsx(ex: Extraction, path: str | Path | io.BytesIO) -> None:
    """A workbook a proposal team can work in: the first sheet is a ready-to-fill compliance matrix."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="1F3A5F")
    head_font = Font(bold=True, color="FFFFFF")

    def sheet(title: str, columns: list[str], rows: list[list], widths: list[int], first: bool = False):
        ws = wb.active if first else wb.create_sheet()
        ws.title = title
        ws.append(columns)
        for row in rows:
            ws.append(row)
        for i, wdt in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = wdt
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(vertical="top", wrap_text=True)
        ws.freeze_panes = "A2"
        if rows:
            ws.auto_filter.ref = ws.dimensions
        return ws

    ws = sheet("Compliance matrix", REQ_COLUMNS, _req_rows(ex), [8, 9, 6, 18, 11, 12, 10, 80, 9, 18, 14, 14], first=True)
    if ex.requirements:
        dv = DataValidation(type="list", formula1='"Not started,In progress,Drafted,Reviewed,Done"', allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"L2:L{len(ex.requirements) + 1}")

    t = ex.terms
    summary = [["Solicitation number", t.solicitation_number], ["Title", t.title], ["Agency", t.agency],
               ["Contract type", t.contract_type], ["NAICS", t.naics], ["Set-aside", t.set_aside],
               ["Period of performance", t.period_of_performance], ["Place of performance", t.place_of_performance],
               ["Source file", ex.metadata.source_file], ["Pages", ex.metadata.page_count],
               ["Extraction mode", ex.metadata.mode + (f" ({ex.metadata.model})" if ex.metadata.model else "")],
               ["Generated (UTC)", ex.metadata.generated_at]]
    summary += [[k.replace("_", " ").capitalize(), v] for k, v in ex.stats().items()]
    summary += [["Warning", w] for w in ex.warnings]
    sheet("Summary", ["Field", "Value"], summary, [26, 90])

    sheet("Key dates", ["Label", "Date", "Time", "As written", "Page", "Evidence"],
          [[d.label, d.date, d.time, d.raw, d.page, d.evidence] for d in ex.key_dates], [20, 12, 16, 20, 6, 80])
    sheet("Amounts", ["Label", "Amount (USD)", "As written", "Page", "Evidence"],
          [[a.label, a.amount, a.raw, a.page, a.evidence] for a in t.amounts], [20, 16, 16, 6, 80])
    sheet("Evaluation factors", ["Factor", "Importance", "Subfactors", "Page"],
          [[f.name, f.importance, "; ".join(f.subfactors), f.page] for f in ex.evaluation_factors], [32, 46, 60, 6])
    sheet("Deliverables (CDRL)", ["ID", "Title", "Frequency", "Due", "Page"],
          [[d.id, d.title, d.frequency, d.due, d.page] for d in ex.deliverables], [8, 36, 14, 36, 6])
    sheet("CLINs", ["CLIN", "Description", "Type", "Page"],
          [[c.number, c.description, c.type, c.page] for c in ex.clins], [8, 60, 8, 6])

    if isinstance(path, io.BytesIO):
        wb.save(path)
    else:
        wb.save(str(path))
