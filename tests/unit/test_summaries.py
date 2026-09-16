"""Category summaries: the fixture template reads the candidates back, the grounding check
lets no number through that the pages or candidates do not carry, and a lettered rate block
above a table becomes the applicability of every cell under it."""

from __future__ import annotations

from tariff_api import extraction, summaries
from tariff_api.tariff_schema import Applicability, Candidate, EvidenceRef


def _cand(value, comp, block=None, desc=None, unit="kVAh"):
    return Candidate(
        family="retail_tariff",
        category_code="HV-1",
        component_type=comp,
        value=value,
        value_state="value",
        original_text=f"Rs. {value} / {unit}",
        currency="rupees",
        per_unit=unit,
        applicability=Applicability(rate_block=block, description=desc),
        evidence=[
            EvidenceRef(page_index=384, kind="cell", grid_ordinal=1, row=1, col=2, excerpt=f"Rs. {value} / {unit}")
        ],
    )


PAGE = """RATE SCHEDULE HV-1 NON-INDUSTRIAL BULK LOADS
3. RATE:
Rate is the demand and energy charges at which the consumer shall be billed during
the billing period applicable to the category:
(a) Commercial Loads / Private Institutions / Non - domestic bulk power consumer
with contracted load 75 kW & above and getting supply at Single Point on 11 kV
& above:
Contracted Load Fixed Charge Energy Charge
For supply at 11kV Rs. 430.00 / kVA / month Rs. 8.32 / kVAh
For supply above 11kV Rs. 400.00 / kVA / month Rs. 8.12 / kVAh
(b) Public Institutions, Registered Societies, Residential Colonies / Townships,
with contracted load 75 kW & above and getting supply at Single Point on 11 kV
& above voltage levels:
Contracted Load Fixed Charge Energy Charge
For supply at 11kV Rs. 380.00 / kVA / month Rs. 7.70 / kVAh
For supply above 11kV Rs. 360.00 / kVA / month Rs. 7.50/ kVAh
"""


def test_template_summary_reads_candidates_back_by_rate_block_and_is_grounded():
    a = "(a) Commercial Loads / Private Institutions / Non - domestic bulk power consumer with contracted load 75 kW & above:"
    b = "(b) Public Institutions, Registered Societies, Residential Colonies / Townships:"
    cands = [
        _cand("430.00", "fixed", a, "For supply at 11kV", "kVA"),
        _cand("8.32", "energy", a, "For supply at 11kV"),
        _cand("380.00", "fixed", b, "For supply at 11kV", "kVA"),
        _cand("7.70", "energy", b, "For supply at 11kV"),
    ]
    inp = summaries.SummaryInput("sha", "HV-1", "NON-INDUSTRIAL BULK LOADS", [384], {384: PAGE}, cands)
    text = summaries.template_summary(inp)
    assert text.startswith("HV-1 — NON-INDUSTRIAL BULK LOADS.")
    assert "(a) Commercial Loads" in text and "(b) Public Institutions" in text
    assert "fixed Rs 430.00 per kVA (For supply at 11kV)" in text and "energy Rs 7.70 per kVAh" in text
    grounded, unsupported = summaries.grounding_check(text, inp)
    assert grounded and unsupported == []


def test_grounding_check_lists_numbers_the_pages_do_not_carry():
    inp = summaries.SummaryInput("sha", "HV-1", None, [384], {384: PAGE}, [_cand("7.70", "energy")])
    grounded, unsupported = summaries.grounding_check(
        "Energy charge Rs 7.70 per kVAh; fixed charge Rs 999.00 per kVA per month.", inp
    )
    assert not grounded and unsupported == ["999.00"]
    grounded, _ = summaries.grounding_check("Fixed Rs 380.00, energy Rs 7.70; contracted load 75 kW and above.", inp)
    assert grounded  # 380.00 and 75 are on the page even though only 7.70 is a candidate


def test_lettered_rate_block_above_a_table_becomes_applicability():
    inp = extraction.StructureInput(
        source_sha="sha",
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role="approved_schedule",
        region_ordinal=1,
        page_indices=[384],
        page_texts={384: PAGE},
    )
    # the second table's 11 kV row: its block is (b), not (a)
    cell = {"page_index": 384, "row_path": ["For supply at 11kV"], "raw": "Rs. 7.70 / kVAh"}
    # the anchor line appears twice on the page; the block is decided per occurrence, so the
    # helper is exercised on a text that holds only the second table
    second = PAGE[PAGE.index("(b)") :]
    inp.page_texts = {384: PAGE[: PAGE.index("(a)")] + second}
    block = extraction._rate_block_for(inp, cell)
    assert block.startswith("(b) Public Institutions") and block.endswith("voltage levels:")
    inp.page_texts = {384: PAGE}
    assert extraction._rate_block_for(inp, cell).startswith("(a) Commercial Loads")


def test_category_pages_span_from_heading_to_next_heading():
    headings = [
        {"kind": "rate_schedule", "code_canonical": "HV-1", "page_index": 383, "line_no": 1, "text": "HV-1"},
        {"kind": "rate_schedule", "code_canonical": "HV-2", "page_index": 386, "line_no": 1, "text": "HV-2"},
        {"kind": "table_caption", "code_canonical": "9-1", "page_index": 384, "line_no": 3, "text": "x"},
    ]
    spans = summaries.category_pages(headings, "rate_schedule", list(range(380, 391)))
    assert spans["HV-1"] == ("HV-1", [383, 384, 385, 386]) and spans["HV-2"] == ("HV-2", [386, 387, 388, 389, 390])
