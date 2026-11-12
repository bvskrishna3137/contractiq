from contractiq.evaluate import evaluate, format_report
from contractiq.schema import Extraction, KeyDate, Requirement


def ex(*texts, dates=()):
    return Extraction(requirements=[Requirement(text=t, evidence=t, page=1) for t in texts],
                      key_dates=[KeyDate(label="x", date=d) for d in dates])


def test_identical_extractions_score_one(gold):
    rep = evaluate(gold, gold)
    assert rep["overall"]["f1"] == 1.0 and rep["terms"]["accuracy"] == 1.0


def test_missing_and_extra_items_are_counted():
    g = ex("The Contractor shall wash windows daily.", "The Contractor shall mop floors weekly.")
    p = ex("The Contractor shall wash windows daily.", "Something completely different happens here.")
    r = evaluate(p, g)["requirements"]
    assert (r["tp"], r["fp"], r["fn"]) == (1, 1, 1) and r["f1"] == 0.5


def test_small_wording_differences_still_match():
    g = ex("The Contractor shall wash windows daily.")
    p = ex("The Contractor shall wash the windows daily")
    assert evaluate(p, g)["requirements"]["tp"] == 1


def test_matching_is_one_to_one():
    g = ex("The Contractor shall wash windows daily.")
    p = ex("The Contractor shall wash windows daily.", "The Contractor shall wash windows daily!")
    r = evaluate(p, g)["requirements"]
    assert r["tp"] == 1 and r["fp"] == 1


def test_dates_match_on_value():
    assert evaluate(ex(dates=["2027-01-22", "2027-02-01"]), ex(dates=["2027-01-22"]))["key_dates"]["precision"] == 0.5


def test_empty_inputs_do_not_divide_by_zero():
    rep = evaluate(Extraction(), Extraction())
    assert rep["overall"]["f1"] == 0.0 and "requirements" in format_report(rep)
