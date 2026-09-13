"""Page triage rules (Section 6.3) as pure functions, then over the synthetic fixtures.

These pin the behaviour the reading hazards in Parts D, E and F depend on: printed labels that
are not the PDF index (roman front matter, constant offsets, footer-less pages, conflicts), a
text layer that exists but is useless, vector-drawn tables with no text at all, and the rule
that a page which matches nothing clearly is `unknown` — never guessed.
"""

from __future__ import annotations

import pymupdf
import pytest

from fixtures.synthetic_pdfs import garbled_text_pdf, labelled_order_pdf, mixed_text_and_image_pdf
from tariff_api.page_signals import extract_signals
from tariff_api.triage import (
    LabelSegment,
    ObservedLabel,
    PageSignals,
    assess_text,
    classify_page,
    extract_label,
    infer_label_rule,
    int_to_roman,
    resolve_label,
    roman_to_int,
)

# ------------------------------------------------------------------ text quality


def test_glyph_soup_is_flagged_even_with_perfect_glyph_coverage():
    """The failure this guards: a weighted average that let a page of consonant soup pass
    because its glyphs were all valid codepoints."""
    soup = " ".join(["xqzvbn ptkrsd wxqzb mnplk zzxqw vbnmk"] * 12)
    q = assess_text(soup, [(10 * i, 72.0, "x") for i in range(20)])
    assert q.glyph_coverage == 1.0
    assert q.dictionary_hit_rate < 0.1
    assert q.token_count >= 30
    sig = PageSignals(
        text_chars=len(soup),
        line_count=20,
        image_count=0,
        image_area_ratio=0,
        drawing_count=0,
        ruling_line_count=0,
        aligned_column_count=1,
        rotation=0,
        text=soup,
        quality=q,
    )
    res = classify_page(sig)
    assert "text_not_wordlike" in res.quality_flags
    assert "low_text_quality" in res.quality_flags
    assert res.ocr_recommended is True


def test_numeric_table_page_is_not_condemned_for_having_few_words():
    """A rate table is mostly numbers.  With too few alphabetic tokens to judge, the dictionary
    check must abstain rather than flag."""
    text = "Slab kWh Rs\n" + "\n".join(f"{i * 100} 6.{i}5 90.00" for i in range(40))
    q = assess_text(text, [(10 * i, 72.0, "x") for i in range(41)])
    assert q.token_count < 30
    sig = PageSignals(
        text_chars=len(text),
        line_count=41,
        image_count=0,
        image_area_ratio=0,
        drawing_count=40,
        ruling_line_count=12,
        aligned_column_count=3,
        rotation=0,
        text=text,
        quality=q,
    )
    res = classify_page(sig)
    assert res.page_class == "table"
    assert "text_not_wordlike" not in res.quality_flags
    assert "low_text_quality" not in res.quality_flags


def test_damaged_glyph_mapping_and_interleaved_columns_are_separate_flags():
    text = "the tariff order ���������� for supply"
    lines = [(100.0, 72.0, "a"), (20.0, 300.0, "b"), (120.0, 72.0, "c"), (40.0, 300.0, "d"), (140.0, 72.0, "e")]
    q = assess_text(text, lines)
    assert q.glyph_coverage < 0.95
    assert q.reading_order_sanity < 0.7
    sig = PageSignals(
        text_chars=len(text),
        line_count=5,
        image_count=0,
        image_area_ratio=0,
        drawing_count=0,
        ruling_line_count=0,
        aligned_column_count=2,
        rotation=0,
        text=text,
        quality=q,
    )
    flags = classify_page(sig).quality_flags
    assert "glyph_mapping_damaged" in flags
    assert "suspected_column_interleaving" in flags
    assert "low_text_quality" in flags


# ------------------------------------------------------------------ classification


def _sig(**kw) -> PageSignals:
    base = dict(
        text_chars=0,
        line_count=0,
        image_count=0,
        image_area_ratio=0.0,
        drawing_count=0,
        ruling_line_count=0,
        aligned_column_count=0,
        rotation=0,
        text="",
        quality=None,
    )
    base.update(kw)
    return PageSignals(**base)


@pytest.mark.parametrize(
    ("signals", "expected_class", "expected_flags"),
    [
        (dict(), "blank", {"no_text_layer"}),
        (dict(image_count=1, image_area_ratio=0.8), "image_only", {"no_text_layer", "ocr_needed"}),
        (
            dict(drawing_count=900),
            "vector_graphics_text_sparse",
            {"no_text_layer", "ocr_needed", "overlapping_graphics"},
        ),
        (dict(text_chars=40, drawing_count=900, line_count=2), "vector_graphics_text_sparse", {"ocr_needed"}),
        (dict(image_count=1, image_area_ratio=0.05), "unknown", {"no_text_layer", "ocr_needed"}),
        (dict(text_chars=300, line_count=15, ruling_line_count=12, aligned_column_count=4), "table", set()),
        (
            dict(
                text_chars=900,
                line_count=40,
                ruling_line_count=12,
                aligned_column_count=4,
                text=" ".join(["the commission approves the tariff for supply"] * 15),
            ),
            "mixed",
            set(),
        ),
        (dict(text_chars=60, line_count=3, text="ANNEXURE - I\nRATE SCHEDULE"), "annexure_cover", set()),
        (dict(text_chars=60, line_count=3, text="some words"), "unknown", set()),
        (dict(text_chars=2000, line_count=40), "narrative", set()),
        (dict(text_chars=2000, line_count=40, rotation=90), "narrative", {"rotated"}),
    ],
)
def test_classification_rules(signals, expected_class, expected_flags):
    res = classify_page(_sig(**signals))
    assert res.page_class == expected_class
    assert set(res.quality_flags) >= expected_flags
    assert res.rationale  # every decision explains itself


def test_thresholds_are_overridable_per_profile():
    res = classify_page(_sig(drawing_count=100), thresholds={"vector_min_drawings": 50})
    assert res.page_class == "vector_graphics_text_sparse"


# ------------------------------------------------------------------ labels


def test_roman_numerals_round_trip():
    for n in (1, 4, 9, 14, 40, 90, 400, 1994):
        assert roman_to_int(int_to_roman(n)) == n
    assert roman_to_int("IV") == 4 and roman_to_int("xxiv") == 24
    assert roman_to_int("iiii") is None and roman_to_int("") is None and roman_to_int("page") is None
    assert int_to_roman(12, upper=True) == "XII"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("body text\nmore text\nPage 12 of 423", ("12", "decimal")),
        ("Chapter – 6 : Tariff Charges     Page 209", ("209", "decimal")),
        ("some text\n\n   iv   \n", ("iv", "roman_lower")),
        ("some text\nPage IV", ("IV", "roman_upper")),
        ("body\n\n42", ("42", "decimal")),
        # running prose is not a label: "page 1" does not end the line
        ("Fixture text page 1. This page has a text layer.", None),
        ("As stated on page 12 of the petition, the licensee", None),
        ("no label here at all", None),
    ],
)
def test_footer_label_extraction(text, expected):
    obs = extract_label(text)
    if expected is None:
        assert obs is None
    else:
        assert obs is not None and (obs.value, obs.style) == expected


def test_label_rule_inference_roman_front_matter_then_offset():
    """The KERC/GERC shape: roman i-x on the contents pages, then printed = index - 16."""
    obs = [ObservedLabel(i, int_to_roman(i), i, "roman_lower", "") for i in range(1, 11)]
    obs += [
        ObservedLabel(i, str(i - 16), i - 16, "decimal", "") for i in range(17, 60) if i % 3
    ]  # some pages footer-less
    segs = infer_label_rule(obs, page_count=570)
    assert [(s.start_index, s.end_index, s.style, s.offset) for s in segs] == [
        (1, 16, "roman_lower", 0),
        (17, 570, "decimal", -16),
    ]
    # printed 209 -> PDF 225, printed 534 -> PDF 550 (the E.3 acceptance check), footer-less pages included
    assert segs[1].label_for(225) == "209" and segs[1].label_for(550) == "534"
    assert resolve_label(225, None, None, segs) == ("209", "rule", [])


def test_label_rule_npcl_shape_identity():
    obs = [ObservedLabel(i, str(i), i, "decimal", "") for i in range(1, 401)]
    segs = infer_label_rule(obs, page_count=423)
    assert [(s.start_index, s.end_index, s.offset) for s in segs] == [(1, 423, 0)]
    assert segs[0].label_for(402) == "402"  # image-only tail pages inherit the rule


def test_single_disagreeing_page_does_not_become_a_rule():
    obs = [ObservedLabel(i, str(i), i, "decimal", "") for i in range(1, 8)]
    obs.append(ObservedLabel(8, "99", 99, "decimal", ""))
    obs += [ObservedLabel(i, str(i), i, "decimal", "") for i in range(9, 13)]
    segs = infer_label_rule(obs, page_count=12)
    assert [(s.start_index, s.end_index, s.offset) for s in segs] == [(1, 12, 0)]
    label, source, flags = resolve_label(8, None, obs[7], segs)
    assert (label, source) == ("99", "observed")
    assert "label_off_rule" in flags  # shown, not silently corrected


def test_resolution_precedence_and_conflicts():
    segs = [LabelSegment(1, 10, "decimal", 0, 10)]
    assert resolve_label(3, "3", ObservedLabel(3, "3", 3, "decimal", ""), segs) == ("3", "observed", [])
    assert resolve_label(3, "iii", ObservedLabel(3, "3", 3, "decimal", ""), segs) == (
        "3",
        "observed",
        ["label_conflict"],
    )
    assert resolve_label(4, "4", None, segs) == ("4", "rule", [])
    assert resolve_label(4, "x", None, segs) == ("4", "rule", ["label_conflict"])
    assert resolve_label(4, "iv", None, []) == ("iv", "declared", [])
    assert resolve_label(4, None, None, []) == (None, "none", [])
    assert infer_label_rule([], 10) == []


# ------------------------------------------------------------------ over the fixtures


def _triage(data: bytes):
    doc = pymupdf.open(stream=data, filetype="pdf")
    rows = []
    for i in range(doc.page_count):
        sig = extract_signals(doc[i])
        obs = extract_label(sig.text)
        if obs:
            obs.page_index = i + 1
        rows.append((sig, classify_page(sig), obs, doc[i].get_label() or None))
    return doc.page_count, rows


def test_labelled_order_fixture_end_to_end():
    n, rows = _triage(labelled_order_pdf())
    classes = [r[1].page_class for r in rows]
    assert classes == [
        "narrative",
        "narrative",
        "narrative",  # contents pages i-iii
        "narrative",  # body, printed 1
        "annexure_cover",  # printed 2
        "table",  # ruled rate table, printed 3
        "vector_graphics_text_sparse",  # the KERC hazard, no footer
        "image_only",  # scan, no footer
        "blank",
        "narrative",
        "narrative",
        "narrative",
    ]
    assert rows[6][1].ocr_recommended and rows[7][1].ocr_recommended
    assert "no_text_layer" in rows[6][1].quality_flags and "overlapping_graphics" in rows[6][1].quality_flags

    observations = [r[2] for r in rows if r[2]]
    segs = infer_label_rule(observations, n)
    assert [(s.start_index, s.end_index, s.style, s.offset) for s in segs] == [
        (1, 3, "roman_lower", 0),
        (4, 12, "decimal", -3),
    ]
    resolved = [resolve_label(i + 1, rows[i][3], rows[i][2], segs) for i in range(n)]
    assert [r[0] for r in resolved] == ["i", "ii", "iii", "1", "2", "3", "4", "5", "6", "7", "99", "9"]
    assert [r[1] for r in resolved] == ["observed"] * 6 + ["rule"] * 3 + ["observed"] * 3
    assert resolved[10][2] == ["label_off_rule"]  # the page whose footer says 99
    assert all(r[2] == [] for i, r in enumerate(resolved) if i != 10)


def test_garbled_fixture_is_flagged_for_ocr():
    _, rows = _triage(garbled_text_pdf())
    sig, res, _, _ = rows[0]
    assert sig.text_chars > 100  # a text layer exists...
    assert "text_not_wordlike" in res.quality_flags  # ...and is useless
    assert res.ocr_recommended is True


def test_declared_labels_are_used_when_nothing_is_printed():
    """The mixed fixture declares PDF page labels (i, ii, 1-4) and prints none: no conflicts,
    every page resolves to the declared label."""
    n, rows = _triage(mixed_text_and_image_pdf())
    assert all(r[2] is None for r in rows)  # body text "page 1." is not a footer label
    segs = infer_label_rule([], n)
    resolved = [resolve_label(i + 1, rows[i][3], None, segs) for i in range(n)]
    assert [r[0] for r in resolved] == ["i", "ii", "1", "2", "3", "4"]
    assert all(r[1] == "declared" and r[2] == [] for r in resolved)
