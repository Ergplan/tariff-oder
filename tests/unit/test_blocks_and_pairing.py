"""Two tables under lettered blocks on one page (NPCL page 384): each table takes its own
block, so the (a) and (b) readings never collide; the two channels pair on the block letter
and the row label however they spell them; a candidate key is spacing- and case-insensitive."""

from __future__ import annotations

from tariff_api.extraction import StructureInput, compare_channels, rules_extract
from tariff_api.grid_integrity import GridInput, analyse_grids
from tariff_api.tariff_schema import Applicability, Candidate, EvidenceRef, ExtractionOutput, block_letter, norm_text

PAGE = """RATE SCHEDULE HV – 1
NON - INDUSTRIAL BULK LOADS
Rate:
(a)    Commercial Loads / Private Institutions / Non - domestic bulk power consumer

with contracted load 75 kW & above and getting supply at Single Point on 11 kV
& above:
Contracted Load Fixed Charge Energy Charge
For supply at 11kV Rs. 430.00 / kVA / month Rs. 8.32 / kVAh
For supply above 11kV Rs. 400.00 / kVA / month Rs. 8.12 / kVAh
(b)    Public Institutions, Registered Societies, Residential Colonies / Townships,
Residential Multi-Storied Buildings with contracted load 75 kW & above and getting supply at Single Point on 11 kV
& above voltage levels:
Contracted Load Fixed Charge Energy Charge
For supply at 11kV Rs. 380.00 / kVA / month Rs. 7.70 / kVAh
For supply above 11kV Rs. 360.00 / kVA / month Rs. 7.50/ kVAh
The body seeking the supply at Single point for bulk loads under this category shall be considered as a deemed franchisee of the Licensee.
"""
HDR = ["Contracted Load", "Fixed Charge", "Energy Charge"]


def _cells():
    g0 = GridInput(
        384,
        0,
        [
            HDR,
            ["For supply at 11kV", "Rs. 430.00 / kVA / month", "Rs. 8.32 / kVAh"],
            ["For supply above 11kV", "Rs. 400.00 / kVA / month", "Rs. 8.12 / kVAh"],
        ],
        1,
    )
    g1 = GridInput(
        384,
        1,
        [
            HDR,
            ["For supply at 11kV", "Rs. 380.00 / kVA / month", "Rs. 7.70 / kVAh"],
            ["For supply above 11kV", "Rs. 360.00 / kVA / month", "Rs. 7.50/ kVAh"],
        ],
        1,
    )
    out = []
    for r in analyse_grids([g0, g1]):
        for c in r.cells:
            d = c.to_dict()
            d["value_state"] = d["normalised"]["value_state"]
            d["region_role"] = "approved_schedule"
            out.append(d)
    return out


def _inp():
    return StructureInput(
        source_sha="a" * 64,
        profile_id="uperc-npcl",
        schedule_heading_kind="rate_schedule",
        region_role="approved_schedule",
        region_ordinal=1,
        page_indices=[384],
        cells=_cells(),
        headings=[
            {"page_index": 384, "kind": "rate_schedule", "code_canonical": "HV-1", "text": "RATE SCHEDULE HV – 1"}
        ],
        page_texts={384: PAGE},
        period="FY2026-27",
        utility="NPCL",
        utilities=["NPCL"],
        category_code_pattern=r"\b(?:LMV|HV)\s*[-–]\s*\d+[A-Z]?\b",
    )


def test_each_table_takes_its_own_lettered_block_and_all_eight_values_survive():
    out = rules_extract(_inp())
    retail = [c for c in out.candidates if c.family == "retail_tariff" and c.category_code == "HV-1"]
    by = {
        (block_letter(c.applicability.rate_block), c.applicability.description, c.component_type): c.value
        for c in retail
    }
    assert (
        by[("(a)", "For supply at 11kV", "fixed")] == "430.00" and by[("(a)", "For supply at 11kV", "energy")] == "8.32"
    )
    assert (
        by[("(b)", "For supply at 11kV", "fixed")] == "380.00"
        and by[("(b)", "For supply above 11kV", "energy")] == "7.50"
    )
    assert len(by) == 8 and len({c.key() for c in retail}) == 8
    blocks = {c.applicability.rate_block for c in retail}
    assert any(
        b.startswith("(a)") and b.endswith("11 kV & above:") for b in blocks
    )  # joined to the colon, blank line skipped
    assert any(b.startswith("(b)") and "voltage levels:" in b for b in blocks)


def _cand(block, description, voltage, value, component="fixed"):
    return Candidate(
        family="retail_tariff",
        category_code="HV-1",
        component_type=component,
        value=value,
        value_state="value",
        original_text=value,
        currency="rupees",
        per_unit="kVA",
        frequency="per_month",
        applicability=Applicability(rate_block=block, description=description, voltage=voltage),
        evidence=[EvidenceRef(page_index=384, kind="cell", row=1, col=1, excerpt=value)],
    )


def test_channels_pair_on_block_letter_and_row_label_however_they_are_spelled():
    rules = ExtractionOutput(
        candidates=[
            _cand("(a) Commercial Loads / Private Institutions … 11 kV & above:", "For supply at 11kV", None, "430.00"),
            _cand("(b) Public Institutions … voltage levels:", "For supply at 11kV", None, "380.00"),
        ]
    )
    model = ExtractionOutput(
        candidates=[
            _cand(
                "(a)",
                "Commercial Loads / Private Institutions / Non - domestic bulk power consumer …",
                "For supply at 11kV",
                "430.00",
            ),
            _cand("(b)", "Public Institutions, Registered Societies …", "For supply at 11kV", "390.00"),
        ]
    )
    cmp = {block_letter(c.primary.applicability.rate_block): c for c in compare_channels(rules, model)}
    assert cmp["(a)"].agreement == "agree" and cmp["(a)"].structure.value == "430.00"
    assert cmp["(b)"].agreement == "disagree" and cmp["(b)"].disagreeing_fields == ["value"]
    assert all(c.structure is not None for c in cmp.values())  # the rules' record is the primary
    # the model's block (c) that the rules did not read stays one_missing
    model.candidates.append(_cand("(c)", "Something else", "For supply at 11kV", "1.00"))
    assert [c.agreement for c in compare_channels(rules, model) if c.structure is None] == ["one_missing"]


def test_key_is_spacing_and_case_insensitive_and_uses_the_block_letter():
    a = _cand("(a) Commercial Loads", "For supply at 11kV", None, "1")
    b = _cand("(A)", "for  supply at 11 kV", None, "2")
    assert a.key() == b.key()
    assert norm_text("At 11 kV") == "at 11kv" and block_letter("(iv) Something") == "(iv)" and block_letter(None) == ""
    assert (
        block_letter("Consumers getting supply as per Rural Schedule")
        == "consumers getting supply as per rural schedule"
    )
