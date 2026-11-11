"""ARR Network Librarian: paragraphs, headings and chunks from page text (no model needed)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("arrnet")

from arrnet import librarian, store  # noqa: E402
from arrnet.ingest import DryRunSink  # noqa: E402

PAGE = """CHAPTER 4: AGGREGATE REVENUE REQUIREMENT
4.13 Operation and Maintenance Expenses
4.13.1 The Petitioner has claimed O&M expenses of Rs. 3,470.68 crore for FY 2026-27
in accordance with the Regulations.
4.13.2 The Commission has examined the submission and approves Rs. 3,468.46 crore.
Particulars FY 2025-26 FY 2026-27
Employee Cost 2,987.62 2,990.10
R&M 155.87 160.20

The Commission directs the Petitioner to submit the audited accounts by 30 June.
12
"""


def test_paragraphs_split_on_numbers_and_blank_lines_and_skip_table_rows():
    ps = librarian.split_paragraphs(PAGE)
    texts = [p["text"] for p in ps]
    assert ps[0]["kind"] == "heading" and texts[0].startswith("CHAPTER 4")
    assert any(p["kind"] == "heading" and p["text"] == "4.13 Operation and Maintenance Expenses" for p in ps)
    claimed = next(t for t in texts if t.startswith("4.13.1"))
    assert claimed.endswith("in accordance with the Regulations.")  # a wrapped line joins its paragraph
    assert any(t.startswith("4.13.2") for t in texts)
    assert not any("2,987.62" in t for t in texts)  # table rows are facts, not paragraphs
    assert texts[-1].startswith("The Commission directs")
    assert [p["seq"] for p in ps] == list(range(1, len(ps) + 1))


def test_long_paragraph_is_split_and_chunks_stay_within_bounds():
    long = "4.1 " + " ".join(f"Sentence number {i} says the Commission considered the claim." for i in range(120))
    ps = librarian.split_paragraphs(long)
    assert len(ps) > 1 and all(librarian.ntokens(p["text"]) <= librarian.MAX_TOKENS for p in ps)
    chunks = librarian.chunk_page(ps)
    assert all(librarian.ntokens(c["text"]) <= librarian.MAX_TOKENS + 5 for c in chunks)
    assert len({c["paragraph_seq"] for c in chunks}) == len(chunks)  # one chunk per (page, first paragraph)


def test_small_paragraphs_are_joined_up_to_the_minimum():
    ps = [{"seq": i, "kind": "text", "text": "word " * 40} for i in range(1, 11)]
    chunks = librarian.chunk_page(ps)
    assert all(librarian.ntokens(c["text"]) >= librarian.MIN_TOKENS for c in chunks[:-1])
    assert [c["paragraph_seq"] for c in chunks][0] == 1


def test_index_order_never_crosses_pages_and_reports_missing_embeddings(tmp_path, monkeypatch):
    monkeypatch.setenv("ARRNET_STATE", str(tmp_path))
    sha = "a" * 64
    pages = [
        {"page": 1, "text": PAGE, "has_text_layer": True},
        {"page": 2, "text": PAGE, "has_text_layer": True},
        {"page": 3, "text": "", "has_text_layer": False},
    ]
    store.write(sha, "pages", {"order": {}, "pages": pages})
    sink = DryRunSink(tmp_path / "dry")
    s = librarian.index_order({"url": "https://example.org/o.pdf", "sha256": sha}, sink, embed=False)
    chunks = [json.loads(x) for x in (tmp_path / "dry" / "chunks.jsonl").read_text().splitlines()]
    assert s["chunks"] == len(chunks) and {c["page"] for c in chunks} == {1, 2}
    assert all("embedding" not in c for c in chunks)
    run = json.loads((tmp_path / "dry" / "agent_runs.jsonl").read_text().splitlines()[-1])
    assert "without embeddings" in run["note"]
