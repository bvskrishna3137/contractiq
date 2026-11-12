# Evaluation

## What is measured

`contractiq evaluate FILE --gold GOLD` runs an extraction and compares it with a hand-labelled answer key.

- **Requirements:** greedy one-to-one matching on text similarity (difflib ratio of at least 0.85 after normalising case and punctuation). Harmless wording differences count as a match; a different sentence does not.
- **Key dates:** match on the ISO date. **Amounts:** on the numeric value. **CLINs:** on the number. **CDRLs:** on the id. **Evaluation factors:** on the name (fuzzy).
- **Contract terms:** eight fields, each correct if the normalised values are equal or one contains the other.
- For matched requirements it also reports accuracy of **party**, **category** and **obligation**.
- **Overall** is the micro-average across all list-type collections.

Precision is "of what it found, how much was right"; recall is "of what exists, how much it found".

## Result on the fictional sample (rules mode)

| Collection | Expected | Found | Correct | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| Requirements | 35 | 33 | 32 | 0.970 | 0.914 | 0.941 |
| Key dates | 6 | 6 | 6 | 1.000 | 1.000 | 1.000 |
| Amounts | 5 | 5 | 5 | 1.000 | 1.000 | 1.000 |
| CLINs | 5 | 5 | 5 | 1.000 | 1.000 | 1.000 |
| CDRLs | 6 | 6 | 6 | 1.000 | 1.000 | 1.000 |
| Evaluation factors | 4 | 4 | 4 | 1.000 | 1.000 | 1.000 |
| **Overall** | 61 | 59 | 58 | 0.983 | 0.951 | 0.967 |

Terms 8/8. Matched requirements: party 100%, obligation 100%, category 91%.

### The errors, explained

| Kind | Item | Why |
|---|---|---|
| Missed (C.3.4) | "Emergency calls will be answered by a live dispatcher at all hours." | `will` with no named actor is ignored on purpose, to avoid "Proposals will be evaluated..." |
| Missed (C.4.3) | "Hazardous materials are prohibited on site..." | a prohibition with no modal verb |
| Missed (H.4) | "A satisfactory background check is a condition of site access..." | a condition with no modal verb |
| False positive (C.3.6) | "Nothing in this section shall be construed to require..." | contains `shall`, but limits scope instead of imposing a duty |
| Wrong category x3 | C.2.3, C.3.5, L.3 | keyword rules: a quality-control plan is filed as technical, a Government duty as technical, and "Past Performance" in a proposal-volume list as past performance |

These are stable: `tests/test_sample.py` asserts that the misses are exactly C.3.4, C.4.3 and H.4.

## Why this is not a benchmark

- **One synthetic document**, written by the same person who wrote the extractor. The formatting is clean and the vocabulary is the kind the rules look for, so the offline baseline scores high on structured fields. Real solicitations (SF-33 forms, multi-column pages, tables, amendments) will score lower.
- **35 requirements** is far too few to put error bars on anything.
- **LLM mode has not been measured here.** No API key was used while building this project; the LLM path is covered by unit tests with a fake client, which show that parsing, validation, retry, salvage, merging and grounding behave, not that a model extracts well.

## How to measure LLM mode

```bash
contractiq evaluate samples/fictional_rfp.pdf --gold samples/gold.json --mode llm
```

Compare it with the table above. To go further, label a real document you are allowed to use (copy `samples/gold.json` as a template and keep the JSON shape), keep it out of the repository, and run both modes on it. Report the document count and size next to any number you share.

## Using the evaluator for development

The sample and answer key are generated together by `tools/make_sample_rfp.py`. To test a new rule, add a sentence to the source there, regenerate (`python tools/make_sample_rfp.py`), and check the delta in `contractiq evaluate`. `tests/test_sample.py` keeps a regression floor (requirement recall at least 0.90, precision at least 0.95, overall F1 at least 0.95).
