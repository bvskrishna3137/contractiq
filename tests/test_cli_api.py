import json

import pytest
from conftest import GOLD, ROOT, SAMPLE
from fastapi.testclient import TestClient

from contractiq.api import app
from contractiq.cli import main


def test_cli_extract_writes_all_formats(tmp_path, capsys):
    assert main(["extract", str(SAMPLE), "--out", str(tmp_path)]) == 0
    assert {p.name for p in tmp_path.iterdir()} == {"fictional_rfp.json", "fictional_rfp_requirements.csv", "fictional_rfp.xlsx"}
    assert "33 requirements" in capsys.readouterr().out


def test_cli_evaluate_prints_table_and_json(capsys):
    assert main(["evaluate", str(SAMPLE), "--gold", str(GOLD)]) == 0
    assert "overall" in capsys.readouterr().out
    assert main(["evaluate", str(SAMPLE), "--gold", str(GOLD), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["overall"]["f1"] > 0.9


def test_cli_llm_without_key_is_a_clean_error(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    assert main(["extract", str(SAMPLE), "--mode", "llm", "--out", str(tmp_path)]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_cli_dry_run_sends_nothing(capsys):
    assert main(["extract", str(SAMPLE), "--mode", "llm", "--dry-run"]) == 0
    assert "No request was sent" in capsys.readouterr().out


def test_cli_missing_file_is_a_clean_error(capsys):
    assert main(["extract", "nope.pdf"]) == 2


client = TestClient(app)


def test_api_health_and_sample(monkeypatch):
    monkeypatch.chdir(ROOT)  # a non-editable install finds the sample through the working folder
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/sample").json()["metadata"]["page_count"] == 8


def test_api_extract_upload():
    r = client.post("/extract", files={"file": ("rfp.pdf", SAMPLE.read_bytes(), "application/pdf")})
    assert r.status_code == 200 and len(r.json()["requirements"]) == 33


def test_api_extract_text_upload():
    r = client.post("/extract", files={"file": ("a.txt", b"C.1 The Contractor shall clean the site daily.", "text/plain")})
    assert r.status_code == 200 and r.json()["requirements"][0]["section"] == "C.1"


@pytest.mark.parametrize("params,status", [({"mode": "magic"}, 400), ({"mode": "llm"}, 400)])
def test_api_rejects_bad_mode_and_missing_key(params, status, monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    r = client.post("/extract", params=params, files={"file": ("rfp.pdf", SAMPLE.read_bytes(), "application/pdf")})
    assert r.status_code == status


def test_api_unreadable_pdf_is_422():
    assert client.post("/extract", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 422


def test_api_xlsx_download():
    r = client.post("/extract.xlsx", files={"file": ("rfp.pdf", SAMPLE.read_bytes(), "application/pdf")})
    assert r.status_code == 200 and r.content[:2] == b"PK"
