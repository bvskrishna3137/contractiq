from contractiq.pdf import strip_repeated_lines, to_blocks


def test_repeated_headers_and_page_numbers_are_removed():
    pages = [f"BANNER TEXT\nfirst line {'abcde'[i]}\nmiddle {'vwxyz'[i]}\nlast line {'fghij'[i]}\nPage {i + 1}"
             for i in range(5)]
    out = strip_repeated_lines(pages)
    assert all("BANNER" not in p and "Page" not in p for p in out)
    assert out[2] == "first line c\nmiddle x\nlast line h"


def test_short_documents_are_left_alone():
    pages = ["BANNER\nx", "BANNER\ny"]
    assert strip_repeated_lines(pages) == pages


def test_wrapped_lines_join_and_refs_start_new_blocks():
    b = to_blocks(["C.1 The Contractor shall do a\nvery long thing.\nC.2 The Contractor shall rest."])
    assert [x.ref for x in b] == ["C.1", "C.2"]
    assert b[0].text == "C.1 The Contractor shall do a very long thing."


def test_paragraph_continues_across_pages_and_keeps_start_page():
    b = to_blocks(["C.1 The Contractor shall do a", "very long thing.\nC.2 Next one here."])
    assert b[0].page == 1 and b[0].text.endswith("very long thing.")


def test_section_letter_is_tracked_and_label_lines_stay_single():
    b = to_blocks(["SECTION L - INSTRUCTIONS\nNAICS Code: 561210\nKey Dates\nL.1 Offerors shall bid."])
    assert b[1].kind == "label" and b[2].text == "Key Dates"
    assert b[3].letter == "L"


def test_numbers_like_2_5_million_are_not_mistaken_for_refs():
    b = to_blocks(["C.1 Insurance of at least\n2.5 million is needed."])
    assert len(b) == 1
