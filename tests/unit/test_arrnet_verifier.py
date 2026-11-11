"""ARR Network Verifier: evidence checks and consensus classes on synthetic readings (no PDF).

Run with the tool's own environment:
    tools/arrnet/.venv/bin/python -m pytest tests/unit/test_arrnet_*.py
"""

from __future__ import annotations

import pytest

pytest.importorskip("arrnet")

from arrnet import store, verifier  # noqa: E402

PAGE_TEXT = (
    "Table 4.52: ARR approved for FY 2026-27 (Rs. Crore)\n"
    "Power Purchase Cost 5,485.10 5,678.19\n"
    "O&M Expenses 3,633.30 3,468.46\n"
    "Net ARR 9,118.40 9,146.65\n"
)


def reading(reader, value, printed=None, label="Power Purchase Cost", head="power_purchase", page=10, **kw):
    printed = printed or f"{value:,.2f}"
    return {
        "reader": reader,
        "reader_version": f"{reader} 1",
        "utility": "UPCL",
        "fiscal_year": "FY2026-27",
        "voice": "approved",
        "stage": "ARR",
        "head": head,
        "label": label,
        "value_printed": printed,
        "value": value,
        "unit": "crore",
        "value_crore": value,
        "page": page,
        "quote": kw.pop("quote", f"{label} {printed}"),
        "table_page": page,
        "table_title": "Table 4.52: ARR approved for FY 2026-27 (Rs. Crore)",
        **kw,
    }


@pytest.fixture()
def idx():
    return verifier.PageIndex(
        [{"page": 10, "text": PAGE_TEXT, "has_text_layer": True}, {"page": 11, "text": "", "has_text_layer": False}]
    )


def test_evidence_passes_when_quote_numbers_are_on_the_page(idx):
    ok, why, src = verifier.evidence(reading("textlayer", 5678.19), idx, {})
    assert ok and src == "text layer", why


def test_evidence_rejects_a_number_not_on_the_page(idx):
    ok, why, _ = verifier.evidence(reading("docling", 5678.91, "5,678.91"), idx, {})
    assert not ok and "not on page 10" in why


def test_evidence_rejects_a_value_not_in_its_quote(idx):
    r = reading("llm", 3468.46, "3,468.46", quote="Power Purchase Cost 5,678.19")
    ok, why, _ = verifier.evidence(r, idx, {})
    assert not ok and "not in the quote" in why


def test_evidence_rejects_missing_page_or_quote(idx):
    assert not verifier.evidence(reading("llm", 1.0, quote=""), idx, {})[0]
    assert not verifier.evidence(reading("llm", 5678.19, page=99), idx, {})[0]


def test_ocr_page_is_checked_against_the_readers_own_text_and_says_so(idx):
    r = reading("docling", 120.5, "120.50", page=11)
    ok, why, _ = verifier.evidence(r, idx, {})
    assert not ok and "no text layer" in why
    ok, _, src = verifier.evidence(r, idx, {"11": "| Depreciation | 120.50 |"})
    assert ok and "OCR" in src


def test_consensus_single_agreed_and_three_readers():
    facts = verifier.consensus([reading("textlayer", 5678.19)])
    assert [f["consensus"] for f in facts] == ["single"]
    facts = verifier.consensus(
        [reading("textlayer", 5678.19), reading("docling", 5678.19, label="Power purchase cost")]
    )
    assert [f["consensus"] for f in facts] == ["agreed_2"]
    assert facts[0]["readers"] == ["textlayer", "docling"]
    assert facts[0]["label"] == "Power Purchase Cost"  # the text-layer reading represents the fact
    three = [reading("textlayer", 5678.19), reading("docling", 5678.19), reading("llm", 5678.192)]
    assert verifier.consensus(three)[0]["consensus"] == "agreed_3"  # within 0.005


def test_consensus_conflict_keeps_every_candidate():
    facts = verifier.consensus([reading("textlayer", 5678.19), reading("docling", 5678.91, "5,678.91")])
    assert len(facts) == 1
    f = facts[0]
    assert f["consensus"] == "conflict" and f["value"] == 5678.19
    assert {(r["reader"], r["agrees"]) for r in f["readings"]} == {("textlayer", True), ("docling", False)}
    assert f["readers"] == ["textlayer", "docling"]  # every reader involved; the application needs two


def test_different_labels_and_values_are_different_figures():
    facts = verifier.consensus(
        [reading("textlayer", 5678.19), reading("docling", 3468.46, label="O&M Expenses", head="power_purchase")]
    )
    assert sorted(f["consensus"] for f in facts) == ["single", "single"]


def test_one_reader_never_agrees_with_itself():
    facts = verifier.consensus(
        [reading("textlayer", 5678.19), reading("textlayer", 5678.19, label="Total power purchase")]
    )
    assert all(f["consensus"] == "single" for f in facts) and len(facts) == 2


def test_readings_without_utility_year_or_voice_make_no_fact():
    assert verifier.consensus([reading("textlayer", 5678.19, voice=None)]) == []


def test_headline_is_the_net_arr_row_of_the_main_table():
    rs = [
        reading("textlayer", v, label=lab, head=h, _seq=i)
        for i, (v, lab, h) in enumerate(
            [
                (5678.19, "Power Purchase Cost", "power_purchase"),
                (3468.46, "O&M Expenses", "om"),
                (9200.0, "Aggregate Revenue Requirement", "arr"),
                (9146.65, "Net ARR", "net_arr"),
            ]
        )
    ]
    facts = verifier.consensus(rs)
    verifier.headlines(facts)
    heads = [f for f in facts if f.get("is_headline")]
    assert len(heads) == 1 and heads[0]["head"] == "net_arr" and "net ARR" in heads[0]["headline_why"]


def test_outlier_headline_is_set_aside_with_the_reason():
    facts = [{"utility": "UPCL", "is_headline": True, "value_crore": v} for v in (9000.0, 9500.0, 10000.0, 95.0)]
    assert verifier.set_aside_outliers(facts) == 1
    assert "five times" in facts[3]["set_aside"] and "set_aside" not in facts[0]


def test_fixture_results_are_never_verified_into_real_output(tmp_path, monkeypatch):
    monkeypatch.setenv("ARRNET_STATE", str(tmp_path))
    sha = "f" * 64
    store.write(sha, "pages", {"order": {}, "pages": [{"page": 10, "text": PAGE_TEXT, "has_text_layer": True}]})
    base = {"reader_version": "x", "status": "ok", "tables": [], "parameters": [], "page_texts": {}, "pages": [10]}
    store.write(
        sha,
        "textlayer",
        {
            **base,
            "reader": "textlayer",
            "is_real": True,
            "values": [
                {k: v for k, v in reading("textlayer", 5678.19).items() if k not in ("reader", "reader_version")}
            ],
        },
    )
    store.write(
        sha,
        "llm",
        {
            **base,
            "reader": "llm",
            "is_real": False,
            "values": [{k: v for k, v in reading("llm", 5678.19).items() if k not in ("reader", "reader_version")}],
        },
    )
    v = verifier.verify_order(
        {"url": "https://example.org/o.pdf", "sha256": sha, "commission": "UERC", "arr_year": "FY2026-27"}
    )
    assert set(v["readers"]) == {"textlayer"}
    assert v["facts"][0]["consensus"] == "single"


def test_rejected_readings_are_counted_and_not_posted(tmp_path, monkeypatch):
    monkeypatch.setenv("ARRNET_STATE", str(tmp_path))
    from arrnet.ingest import DryRunSink

    sha = "e" * 64
    store.write(sha, "pages", {"order": {}, "pages": [{"page": 10, "text": PAGE_TEXT, "has_text_layer": True}]})
    vals = [reading("docling", 5678.19), reading("docling", 1234.56, label="Made up")]
    vals = [{k: v for k, v in x.items() if k not in ("reader", "reader_version")} for x in vals]
    store.write(
        sha,
        "docling",
        {
            "reader": "docling",
            "reader_version": "d",
            "status": "ok",
            "is_real": True,
            "tables": [],
            "values": vals,
            "parameters": [],
            "page_texts": {},
            "pages": [10],
        },
    )
    v = verifier.verify_order(
        {"url": "https://example.org/o.pdf", "sha256": sha, "commission": "UERC", "arr_year": "FY2026-27"}
    )
    assert v["readers"]["docling"]["rejected_values"] == 1
    sink = DryRunSink(tmp_path / "dry")
    verifier.post_order(sink, v)
    posted = (tmp_path / "dry" / "arr_values.jsonl").read_text().splitlines()
    assert len(posted) == 1 and '"replace": true' in posted[0]
    facts = (tmp_path / "dry" / "facts.jsonl").read_text()
    assert "1234.56" not in facts and '"replace_order": true' in facts and "reviewed" not in facts
