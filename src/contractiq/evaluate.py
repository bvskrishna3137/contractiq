"""Score an extraction against a hand-labelled answer key (precision, recall, F1).

Matching is one-to-one and greedy. Requirements match on fuzzy text similarity
(difflib ratio >= 0.85) so harmless wording differences do not count as misses;
every other collection matches on a natural key (date, amount, CLIN number, ...).
Beyond P/R/F1 it also reports how often the *matched* requirements have the right
party, category and obligation.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from difflib import SequenceMatcher

from .schema import Extraction

THRESHOLD = 0.85


def _n(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _prf(tp: int, n_pred: int, n_gold: int) -> dict:
    p = tp / n_pred if n_pred else 0.0
    r = tp / n_gold if n_gold else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"tp": tp, "fp": n_pred - tp, "fn": n_gold - tp, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(f, 3), "predicted": n_pred, "expected": n_gold}


def _match(pred: list, gold: list, same: Callable[[object, object], float]) -> list[tuple[int, int]]:
    """Greedy one-to-one matching, best pairs first. Returns (pred_index, gold_index) pairs."""
    cand = sorted(((same(p, g), i, j) for i, p in enumerate(pred) for j, g in enumerate(gold)), reverse=True)
    used_p, used_g, pairs = set(), set(), []
    for score, i, j in cand:
        if score < THRESHOLD:
            break
        if i in used_p or j in used_g:
            continue
        used_p.add(i)
        used_g.add(j)
        pairs.append((i, j))
    return pairs


def _text_sim(a: str, b: str) -> float:
    return SequenceMatcher(None, _n(a), _n(b)).ratio()


def _exact(fn: Callable[[object], object]) -> Callable[[object, object], float]:
    return lambda p, g: 1.0 if fn(p) == fn(g) and fn(g) not in ("", None) else 0.0


def _field_equal(a: str, b: str) -> bool:
    a, b = _n(a), _n(b)
    return bool(a) and bool(b) and (a == b or a in b or b in a)


def evaluate(pred: Extraction, gold: Extraction) -> dict:
    report: dict = {}
    pairs = _match(pred.requirements, gold.requirements, lambda p, g: _text_sim(p.text, g.text))
    report["requirements"] = _prf(len(pairs), len(pred.requirements), len(gold.requirements))
    if pairs:
        def acc(attr: str) -> float:
            return round(sum(getattr(pred.requirements[i], attr) == getattr(gold.requirements[j], attr)
                             for i, j in pairs) / len(pairs), 3)
        report["requirement_attributes"] = {"party_accuracy": acc("party"), "category_accuracy": acc("category"),
                                            "obligation_accuracy": acc("obligation"), "matched": len(pairs)}

    simple = {
        "key_dates": (pred.key_dates, gold.key_dates, _exact(lambda x: x.date)),
        "amounts": (pred.terms.amounts, gold.terms.amounts, _exact(lambda x: x.amount)),
        "clins": (pred.clins, gold.clins, _exact(lambda x: x.number)),
        "deliverables": (pred.deliverables, gold.deliverables, _exact(lambda x: x.id.upper())),
        "evaluation_factors": (pred.evaluation_factors, gold.evaluation_factors,
                               lambda p, g: _text_sim(p.name, g.name)),
    }
    for name, (p, g, fn) in simple.items():
        report[name] = _prf(len(_match(p, g, fn)), len(p), len(g))

    fields = ["solicitation_number", "title", "agency", "contract_type", "naics", "set_aside",
              "period_of_performance", "place_of_performance"]
    hits = {f: _field_equal(getattr(pred.terms, f), getattr(gold.terms, f)) for f in fields}
    report["terms"] = {"correct": sum(hits.values()), "total": len(fields), "accuracy": round(sum(hits.values()) / len(fields), 3),
                       "wrong_fields": [f for f, ok in hits.items() if not ok]}

    # headline: micro-average over every list-type collection
    tp = sum(report[k]["tp"] for k in simple) + report["requirements"]["tp"]
    npred = sum(report[k]["predicted"] for k in simple) + report["requirements"]["predicted"]
    ngold = sum(report[k]["expected"] for k in simple) + report["requirements"]["expected"]
    report["overall"] = _prf(tp, npred, ngold)
    return report


def format_report(rep: dict) -> str:
    rows = ["collection            expected  found  correct  precision  recall     F1"]
    for k in ["requirements", "key_dates", "amounts", "clins", "deliverables", "evaluation_factors", "overall"]:
        r = rep[k]
        rows.append(f"{k:<21} {r['expected']:>8} {r['predicted']:>6} {r['tp']:>8} {r['precision']:>10.3f} "
                    f"{r['recall']:>7.3f} {r['f1']:>6.3f}")
    t = rep["terms"]
    rows.append(f"{'terms (fields)':<21} {t['total']:>8} {'':>6} {t['correct']:>8} {'':>10} {t['accuracy']:>7.3f}")
    a = rep.get("requirement_attributes")
    if a:
        rows.append(f"\nOf the {a['matched']} matched requirements: party {a['party_accuracy']:.0%}, "
                    f"category {a['category_accuracy']:.0%}, obligation {a['obligation_accuracy']:.0%} correct.")
    return "\n".join(rows)
