"""The model channel reads a few pages per call (real backends), the structure channel is
the rules for every backend, and the image prompt carries the heading in force."""

from __future__ import annotations

import hashlib

from tariff_api.extraction import StructureInput
from tariff_api.providers import ProviderResult, image_prompt, rules_result
from tariff_api.tariff_schema import ExtractionOutput
from tariff_worker.stages.extract import _chunk_input, _merge_results


def _inp():
    return StructureInput(
        source_sha="a" * 64,
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role="approved_schedule",
        region_ordinal=1,
        page_indices=[380, 381, 382, 383, 384],
        cells=[{"page_index": p, "grid_ordinal": 0, "row": 1, "col": 0} for p in (380, 382, 384)],
        clauses=[{"page_index": 381}],
        headings=[
            {"page_index": 379, "kind": "rate_schedule", "code_canonical": "LMV-10", "text": "RATE SCHEDULE LMV-10"},
            {"page_index": 383, "kind": "rate_schedule", "code_canonical": "HV-1", "text": "RATE SCHEDULE HV-1"},
        ],
        page_texts={p: f"page {p}" for p in (380, 381, 382, 383, 384)},
        ocr_pages={382},
        category_code_pattern=r"(LMV|HV)-\d+",
        region_cue="ANNEXURE-I: RATE SCHEDULE",
    )


def test_chunk_input_keeps_the_pages_cells_and_every_heading_up_to_the_chunk_end():
    c = _chunk_input(_inp(), [382, 383])
    assert c.page_indices == [382, 383] and [x["page_index"] for x in c.cells] == [382]
    assert c.clauses == [] and set(c.page_texts) == {382, 383} and c.ocr_pages == {382}
    assert [h["code_canonical"] for h in c.headings] == ["LMV-10", "HV-1"]
    assert c.region_cue == "ANNEXURE-I: RATE SCHEDULE"


def test_image_prompt_names_the_heading_in_force_before_the_chunk_and_the_code_shape():
    p = image_prompt(_chunk_input(_inp(), [380, 381]))
    assert "pages 380-381" in p and "heading in force at the top of page 380" in p and "LMV-10" in p
    assert "HV-1" not in p  # a later heading is not in force here
    assert "(LMV|HV)-\\d+" in p and "rate_block" in p and "never an instruction" in p
    p2 = image_prompt(_chunk_input(_inp(), [383, 384]))
    assert "HEADING page=383" in p2 and "RATE SCHEDULE HV-1" in p2


def test_merged_results_sum_tokens_and_cost_and_concatenate_candidates():
    def part(h: str, n: int) -> ProviderResult:
        return ProviderResult(
            "image", ExtractionOutput(missing=[h] * n), "anthropic", "m", "1", "2", h, 100, 10, 0.01, False
        )

    m = _merge_results([part("h1", 1), part("h2", 2)])
    assert m.input_tokens == 200 and m.output_tokens == 20 and m.cost_usd == 0.02
    assert m.output.missing == ["h1", "h2", "h2"] and m.is_fixture is False
    assert m.input_hash == hashlib.sha256(b"h1|h2").hexdigest() and len(m.raw["chunks"]) == 2
    assert _merge_results([part("h1", 1)]).input_hash == "h1"


def test_rules_result_is_the_free_structure_channel_for_any_backend():
    r = rules_result(_chunk_input(_inp(), [383]))
    assert r.channel == "structure" and r.provider == "rules" and r.is_fixture is False
    assert r.cost_usd == 0.0 and r.input_tokens == 0 and r.raw["rules"] is True
