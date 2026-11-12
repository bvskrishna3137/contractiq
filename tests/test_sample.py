"""Regression tests on the FICTIONAL sample RFP. These guard the baseline; they are not a benchmark."""
import importlib.util
import json
import sys

from conftest import GOLD, ROOT, SAMPLE

from contractiq.evaluate import evaluate


def test_sample_is_labelled_fictional_on_every_page(sample_pages):
    import pdfplumber
    with pdfplumber.open(SAMPLE) as pdf:
        assert all("FICTIONAL SAMPLE" in (p.extract_text() or "") for p in pdf.pages)


def test_headers_and_footers_do_not_leak_into_results(sample_result):
    assert all("FICTIONAL SAMPLE" not in r.text and "Page " not in r.text for r in sample_result.requirements)


def test_baseline_scores_do_not_regress(sample_result, gold):
    rep = evaluate(sample_result, gold)
    assert rep["requirements"]["recall"] >= 0.90 and rep["requirements"]["precision"] >= 0.95
    assert rep["overall"]["f1"] >= 0.95
    assert rep["terms"]["accuracy"] == 1.0
    for k in ("key_dates", "amounts", "clins", "deliverables", "evaluation_factors"):
        assert rep[k]["f1"] == 1.0, k


def test_known_baseline_misses_are_the_documented_ones(sample_result, gold):
    got = {r.text for r in sample_result.requirements}
    missed = {r.section for r in gold.requirements if r.text not in got}
    assert missed == {"C.3.4", "C.4.3", "H.4"}  # no modal verb, or "will" without an actor


def test_every_item_is_grounded_with_a_page(sample_result):
    assert sample_result.stats()["ungrounded"] == 0
    assert all(r.page for r in sample_result.requirements)


def test_gold_pages_match_extracted_pages(sample_result, gold):
    by_text = {r.text: r.page for r in sample_result.requirements}
    assert all(by_text[g.text] == g.page for g in gold.requirements if g.text in by_text)


def test_sample_and_gold_regenerate_identically(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("make_sample_rfp", ROOT / "tools" / "make_sample_rfp.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["make_sample_rfp"] = mod  # dataclasses look the module up by name
    spec.loader.exec_module(mod)
    pdf = tmp_path / "x.pdf"
    mod.build_pdf(pdf)
    data = mod.build_gold(pdf).model_dump(exclude={"metadata": {"generated_at"}})
    data["metadata"]["source_file"] = "fictional_rfp.pdf"
    assert data == json.loads(GOLD.read_text(encoding="utf-8"))
