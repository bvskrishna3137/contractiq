import csv
import io

from openpyxl import load_workbook

from contractiq.export import REQ_COLUMNS, requirements_csv, to_json, to_xlsx
from contractiq.schema import Extraction


def test_json_round_trips(sample_result):
    assert Extraction.model_validate_json(to_json(sample_result)).stats() == sample_result.stats()


def test_csv_has_one_row_per_requirement(sample_result):
    rows = list(csv.reader(io.StringIO(requirements_csv(sample_result))))
    assert rows[0] == REQ_COLUMNS and len(rows) == len(sample_result.requirements) + 1


def test_xlsx_is_a_usable_compliance_matrix(sample_result, tmp_path):
    path = tmp_path / "m.xlsx"
    to_xlsx(sample_result, path)
    wb = load_workbook(path)
    assert wb.sheetnames[0] == "Compliance matrix" and "CLINs" in wb.sheetnames
    ws = wb["Compliance matrix"]
    assert ws.max_row == len(sample_result.requirements) + 1
    assert ws["L2"].value == "Not started" and ws.freeze_panes == "A2"
    assert ws.data_validations.dataValidation, "status column should be a dropdown"


def test_xlsx_to_memory_and_empty_result():
    buf = io.BytesIO()
    to_xlsx(Extraction(), buf)
    assert load_workbook(io.BytesIO(buf.getvalue())).sheetnames[0] == "Compliance matrix"
