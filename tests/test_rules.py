import pytest

from contractiq.extractors import rules
from contractiq.pdf import to_blocks


def reqs(text):
    return rules._requirements(to_blocks([text]))


@pytest.mark.parametrize("text,iso", [
    ("due January 22, 2027", "2027-01-22"),
    ("due Jan. 5, 2027", "2027-01-05"),
    ("due 22 January 2027", "2027-01-22"),
    ("due 04/01/2027", "2027-04-01"),
    ("due Sept 9th, 2027", "2027-09-09"),
])
def test_date_formats(text, iso):
    assert rules.find_dates(text)[0][0] == iso


def test_impossible_dates_are_ignored():
    assert rules.find_dates("on February 30, 2027") == []


def test_date_labels_and_times():
    ks, skipped = rules._key_dates(to_blocks(["Pre-proposal site visit: December 9, 2026, 10:00 AM CT\n"
                                              "Random date: June 1, 2026"]))
    assert [(k.label, k.date, k.time) for k in ks] == [("Site visit", "2026-12-09", "10:00 AM CT")]
    assert skipped == 1


def test_duplicate_dates_are_merged():
    ks, _ = rules._key_dates(to_blocks(["Proposals due: January 22, 2027\nL.1 Proposals shall arrive by January 22, 2027."]))
    assert len(ks) == 1


@pytest.mark.parametrize("text,amount", [("$250,000 total", 250000), ("$2.5 million", 2.5e6), ("$1,000.50", 1000.5), ("$3 M", 3e6)])
def test_money_parsing(text, amount):
    assert rules._amounts(to_blocks([text]))[0].amount == amount


def test_money_labels():
    labels = {m.label for m in rules._amounts(to_blocks([
        "C.1 The ceiling is $10. C.2 A minimum of $5 is guaranteed. C.3 Any repair expected to exceed $7 needs approval."]))}
    assert {"ceiling", "approval threshold"} <= labels


def test_contract_types_are_normalised_in_order():
    t = rules._terms([], "A Time-and-Materials CLIN and a firm fixed price CLIN (FFP).")
    assert t.contract_type == "FFP; T&M"


def test_solicitation_number_fallback():
    assert rules._terms([], "Solicitation W91QUZ26R0042 issued").solicitation_number == "W91QUZ26R0042"


def test_modal_verbs_and_obligation_strength():
    r = {x.obligation: x for x in reqs("C.1 The Contractor shall a b c d.\nC.2 The Contractor must e f g h.\n"
                                       "C.3 The Contractor should i j k l.\nC.4 The Contractor is required to m n o p.")}
    assert set(r) == {"shall", "must", "should", "required"}
    assert r["should"].mandatory is False and r["shall"].mandatory is True


def test_party_detection():
    r = {x.section: x.party for x in reqs("C.1 The Government shall provide space and power.\n"
                                          "C.2 The Contractor shall bring tools and staff.\n"
                                          "L.1 Offerors shall submit four volumes of text.\n"
                                          "L.2 Volume I shall not exceed 25 pages total.")}
    assert r == {"C.1": "government", "C.2": "contractor", "L.1": "offeror", "L.2": "offeror"}


def test_will_needs_an_explicit_actor():
    assert reqs("M.1 Proposals will be evaluated on the following factors.") == []
    assert len(reqs("C.1 The Contractor will maintain a clean site always.")) == 1


def test_abbreviations_do_not_split_sentences():
    assert len(reqs("H.1 Contractor personnel must be U.S. citizens or residents.")) == 1


def test_known_limitation_no_modal_verb_is_missed():
    assert reqs("C.1 Hazardous materials are prohibited on site without approval.") == []


def test_clin_cdrl_and_factor_rows():
    blocks = to_blocks(["CLIN 0003 - Repairs - Type: T&M\nA001 | Monthly Report | Monthly | 5th day\n"
                        "Factor 1 – Technical\nSubfactor 1.1 – Approach\nFactor 2 - Price\n"
                        "Factor 1 is significantly more important than Factor 2."])
    assert [(c.number, c.type) for c in rules._clins(blocks)] == [("0003", "T&M")]
    assert [d.id for d in rules._deliverables(blocks)] == ["A001"]
    f = rules._factors(blocks)
    assert [x.name for x in f] == ["Technical", "Price"]
    assert f[0].subfactors == ["Approach"] and f[0].importance.startswith("significantly more important")


def test_cdrl_mentioned_only_in_prose_is_still_found():
    d = rules._deliverables(to_blocks(["C.1 Submit the report (CDRL B002) monthly."]))
    assert [x.id for x in d] == ["B002"]
