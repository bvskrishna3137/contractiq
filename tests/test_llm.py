"""LLM mode, tested with a fake client. No network and no API key are involved."""
import pytest

from contractiq.extractors import llm
from contractiq.pipeline import run_pages

PAGES = ["Cover page text here, long enough to count.",
         "C.1 Hazardous materials are prohibited on site without approval. The Contractor shall wash the windows.",
         "Proposals due: January 22, 2027, 2:00 PM CT. CLIN 0001 - Maintenance - Type: FFP"]

GOOD = {
    "terms": {"solicitation_number": "X-1", "contract_type": "FFP"},
    "requirements": [
        {"text": "Hazardous materials are prohibited on site without approval.",
         "evidence": "Hazardous materials are prohibited on site without approval.", "page": 2,
         "obligation": "required", "party": "contractor", "category": "technical", "section": "C.1"},
        {"text": "The Contractor shall wash the windows.", "evidence": "The Contractor shall wash the windows.",
         "page": 2, "obligation": "shall", "party": "contractor", "category": "technical"}],
    "key_dates": [{"label": "Proposals due", "date": "2027-01-22", "time": "2:00 PM CT", "raw": "January 22, 2027",
                   "evidence": "Proposals due: January 22, 2027, 2:00 PM CT", "page": 3}],
    "clins": [{"number": "0001", "description": "Maintenance", "type": "FFP",
               "evidence": "CLIN 0001 - Maintenance - Type: FFP", "page": 3}],
}


def test_happy_path_finds_requirement_without_modal_verb(fake_client):
    ex = run_pages(PAGES, mode="llm", client=fake_client(GOOD))
    assert ex.stats()["requirements"] == 2 and ex.stats()["ungrounded"] == 0
    assert ex.requirements[0].source == "llm" and ex.requirements[0].obligation == "required"
    assert ex.terms.solicitation_number == "X-1" and ex.key_dates[0].date == "2027-01-22"
    assert ex.metadata.mode == "llm" and ex.metadata.model == llm.DEFAULT_MODEL


def test_request_is_forced_tool_use_with_page_markers(fake_client):
    c = fake_client(GOOD)
    run_pages(PAGES, mode="llm", client=c, model="my-model")
    kw = c.calls[0]
    assert kw["model"] == "my-model"
    assert kw["tool_choice"] == {"type": "tool", "name": "record_extraction"}
    assert "[[PAGE 2]]" in kw["messages"][0]["content"]


def test_tool_schema_is_fully_inlined():
    s = llm.dump_schema()
    assert "$ref" not in s and "$defs" not in s
    assert llm.tool_definition()["input_schema"]["properties"]["requirements"]["items"]["properties"]["party"]


def test_invented_quote_is_flagged_not_trusted(fake_client):
    bad = {"requirements": [{"text": "The Contractor shall paint the moon.", "evidence": "The Contractor shall paint the moon.",
                             "page": 2, "obligation": "shall", "party": "contractor", "category": "technical"}]}
    ex = run_pages(PAGES, mode="llm", client=fake_client(bad))
    assert ex.requirements[0].grounded is False and ex.stats()["ungrounded"] == 1
    assert any("not found" in w for w in ex.warnings)


def test_wrong_page_number_is_corrected(fake_client):
    wrong = {"requirements": [dict(GOOD["requirements"][1], page=1)]}
    assert run_pages(PAGES, mode="llm", client=fake_client(wrong)).requirements[0].page == 2


def test_validation_error_triggers_one_retry_with_the_error(fake_client):
    invalid = {"requirements": [dict(GOOD["requirements"][1], obligation="banana")]}
    c = fake_client(invalid, GOOD)
    ex = run_pages(PAGES, mode="llm", client=c)
    assert len(c.calls) == 2 and ex.stats()["requirements"] == 2
    last = c.calls[1]["messages"][-1]["content"][0]
    assert last["is_error"] and "Validation failed" in last["content"]


def test_persistent_invalid_items_are_salvaged_and_counted(fake_client):
    mixed = {"requirements": [GOOD["requirements"][1], dict(GOOD["requirements"][0], obligation="banana")]}
    ex = run_pages(PAGES, mode="llm", client=fake_client(mixed))
    assert [r.text for r in ex.requirements] == ["The Contractor shall wash the windows."]
    assert any("1 item(s) failed validation" in w for w in ex.warnings)


def test_model_that_skips_the_tool_is_reported(fake_client):
    ex = run_pages(PAGES, mode="llm", client=fake_client(None))
    assert ex.stats()["requirements"] == 0 and any("did not call" in w for w in ex.warnings)


def test_truncated_output_is_reported(fake_client):
    ex = run_pages(PAGES, mode="llm", client=fake_client(GOOD, stop_reason="max_tokens"))
    assert any("ran out of output space" in w for w in ex.warnings)


def test_all_requests_failing_raises_a_readable_error(fake_client):
    with pytest.raises(RuntimeError, match="Every request failed.*boom"):
        run_pages(PAGES, mode="llm", client=fake_client(ConnectionError("boom")))


def test_one_failed_chunk_keeps_the_rest(fake_client, monkeypatch):
    monkeypatch.setattr(llm, "MAX_CHARS", 60)
    c = fake_client(GOOD, ConnectionError("rate limited"), GOOD)
    ex, _ = llm.extract(PAGES, client=c, max_chars=60)
    assert ex.requirements and any("Request failed" in w and "rate limited" in w for w in ex.warnings)


def test_chunks_follow_page_boundaries_and_duplicates_merge(fake_client):
    pages = ["x" * 50, "y" * 50, "z" * 50]
    chunks = llm.chunk_pages(pages, max_chars=80)
    assert [(a, b) for a, b, _ in chunks] == [(1, 1), (2, 2), (3, 3)]
    ex, _ = llm.extract(PAGES, client=fake_client(GOOD), max_chars=60)  # same answer for every chunk
    assert len(ex.requirements) == 2 and len(ex.clins) == 1


def test_bad_iso_date_is_dropped_but_raw_text_kept(fake_client):
    bad = {"key_dates": [dict(GOOD["key_dates"][0], date="2027-13-45")]}
    d = run_pages(PAGES, mode="llm", client=fake_client(bad)).key_dates[0]
    assert d.date == "" and d.raw == "January 22, 2027"


def test_missing_api_key_gives_a_helpful_message(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm.make_client()


def test_dotenv_reader_does_not_override_real_env(monkeypatch, tmp_path):
    f = tmp_path / ".env"
    f.write_text("# c\nA_TEST_KEY='from-file'\nB_TEST_KEY=2\n")
    monkeypatch.setenv("A_TEST_KEY", "from-env")
    monkeypatch.delenv("B_TEST_KEY", raising=False)
    llm.load_dotenv(f)
    import os
    assert os.environ["A_TEST_KEY"] == "from-env" and os.environ["B_TEST_KEY"] == "2"
    monkeypatch.delenv("B_TEST_KEY")


def test_estimate_counts_requests():
    e = llm.estimate(PAGES)
    assert e["calls"] == 1 and e["approx_input_tokens"] > 0


def test_quote_running_over_a_page_break_is_still_grounded(fake_client):
    from contractiq.grounding import ground
    from contractiq.schema import Extraction, Requirement
    pages = ["intro text. The Contractor shall wash", "the windows daily. more text"]
    ex = Extraction(requirements=[Requirement(text="The Contractor shall wash the windows daily.",
                                              evidence="The Contractor shall wash the windows daily.", page=1)])
    assert ground(ex, pages) == 0 and ex.requirements[0].page == 1
