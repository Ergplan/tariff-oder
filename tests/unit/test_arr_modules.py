"""Unit tests of the ARR read/formulate/file modules (ADR-0018): chapter headings, the grid
reader's refusals, identities flag-never-correct, blocked-parameter propagation and
reproducibility, the filing's untraced-number refusal, and the mapping gate."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from tariff_api.arr import filing as fl
from tariff_api.arr import formulate as fm
from tariff_api.arr.chapters import looks_like_heading, propose_chapters
from tariff_api.arr.extract import GridIn, fiscal_year, parse_value, read_grids
from tariff_api.arr.identities import Value, evaluate
from tariff_api.arr.schema import ArrCandidate, to_canonical, unit_from_text
from tariff_api.arr.taxonomy import Placer, load_mapping, load_taxonomy

TAX = load_taxonomy()
SYN = load_mapping("SYNTHERC")


def test_headings_open_chapters_and_body_text_does_not():
    assert looks_like_heading("4. AGGREGATE REVENUE REQUIREMENT")
    assert looks_like_heading("Chapter 5: Power Purchase")
    assert not looks_like_heading("4. The Commission has examined the power purchase cost claimed.")
    assert not looks_like_heading("The aggregate revenue requirement approved is shown below")
    lines = {
        1: ["SYNTHETIC COMMISSION"],
        2: ["3. ENERGY SALES AND LOSSES", "energy sales are discussed below"],
        3: ["4. AGGREGATE REVENUE REQUIREMENT"],
        4: ["4.2 Expenditure"],  # same branch as the previous heading: merged
        5: ["5. REVENUE GAP"],
    }
    ch = propose_chapters(lines, SYN, page_count=9)
    assert [(c.branch, c.page_start, c.page_end) for c in ch] == [("E", 2, 3), ("C", 3, 5), ("R", 5, 9)]


def test_values_years_and_units_are_read_as_printed():
    assert parse_value("1,234.50") == ("value", "1234.50")
    assert parse_value("(12.5)") == ("value", "-12.5")
    assert parse_value("-") == ("absent_in_source", None)
    assert parse_value("Nil") == ("zero", "0")
    assert parse_value("see note") == ("unknown", None)
    assert fiscal_year("FY 2025-26 Approved") == "FY2025-26"
    assert fiscal_year("2025-2026") == "FY2025-26"
    assert fiscal_year("2025-27") is None  # not one financial year
    assert fiscal_year("FY 2024-25 vs FY 2025-26") is None  # two years: the column is not guessed
    assert unit_from_text("(Rs. Crore)") == "INR_crore" and unit_from_text("in Rs lakh") == "INR_lakh"
    assert to_canonical("250", "INR_lakh", TAX.unit_conversions) == ("2.5", "INR_crore", "INR_lakh->INR_crore x0.01")


def _grid(rows, caption=("Table: ARR (Rs. Crore)",)):
    return GridIn(page_index=3, ordinal=0, rows=rows, header_rows=1, caption=list(caption))


def test_reader_places_rows_and_reports_what_it_cannot():
    placer = Placer(TAX, SYN, "distribution")
    rows = [
        ["S. No.", "Particulars", "FY 2025-26 Petition", "FY 2025-26 Approved", "FY 2025-26 Remarks"],
        ["1", "O&M Expenses", "640.00", "600.00", "x"],
        ["2", "Interest on Loan", "160.00", "-", ""],  # placed by the commission's own alias
        ["3", "Miscellaneous receipts of the year", "5.00", "4.00", ""],  # not an ARR line we know
    ]
    out, rep = read_grids([_grid(rows)], taxonomy=TAX, mapping=SYN, placer=placer, source_id="S", utility="U")
    keys = {(c.line_code, c.value_type): c for c in out.candidates}
    assert keys[("C.OM", "approved")].stated_value == "600.00" and keys[("C.OM", "approved")].stated_unit == "INR_crore"
    assert keys[("C.INT.LOAN", "approved")].value_state == "absent_in_source"
    assert [u["label"] for u in rep.unplaced] == ["Miscellaneous receipts of the year"]
    # a year with no voice word is reported, never assumed (the caption's "Crore" is no "RE")
    assert [(c["col"], c["reason"]) for c in rep.columns_skipped] == [(4, "no voice word")]
    ev = keys[("C.OM", "petitioned")].evidence[0]
    assert (ev.page_index, ev.row, ev.col, ev.excerpt) == (3, 1, 2, "640.00")
    # without a printed unit, money is not assumed to be crore
    out, _ = read_grids(
        [_grid(rows[:2], caption=())], taxonomy=TAX, mapping=SYN, placer=placer, source_id="S", utility="U"
    )
    assert out.candidates[0].stated_unit is None and "stated_unit" in out.candidates[0].missing


def test_a_column_without_a_voice_is_reported_not_assumed():
    placer = Placer(TAX, SYN, "distribution")
    rows = [["Particulars", "FY 2025-26"], ["O&M Expenses", "600.00"]]
    out, rep = read_grids([_grid(rows)], taxonomy=TAX, mapping=SYN, placer=placer, source_id="S", utility="U")
    assert out.candidates == [] and rep.columns_skipped[0]["reason"] == "no voice word"


def _v(code: str, value: str, unit: str = "INR_crore") -> Value:
    return Value(code, Decimal(value), unit, f"ref:{code}")


def test_identities_flag_and_never_correct():
    vals = [
        _v("C.PP", "5000"),
        _v("C.OM", "600"),
        _v("C.RETURN.ROE", "300"),  # rolled up into C.RETURN
        _v("C.TOTAL", "5920"),  # components give 5900
        _v("L.NTI", "100"),
        _v("R.ARR", "5820"),
        _v("R.REV.EXISTING", "5600"),
        _v("R.GAP", "220"),
        _v("E.SALES", "9000", "MU"),
        _v("E.LOSS.DIST_PCT", "10", "percent"),
        _v("E.INPUT.DIST", "10000", "MU"),
    ]
    out = evaluate(vals, taxonomy=TAX, mapping=SYN, group={"fiscal_year": "FY2025-26", "value_type": "approved"})
    assert [(f.identity_id, f.expected, f.printed) for f in out] == [("ARR-I1", "5900", "5920")]
    assert "C.RETURN.ROE" in out[0].lines
    assert vals[3].value == Decimal("5920")  # the printed value is left as printed


def _plan(**over) -> fm.Plan:
    lines = [
        fm.PlanLine(line_code="C.OM", formula="escalate", params={"rate_pct": "param.om"}, unit="INR_crore"),
        fm.PlanLine(line_code="C.DEP", formula="carry_forward", unit="INR_crore"),
        fm.PlanLine(line_code="C.TOTAL", formula="sum", inputs={"of": ["C.OM", "C.DEP"]}, unit="INR_crore"),
    ]
    return fm.Plan(
        id="test-plan",
        version=1,
        commission="T",
        status="synthetic",
        base_rule=fm.BaseRule(prefer=["final_true_up", "approved"]),
        lines=over.get("lines", lines),
    )


def _base() -> dict[str, fm.BaseFact]:
    facts = [
        fm.BaseFact("f1", "C.OM", "FY2025-26", "approved", Decimal("600.00"), "INR_crore", "s1"),
        fm.BaseFact("f2", "C.OM", "FY2025-26", "final_true_up", Decimal("610.00"), "INR_crore", "s2"),
        fm.BaseFact("f3", "C.DEP", "FY2025-26", "approved", Decimal("200.00"), "INR_crore", "s1"),
    ]
    return fm.select_base(facts, fm.BaseRule(prefer=["final_true_up", "approved"]), "FY2025-26")


def test_base_rule_prefers_the_true_up_and_a_missing_parameter_blocks_downstream():
    base = _base()
    assert base["C.OM"].fact_id == "f2"
    lines = fm.compute(_plan(), base_fy="FY2025-26", last_fy="FY2026-27", base=base, assumptions=[])
    st = {(r.line_code, r.status): r.blocked_reason for r in lines}
    assert st[("C.OM", "blocked")] == "parameter missing: param.om for FY2026-27"
    assert st[("C.TOTAL", "blocked")] == "input blocked: C.OM FY2026-27"
    assert ("C.DEP", "computed") in st


def test_compute_is_exact_and_reproducible_across_years():
    a = [fm.AssumptionIn("a1", "param.om", "", Decimal("5"), "percent", "user", None)]
    kw = dict(base_fy="FY2025-26", last_fy="FY2027-28", base=_base(), assumptions=a)
    one, two = fm.compute(_plan(), **kw), fm.compute(_plan(), **kw)
    assert [(r.line_code, r.fiscal_year, r.value) for r in one] == [(r.line_code, r.fiscal_year, r.value) for r in two]
    om = {r.fiscal_year: r.value for r in one if r.line_code == "C.OM"}
    assert om == {"FY2026-27": Decimal("640.50"), "FY2027-28": Decimal("672.53")}  # 610 x 1.05, then x 1.05
    h1 = fm.input_hash(
        plan=_plan(), base_fy="FY2025-26", targets=[{"fiscal_year": "FY2027-28"}], base=_base(), assumptions=a
    )
    a2 = [fm.AssumptionIn("a1", "param.om", "", Decimal("5.5"), "percent", "user", None)]
    h2 = fm.input_hash(
        plan=_plan(), base_fy="FY2025-26", targets=[{"fiscal_year": "FY2027-28"}], base=_base(), assumptions=a2
    )
    assert h1 != h2


def _ctx() -> fl.DraftContext:
    return fl.DraftContext(
        utility_code="U",
        utility_name="U",
        formulation_id="f",
        formulation_name="n",
        base_fy="FY2025-26",
        targets=["FY2026-27"],
        projections={
            ("C.OM", "FY2026-27"): fl.ProjectionRef(
                "C.OM", "FY2026-27", "computed", "630.00", "INR_crore", "escalate", "escalated", None, None, {}
            ),
            ("C.TX", "FY2026-27"): fl.ProjectionRef(
                "C.TX",
                "FY2026-27",
                "blocked",
                None,
                "INR_crore",
                "escalate",
                "escalated",
                "parameter missing: x",
                None,
                {},
            ),
        },
        facts={},
        assumptions={},
        formula_words={"C.OM": "escalated"},
        labels={},
        is_fixture=True,
    )


def test_filing_numbers_only_through_placeholders():
    trace = fl.Trace()
    text, ids = fl.resolve("O&M for {fy:T0} is {proj:C.OM:T0}.", _ctx(), trace, "p1")
    assert text == "O&M for FY2026-27 is 630.00 Rs crore." and ids == ["T0001"]
    text, ids = fl.resolve("Transmission is {proj:C.TX:T0}.", _ctx(), trace, "p2")
    assert text == "Transmission is [blocked: parameter missing: x]." and ids == []
    with pytest.raises(fl.FilingError, match="literal number"):
        fl.resolve("Other expenses of Rs 125 crore are claimed.", _ctx(), trace, "p3")
    with pytest.raises(fl.FilingError, match="no projection"):
        fl.resolve("{proj:C.DEP:T0}", _ctx(), trace, "p4")
    with pytest.raises(fl.FilingError, match="no assumption"):
        fl.resolve("{assumption:param.none:T0}", _ctx(), trace, "p5")


def test_arr_candidate_rules():
    ev = [{"page_index": 1, "kind": "cell", "excerpt": "1"}]
    base = dict(
        line_code="C.OM",
        fiscal_year="FY2025-26",
        value_type="approved",
        as_of_order="s",
        value_state="value",
        original_text="O&M",
        evidence=ev,
    )
    with pytest.raises(ValueError):
        ArrCandidate(**{**base, "fiscal_year": "2025-26"})
    with pytest.raises(ValueError, match="reasoning_quote"):
        ArrCandidate(**base, reason_category="normative")
    assert ArrCandidate(**base).key().startswith("arr||C.OM|FY2025-26|approved|s")


def test_real_arr_approval_waits_for_a_confirmed_mapping():
    from tariff_api.services.review import arr_mapping_confirmed

    def src(code):
        return SimpleNamespace(utility=SimpleNamespace(commission=SimpleNamespace(code=code)))

    ok, why = arr_mapping_confirmed(None, src("UPERC"))
    assert not ok and "not confirmed" in why
    assert arr_mapping_confirmed(None, src("SYNTHERC"))[0]
    assert not arr_mapping_confirmed(None, SimpleNamespace(utility=None))[0]


def test_shipped_plans_and_templates_load_and_name_known_codes():
    codes = TAX.by_code()
    for commission in ("SYNTHERC", "UPERC", "GENERIC"):
        plan = fm.load_plan(commission)
        for pl in plan.lines:
            assert pl.line_code in codes, pl.line_code
            for v in pl.inputs.values():
                for c in [v] if isinstance(v, str) else v:
                    assert c in codes, c
        t = fl.load_template(commission)
        for fmt in t.formats:
            assert all(r in codes for r in fmt.rows)
    assert fm.load_plan("UPERC").status.startswith("skeleton") and fl.load_template("UPERC").status == "skeleton"


def test_live_arr_channel_shapes_validates_and_never_trusts_the_model_on_identity(monkeypatch):
    """The Anthropic ARR channel with the HTTP call mocked: pages go in chunks, each
    candidate is validated one by one, the order and licensee are set by code, the canonical
    value is recomputed from the printed one, cost comes from the configured prices."""
    import httpx

    from tariff_api.arr import provider as pv

    calls = []

    def fake_post(url, headers, json, timeout):  # noqa: A002
        calls.append(json)
        tool_input = {
            "candidates": [
                {
                    "line_code": "C.OM",
                    "fiscal_year": "FY2025-26",
                    "value_type": "approved",
                    "as_of_order": "the model guessed this",
                    "utility": "SOMEONE-ELSE",
                    "value_state": "value",
                    "stated_value": "1,234.50",
                    "stated_unit": "INR_lakh",
                    "canonical_value": "999",  # the model's arithmetic is ignored
                    "original_text": "O&M Expenses",
                    "evidence": [{"page_index": 3, "excerpt": "1,234.50"}],
                },
                {"line_code": "C.OM", "fiscal_year": "2025-26", "value_type": "approved", "value_state": "value"},
            ],
            "missing": ["row 'Misc' fits no code"],
        }
        body = {
            "id": f"msg_{len(calls)}",
            "stop_reason": "tool_use",
            "content": [{"type": "tool_use", "name": "return_arr_candidates", "input": tool_input}],
            "usage": {"input_tokens": 1000, "output_tokens": 200},
        }
        return httpx.Response(200, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    with pytest.raises(pv.ArrChannelUnavailable):
        pv.AnthropicArrImageChannel("", "m", 3.0, 15.0)
    ch = pv.AnthropicArrImageChannel("k", "claude-test", 3.0, 15.0)
    ctx = {
        "pages": list(range(1, 9)),
        "source_id": "SRC",
        "utility": "NPCL",
        "commission": "UPERC",
        "voices": ["approved"],
        "line_items": [("C.OM", "O&M")],
        "conversions": TAX.unit_conversions,
    }
    res = ch.read_chapter(pv.ArrExtractionOutput(), [b"img"] * 8, ctx)
    assert len(calls) == 2  # 8 pages in chunks of 6
    assert "IGNORE" not in calls[0]["system"] and "document data" in calls[0]["system"]
    assert calls[0]["tool_choice"] == {"type": "tool", "name": "return_arr_candidates"}
    c = res.output.candidates[0]
    assert (c.as_of_order, c.utility, c.stated_value) == ("SRC", "NPCL", "1234.50")
    assert (c.canonical_value, c.canonical_unit) == ("12.345", "INR_crore")
    assert len(res.output.candidates) == 2 and len(res.raw["rejected"]) == 2  # one bad row per call
    assert res.input_tokens == 2000 and res.cost_usd == round(2000 / 1e6 * 3 + 400 / 1e6 * 15, 6)
    assert not res.is_fixture and "row 'Misc' fits no code" in res.output.missing


def test_discovery_proposes_entries_from_a_listing_page_and_says_what_it_guessed():
    from tariff_api.library import propose_from_html

    page = """
    <table>
      <tr><td><a href="/Orders/NPCL_TO.pdf">Tariff Order of NPCL for FY 2025-26</a></td></tr>
      <tr><td><a href='docs/tu.PDF'>True-up order of PVVNL for FY 2023-24</a></td></tr>
      <tr><td><a href="https://x.example/myt.pdf">MYT Petition filed by KESCO for Control Period FY 2025-26 to FY 2029-30</a></td></tr>
      <tr><td><a href="/regs/2025.pdf">UPERC (Multi Year Distribution Tariff) Regulations, 2025</a></td></tr>
      <tr><td><a href="/all.pdf">Order on ARR of all DISCOMs &amp; licensees FY 2026-27</a></td></tr>
      <tr><td><a href="/Orders/NPCL_TO.pdf">duplicate link</a> <a href="/page.aspx">not a PDF</a></td></tr>
    </table>"""
    lic = {"NPCL": ["Noida Power Company Ltd"], "PVVNL": [], "KESCO": ["Kanpur Electricity Supply Company"]}
    props = {p["title"][:20]: p for p in propose_from_html(page, "https://www.uperc.org/list.aspx", licensees=lic)}
    assert len(props) == 5
    to = props["Tariff Order of NPCL"]
    assert (to["url"], to["document_kind"], to["fiscal_year"], to["utility_code"], to["complete"]) == (
        "https://www.uperc.org/Orders/NPCL_TO.pdf",
        "tariff_order",
        "FY2025-26",
        "NPCL",
        True,
    )
    assert props["True-up order of PVV"]["document_kind"] == "arr_true_up_order"
    assert props["True-up order of PVV"]["url"] == "https://www.uperc.org/docs/tu.PDF"
    myt = props["MYT Petition filed b"]
    assert (myt["document_kind"], myt["fiscal_year"], myt["utility_code"]) == ("myt_petition", "", "KESCO")
    assert props["UPERC (Multi Year Di"]["document_kind"] == "regulation"
    alld = props["Order on ARR of all "]
    assert alld["utility_code"] is None and "no licensee named" in alld["notes"] and not alld["complete"]


def test_discovery_reads_short_year_titles():
    """ "Tariff Order for FY 26" (HPERC, others) is the financial year ending in March 2026
    (increment 46); a bare two-digit number is never a year."""
    from tariff_api.library import expand_short_years, propose_from_html

    assert (
        expand_short_years("ARR and Tariff Order for FY26 of HPSEBL") == "ARR and Tariff Order for FY 2025-26 of HPSEBL"
    )
    assert expand_short_years("Order dated 26 March, page 26") == "Order dated 26 March, page 26"
    page = '<a href="/o.pdf">Tariff Order of HPSEBL for FY 27</a>'
    (p,) = propose_from_html(page, "https://hperc.org/", licensees={"HPSEBL": []})
    assert (p["document_kind"], p["fiscal_year"], p["utility_code"], p["complete"]) == (
        "tariff_order",
        "FY2026-27",
        "HPSEBL",
        True,
    )


def test_every_state_falls_back_to_the_generic_skeletons_and_stays_gated():
    """A commission with no mapping, plan or template of its own reads and formulates with the
    generic skeletons; real lines read with the generic mapping cannot be approved."""
    from tariff_api.services.review import arr_mapping_confirmed

    with pytest.raises(FileNotFoundError):
        load_mapping("MERC")  # strict by default: the API's mapping endpoint says "not found"
    assert load_mapping("MERC", fallback=True).id == "generic-arr"
    assert fm.load_plan("MERC").id == "generic-plan" and fm.load_plan("UPERC").id == "uperc-plan"
    assert fm.load_plan_id("generic-plan").status.startswith("skeleton")
    assert fl.load_template("MERC").id == "generic-petition"
    src = SimpleNamespace(utility=SimpleNamespace(commission=SimpleNamespace(code="MERC")))
    ok, why = arr_mapping_confirmed(None, src)
    assert not ok and "generic" in why.lower() or "not confirmed" in why


def test_chapters_of_a_long_order_follow_its_numbered_sections():
    """Patterns found in a real 423-page ARR order (increment 37), reproduced in SYNTHETIC text:
    a contents page with dotted leaders, a running header on every page of a part, table
    captions, table rows, numbered paragraphs, list items numbered out of sequence, and a
    top-level part heading without a cue.  Only the numbered sections open chapters, each
    ends at the next section or part, and the running header names the part."""
    mapping = load_mapping("NOSUCH", fallback=True)  # the generic skeleton's cues
    part1, part2 = "TRUING-UP OF FY 2024-25", "AGGREGATE REVENUE REQUIREMENT OF FY 2026-27"
    pages: dict[int, list[str]] = {
        1: [
            "CONTENTS",
            "4.4. POWER PURCHASE ........................ 3",
            "TABLE 4-1 ENERGY SALES ......... 3",
            "6.6. OPERATION AND MAINTENANCE EXPENSES ......... 9",
            "6.9. INTEREST CHARGES ............ 10",
        ],
        2: ["4. TRUE UP OF FY 2024-25", "4.1. The Petitioner has submitted the true-up of the year below."],
    }
    for p in range(3, 8):
        pages[p] = [part1, "Page text", f"Page {p} of 13"]
    pages[3] += [
        "4.4. POWER PURCHASE",
        "TABLE 4-25 MEDIUM TERM POWER PURCHASE COST FOR TPTCL",
        "4.4.12. Accordingly, the total cost of long-term power purchase claimed by the Petitioner is",
        "1        Sales (MU)                                 3.53  Included in",
    ]
    pages[5] += ["5.1    Interest on Bank deposits", "3.   Interest on Security Deposit with Exchange"]
    pages[6] += ["4.8. FIXED ASSET AND DEPRECIATION", "17.06.2026   GFA"]
    pages[8] = ["6. DETERMINATION FOR FY 2026-27"]
    for p in range(9, 14):
        pages[p] = [part2, "Page text", f"Page {p} of 13"]
    pages[9] += ["6.6. OPERATION AND MAINTENANCE EXPENSES", "TRANSMISSION CHARGES"]
    pages[10] += [
        "6.9. INTEREST ON WORKING CAPITAL",
        "d.  safeguarding consumers' interest and at the same time, recovery of",
    ]
    chs = propose_chapters(pages, mapping, 13)
    got = [(c.branch, c.cue_text.split()[0], c.page_start, c.page_end) for c in chs]
    branches = {ch.branch for ch in mapping.chapter_map}
    assert {"C.PP", "C.DEP", "C.OM", "C.INT"} <= branches
    assert got == [
        ("C.PP", "4.4.", 3, 6),
        ("C.DEP", "4.8.", 6, 8),  # ends at the next part's heading, which has no cue of its own
        ("C.OM", "6.6.", 9, 10),
        ("C.INT", "6.9.", 10, 13),
    ], got
    assert chs[0].note and part1 in chs[0].note and part2 in chs[2].note
    assert not [c for c in chs if "of 13" in (c.note or "")]  # a page-number footer is not a part
    assert not looks_like_heading("17.06.2026   GFA") and not looks_like_heading("TABLE 4-25 MEDIUM TERM POWER")
    assert not looks_like_heading("4.4.12. Accordingly, the total cost of long-term power purchase claimed by the")
    assert looks_like_heading("6.6. Operation and Maintenance Expenses")


def test_real_order_table_layouts_are_read():
    """Table layouts of a real ARR order (increment 38) in SYNTHETIC figures: the year only in
    the caption, the voice from the part, an earlier order's approval, reference and unit
    columns beside the label, a second header row, footnote marks, a percentage in a label."""
    from tariff_api.arr.extract import label_unit, voice_in_context

    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    placer = Placer(tax, mapping, "distribution")

    def read(grid: GridIn, part: str | None):
        out, rep = read_grids(
            [grid], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="SYN", part=part
        )
        return {(c.line_code, c.fiscal_year, c.value_type): c.stated_value for c in out.candidates}, rep

    summary = GridIn(
        9,
        0,
        [
            ["S. No.", "Particulars", "Ref.", "Units", "Claimed", "Approved"],
            ["1", "Power Purchase Expenses", "A", "Rs. Cr.", "2,448.33", "2,477.36*"],
            ["2", "Depreciation", "B", "Rs. Cr.", "106.75", "103.80"],
            ["3", "Energy Sales", "C", "MU", "4,399.84", "4,399.84"],
        ],
        1,
        ["TABLE 6-81 SUMMARY OF ARR AS APPROVED BY THE COMMISSION FOR FY 2026-27 (IN RS. CR.)"],
    )
    got, _ = read(summary, "AGGREGATE REVENUE REQUIREMENT OF FY 2026-27")
    assert got[("C.PP", "FY2026-27", "petitioned")] == "2448.33"
    assert got[("C.PP", "FY2026-27", "approved")] == "2477.36"  # the footnote mark is not part of it
    assert got[("E.SALES", "FY2026-27", "approved")] == "4399.84"  # the units column gives MU

    trued = GridIn(
        4,
        0,
        [
            ["Sl. No.", "Particulars", "Approved in TO dated 10.10.2024", "Claimed", "Approved"],
            ["1", "Depreciation", "70.00", "75.00", "72.00"],
        ],
        1,
        ["TABLE 4-100 DEPRECIATION APPROVED BY THE COMMISSION FOR FY 2024-25 (IN RS. CR.)"],
    )
    got, _ = read(trued, "TRUING-UP OF FY 2024-25")
    assert got == {
        ("C.DEP", "FY2024-25", "approved"): "70.00",  # the earlier order's approval
        ("C.DEP", "FY2024-25", "petitioned"): "75.00",
        ("C.DEP", "FY2024-25", "final_true_up"): "72.00",  # an approval inside the true-up
    }
    got, _ = read(trued, "ANNUAL PERFORMANCE REVIEW OF FY 2024-25")
    assert got[("C.DEP", "FY2024-25", "provisional_true_up")] == "72.00"

    two_rows = GridIn(
        8,
        0,
        [
            ["Particulars", "FY 2024-25 (True-Up)", "", "FY 2025-26 (APR)", ""],
            ["", "Claimed", "Approved", "Claimed", "Computed"],
            ["Depreciation", "75.00", "72.00", "80.00", "78.00"],
        ],
        1,
        ["TABLE 8-3: CUMULATIVE GAP / (SURPLUS) (IN RS. CR.)"],
    )
    got, rep = read(two_rows, None)
    assert got[("C.DEP", "FY2024-25", "final_true_up")] == "72.00"
    assert got[("C.DEP", "FY2025-26", "petitioned")] == "80.00"
    assert got[("C.DEP", "FY2025-26", "provisional_true_up")] == "78.00"  # "(APR)" over "Computed"
    assert not rep.columns_skipped

    assert (
        voice_in_context("Approved as per TO dtd 22.11.2025", "", "ANNUAL PERFORMANCE REVIEW OF FY 2025-26", mapping)
        == "approved"
    )
    assert label_unit("Maintenance spares @ 40% of the R&M Expenses") is None
    assert label_unit("Distribution Loss (%)") == "percent" and label_unit("ACoS (Rs./kWh)") == "INR_per_kWh"


def test_the_arr_totals_are_placed_only_in_summary_context():
    """A "Total Cost" row of one power source's table (a power-purchase chapter) is not total
    expenditure: reported unplaced with the reason.  In a table titled as the ARR summary, the
    same words are (increment 40, found on a real order by identity ARR-I1)."""
    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    placer = Placer(tax, mapping, "distribution")
    rows = [["Particulars", "Claimed", "Approved"], ["Total Cost", "539.30", "534.52"]]
    source = GridIn(5, 0, rows, 1, ["TABLE 4-26 MEDIUM TERM POWER PURCHASE COST FOR FY 2024-25 (IN RS. CR.)"])
    out, rep = read_grids(
        [source], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="SYN", branch="C.PP"
    )
    assert out.candidates == [] and "not the ARR's C.TOTAL" in rep.unplaced[0]["reason"]
    summary = GridIn(9, 0, rows, 1, ["TABLE 6-81 SUMMARY OF ARR AS APPROVED BY THE COMMISSION FOR FY 2026-27"])
    out, _ = read_grids(
        [summary], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="SYN", branch="C.PP"
    )
    assert {c.line_code for c in out.candidates} == {"C.TOTAL"}


def test_short_year_forms_and_amount_columns():
    """HPERC's layouts (increment 42): "FY27" in a title is FY2026-27; a lone "Amount" column
    takes its voice and year from the title; a bare two-digit number is never a year."""
    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    placer = Placer(tax, mapping, "distribution")
    assert fiscal_year("ARR approved by the Commission for FY27 (Rs. Cr.)") == "FY2026-27"
    assert fiscal_year("Table 26 of 2024") is None and fiscal_year("FY26 and FY27") is None
    grid = GridIn(
        188,
        0,
        [["Particulars", "Amount (Rs. Cr.)"], ["Depreciation", "70.10"]],
        1,
        ["Table 53: Petitioner Submission - Depreciation for FY24 (Rs. Cr.)"],
    )
    out, _ = read_grids([grid], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="SYN")
    assert [(c.line_code, c.fiscal_year, c.value_type, c.stated_value) for c in out.candidates] == [
        ("C.DEP", "FY2023-24", "petitioned", "70.10")
    ]


def test_a_row_whose_unit_contradicts_the_line_is_not_placed():
    """A money row is never an energy line (increment 42, found on HPERC: "Cost of electricity
    purchase including own generation" in a Rs crore table matched an MU line's words)."""
    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    placer = Placer(tax, mapping, "distribution")
    grid = GridIn(
        9,
        0,
        [
            ["Particulars", "Petition", "Approved"],
            ["Energy Sales", "4,399.84", "4,399.84"],
            ["Depreciation", "106.75", "103.80"],
        ],
        1,
        ["Table 244: ARR approved by the Commission for FY27 (Rs. Cr.)"],
    )
    out, rep = read_grids([grid], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="SYN")
    assert {c.line_code for c in out.candidates} == {"C.DEP"}
    assert any("printed in INR_crore, but E.SALES is in MU" in u.get("reason", "") for u in rep.unplaced)


def test_an_order_whose_numbers_mark_paragraphs_is_read_by_its_headings():
    """JSERC's layout (increment 43): every paragraph numbered "5.13", sections under Title Case
    headings inside "Chapter N:" parts.  Numbered prose is no heading; the chapters follow the
    Title Case headings, each in its part; a hearing part is flagged."""
    mapping = load_mapping("NOSUCH", fallback=True)
    pages = {
        1: ["Chapter 4: PUBLIC CONSULTATION", "Power Purchase Cost", "4.12 The Petitioner has stated that the cost of"],
        2: ["Chapter 5: TRUE-UP FOR FY 2024-25", "Energy Sales", "5.13 Based on the information provided above, the"],
        3: ["5.14 Accordingly, the Commission approves the energy sales as", "Power Purchase Cost"],
        4: ["5.40 The Petitioner has claimed the power purchase cost of", "Depreciation"],
        5: [
            "5.81 The Petitioner has claimed depreciation of Rs. 450.33 Crore",
            "5.82 The Commission has considered the",
        ],
        6: ["Chapter 6: ANNUAL PERFORMANCE REVIEW FOR FY 2025-26", "Depreciation"],
    }
    chs = propose_chapters(pages, mapping, 6)
    got = [(c.branch, c.cue_text, c.page_start, c.page_end) for c in chs]
    assert got == [
        ("C.PP", "Power Purchase Cost", 1, 1),
        ("E", "Energy Sales", 2, 3),
        ("C.PP", "Power Purchase Cost", 3, 4),
        ("C.DEP", "Depreciation", 4, 5),  # ends where Chapter 6 begins
        ("C.DEP", "Depreciation", 6, 6),
    ], got
    assert "Chapter 5" in (chs[1].note or "") and "Chapter 6" in (chs[4].note or "")
    assert "likely not the Commission's decisions" in (chs[0].note or "")
    assert not looks_like_heading("5.13 Based on the information provided above, the")
    # a chapter title wraps its year onto the next line; its continuation is part of it
    from tariff_api.arr.chapters import chapter_title

    assert (
        chapter_title(["Chapter 5: TRUE-UP FOR FY", "2024-25", "Energy Sales"], 0)
        == "Chapter 5: TRUE-UP FOR FY 2024-25"
    )
    assert chapter_title(["Chapter 5:", "TRUE-UP FOR FY 2024-25", "5.1 The Petitioner has"], 0) == (
        "Chapter 5: TRUE-UP FOR FY 2024-25"
    )
    assert chapter_title(["Chapter 9: REVENUE GAP", "Treatment of Revenue Gap"], 0) == "Chapter 9: REVENUE GAP"
    assert chapter_title(["Chapter 9:", "REVENUE GAP", "299"], 0) == "Chapter 9: REVENUE GAP"


def test_a_label_naming_what_a_line_is_for_is_not_that_line():
    """JSERC's energy balance (increment 43): "Total Energy Available for Sales" contains
    "sales" and "Energy Input Directly to State Transmission System" contains "energy input",
    yet neither is the line; a taxonomy line's ``not_when`` phrases refuse such matches."""
    placer = Placer(load_taxonomy(), load_mapping("NOSUCH", fallback=True), "distribution")

    def code(label: str) -> str | None:
        p = placer.place(label, "MU")
        return p.code if p else None

    assert code("Total Energy Available for Sales (MU)") != "E.SALES"
    assert code("Energy Input Directly to State Transmission System (MU)") != "E.INPUT.DIST"
    assert code("Direct Input Energy from State Solar System (MUs)") != "E.INPUT.DIST"
    assert code("Energy Required for distribution (MU)") == "E.INPUT.DIST"
    assert code("Total energy sold (MU)") == "E.SALES"
    assert code("Energy Sales") == "E.SALES"
    assert code("Energy input at DISCOM periphery") == "E.INPUT.DIST"
    # the previous year's gap carried into this ARR is not this year's gap (UERC, increment 48)
    assert placer.place("Gap/(Surplus) of previous year", "INR_crore") is None
    assert placer.place("Adjusted Revenue (Surplus)/Gap", "INR_crore").code == "R.GAP"


def test_a_cost_row_named_like_a_quantity_follows_the_table_unit_and_number_agrees():
    """ "Power Purchase Expense" in a crore table is the cost, in an MU table the quantity;
    a multi-word alias matches its singular and plural (increment 43, JSERC's summary)."""
    placer = Placer(load_taxonomy(), load_mapping("NOSUCH", fallback=True), "distribution")

    def code(label: str, unit: str) -> str | None:
        p = placer.place(label, unit)
        return p.code if p else None

    assert code("Power Purchase Expense", "INR_crore") == "C.PP"
    assert code("Power Purchase", "MU") == "E.PP.QTY"
    assert code("Employee Expense", "INR_crore") == "C.OM.EMPLOYEE"
    assert code("Interest on Long Term Loan", "INR_crore") == "C.INT.LOAN"
    assert code("Operations and Maintenance Expenses", "INR_crore") == "C.OM"
    assert code("Sale of surplus power", "INR_crore") != "E.SALES"
    assert not placer.collisions()


def test_a_total_printed_inclusive_of_other_lines_is_a_convention_question():
    """ARR-I1 when power purchase is printed inclusive of transmission (JSERC, increment 44):
    with no convention stated the finding stays blocking and names the reconciliation; with the
    mapping's ``total_includes`` the included lines are counted once and it passes."""
    from tariff_api.arr.taxonomy import TotalIncludes

    vals = [
        Value("C.TOTAL", Decimal("100"), "INR_crore", "p.1"),
        Value("C.PP", Decimal("80"), "INR_crore", "p.1"),  # includes the 10 of transmission
        Value("C.TX", Decimal("10"), "INR_crore", "p.1"),
        Value("C.OM", Decimal("20"), "INR_crore", "p.1"),
    ]
    group = {"fiscal_year": "FY2024-25", "value_type": "approved"}
    (f,) = [x for x in evaluate(vals, taxonomy=TAX, mapping=SYN, group=group) if x.identity_id == "ARR-I1"]
    assert f.severity == "blocking"
    assert f.detail["reconciles_if"] == {
        "total": "C.PP",
        "includes": ["C.TX"],
        "why": "power purchase printed inclusive of transmission charges",
    }
    assert "reconciles if C.PP includes C.TX" in f.message
    stated = SYN.model_copy(update={"total_includes": [TotalIncludes(total="C.PP", includes=["C.TX"])]})
    assert not [x for x in evaluate(vals, taxonomy=TAX, mapping=stated, group=group) if x.identity_id == "ARR-I1"]
    # a failure no known convention explains carries no hint
    off = [*vals[:1], Value("C.PP", Decimal("50"), "INR_crore", "p.1"), *vals[2:]]
    (g,) = [x for x in evaluate(off, taxonomy=TAX, mapping=SYN, group=group) if x.identity_id == "ARR-I1"]
    assert "reconciles_if" not in g.detail


def test_the_loss_basis_is_a_convention_question():
    """BERC's energy balance (increment 45): the loss grosses up the sales within the state
    (retail sales less inter-state sales to Nepal).  The rows are placed apart; with no
    convention stated ARR-I4 stays blocking and names it; with ``loss_basis`` it passes."""
    placer = Placer(TAX, load_mapping("NOSUCH", fallback=True), "distribution")

    def code(label: str) -> str | None:
        p = placer.place(label, "MU")
        return p.code if p else None

    assert code("Energy sales (retail sales only)") == "E.SALES"
    assert code("Less: Inter-state sales (Nepal)") == "E.SALES.INTERSTATE"
    # a bare inter-state sale is ambiguous (HPSEBL's is surplus power sold to other states)
    assert code("Inter State Sale(MU)") != "E.SALES.INTERSTATE"
    # the sales within the state are no inter-state sales (and, as NPCL prints its retail sales
    # this way, they stay a reading of the sales: the first printed sales value is the one used)
    assert code("Energy sales excluding Inter-state sales") == "E.SALES"

    vals = [
        Value("E.SALES", Decimal("16993.71"), "MU", "p.141"),
        Value("E.SALES.INTERSTATE", Decimal("196.49"), "MU", "p.141"),
        Value("E.LOSS.DIST_PCT", Decimal("11.46"), "percent", "p.141"),
        Value("E.INPUT.DIST", Decimal("18971.33"), "MU", "p.141"),
    ]
    group = {"fiscal_year": "FY2024-25", "value_type": "actual"}
    (f,) = [x for x in evaluate(vals, taxonomy=TAX, mapping=SYN, group=group) if x.identity_id == "ARR-I4"]
    assert f.severity == "blocking" and f.detail["reconciles_if"]["loss_basis"] == "sales_within_state"
    stated = SYN.model_copy(update={"loss_basis": SYN.loss_basis.model_copy(update={"value": "sales_within_state"})})
    assert not [x for x in evaluate(vals, taxonomy=TAX, mapping=stated, group=group) if x.identity_id == "ARR-I4"]


def test_discovery_titles_icon_links_by_their_column_group_and_listing_groups():
    """MPERC (increment 46): icon links under a two-level header — "Tariff Order" and "True Up
    Order" groups — take their group's name and the row's period; a listing for a group of
    licensees proposes each; a file name of words tells an MYT order whose row says nothing."""
    from tariff_api.library import guess_kind, propose_from_html

    page = """<table>
      <tr><th colspan="7">Distribution Tariff Orders</th></tr>
      <tr><th rowspan="2">Period</th><th colspan="3">Tariff Order</th><th colspan="3">True Up Order</th></tr>
      <tr><th>Date of Order</th><th>Label</th><th>Download</th><th>Date of Order</th><th colspan="2">Download</th></tr>
      <tr><td>FY-2024-25</td><td>06/03/2024</td><td>Tariff order 2024-25</td>
          <td><a href="/u/ARR_Order_2024-25.pdf"><img src="i.png"></a></td>
          <td>25/03/2026</td><td colspan="2"><a href="/u/TU 2024 25.pdf"><img src="i.png"></a></td></tr>
      <tr><td>FY-2022-23</td><td>31/03/2022</td><td>English</td>
          <td><a href="/u/DISCOM-MYT-Order-FY-2022-23-to-FY-2026-27.pdf"></a></td><td></td><td colspan="2"></td></tr>
    </table>"""
    group = ["MPPKVVCL", "MPMKVVCL"]
    props = propose_from_html(
        page, "https://mperc.in/page/x", licensees={c: [] for c in group}, default_group=group, since="FY2024-25"
    )
    got = {(p["url"].rsplit("/", 1)[-1], p["document_kind"], p["fiscal_year"], p["utility_code"]) for p in props}
    assert got == {
        ("ARR_Order_2024-25.pdf", "tariff_order", "FY2024-25", "MPPKVVCL"),
        ("ARR_Order_2024-25.pdf", "tariff_order", "FY2024-25", "MPMKVVCL"),
        ("TU%202024%2025.pdf", "arr_true_up_order", "FY2024-25", "MPPKVVCL"),  # spaces encoded
        ("TU%202024%2025.pdf", "arr_true_up_order", "FY2024-25", "MPMKVVCL"),
        ("DISCOM-MYT-Order-FY-2022-23-to-FY-2026-27.pdf", "myt_order", "", "MPPKVVCL"),
        ("DISCOM-MYT-Order-FY-2022-23-to-FY-2026-27.pdf", "myt_order", "", "MPMKVVCL"),
    }, got
    tu = next(p for p in props if "TU" in p["url"])
    assert tu["title"].startswith("True Up Order FY-2024-25")
    # what is listed beside orders and is not one (UERC)
    for title in (
        "Salient features of Tariff Orders for FY 2024-25. 1. UPCL",
        "Admittance Order in the matter of UPCL's Petition for True up of FY 2022-23",
        "Order in the matter of Petition for review of the Commission's Order dated 28.03.2024",
        "Interim Order on the ARR petition of UPCL",
    ):
        assert guess_kind(title)[0] is None, title
    assert guess_kind("Tariff Orders for FY 2025-26. 1. UPCL")[0] == "tariff_order"


def test_lettered_parts_structure_a_paragraph_numbered_order():
    """OERC (increment 47): parts lettered "A." to "I." in capitals, paragraphs numbered "45.",
    sections under Title Case headings; the proposal and hearing parts are flagged; a table's
    lone "A." row is not a part."""
    from tariff_api.arr.chapters import lettered_parts

    mapping = load_mapping("NOSUCH", fallback=True)

    def prose(n: int) -> str:  # distinct sentences (a line on every page is a running header)
        topic = {2: "notice", 3: "hearing", 21: "sales", 72: "objection", 73: "reply", 178: "forecast"}.get(n, "staff")
        return f"{n}. The Commission has examined the {topic} submission of the licensees in detail."

    pages = {
        1: ["A.   PROCEDURAL HISTORY (PARA 2 TO 20)", prose(2), prose(3)],
        2: [
            "B.   ARR & RETAIL SUPPLY TARIFF PROPOSAL OF THE DISCOMs FOR FY",
            "2026-27",
            "Energy Sales",
            prose(21),
        ],
        3: ["C.   OBJECTIONS RAISED DURING THE HEARING", prose(72), prose(73)],
        4: ["D.   OBSERVATIONS AND DIRECTIONS OF THE COMMISSION", "Energy Sales", prose(178)],
        5: ["Employee Expenses", prose(300), prose(301).replace("staff", "wages")],
    }
    chs = propose_chapters(pages, mapping, 5)
    got = [(c.branch, c.cue_text, c.page_start) for c in chs]
    assert got == [("E", "Energy Sales", 2), ("E", "Energy Sales", 4), ("C.OM", "Employee Expenses", 5)], got
    assert "likely not the Commission's decisions" in (chs[0].note or "")
    assert "D. OBSERVATIONS AND DIRECTIONS" in (chs[1].note or "") and "likely not" not in (chs[1].note or "")
    assert lettered_parts([(3, (1,), None, "A. ENERGY REQUIREMENT")]) == []


def test_a_combined_order_naming_the_licensee_per_row_is_attributed_per_row():
    """OERC's tables (increment 47), SYNTHETIC figures: a "DISCOM" column carried down its
    blank cells, and a licensee's name alone on a row above its block; a total row belongs to
    no licensee and is never attributed."""
    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    placer = Placer(tax, mapping, "distribution")
    lic = {"NORTHCO": ["North Company"], "SOUTHCO": ["South Company"]}

    def read(grid: GridIn) -> dict:
        out, _ = read_grids(
            [grid], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="NORTHCO", licensees=lic
        )
        return {(c.utility, c.line_code, c.value_type): c.stated_value for c in out.candidates}

    by_column = GridIn(
        101,
        1,
        [
            ["DISCOM", "Description", "Proposed by the DISCOM", "Approved by the Commission"],
            ["NORTHCO", "Total Sales", "1,240.50", "1,240.00"],
            ["", "Power Purchase", "1,500.00", "1,480.00"],
            ["SOUTHCO", "Total Sales", "800.00", "790.00"],
            ["All State", "Total Sales", "2,040.50", "2,030.00"],
        ],
        1,
        ["Table-37 Quantum of Power Purchase and Sales approved for FY 2026-27 (MU)"],
    )
    got = read(by_column)
    assert got[("NORTHCO", "E.SALES", "approved")] == "1240.00"
    assert got[("NORTHCO", "E.PP.QTY", "petitioned")] == "1500.00"
    assert got[("SOUTHCO", "E.SALES", "approved")] == "790.00"
    assert not [k for k in got if k[0] not in lic]  # the state total is no licensee's
    assert len([k for k in got if k[1] == "E.SALES"]) == 4

    by_heading = GridIn(
        100,
        1,
        [
            ["Description", "Proposed by licensees for FY 2026-27", "Approved by the Commission for FY 2026-27"],
            ["NORTHCO", "", ""],
            ["Distribution Loss", "15.15%", "14.00%"],
            ["SOUTHCO", "", ""],
            ["Distribution Loss", "20.00%", "18.50%"],
        ],
        1,
        ["Table-36 Losses Proposed by the Licensees and Approved by the Commission"],
    )
    got = read(by_heading)
    assert got[("NORTHCO", "E.LOSS.DIST_PCT", "approved")] == "14.00"
    assert got[("SOUTHCO", "E.LOSS.DIST_PCT", "approved")] == "18.50"


def test_a_long_chapter_is_split_at_its_three_level_sections():
    """UERC (increment 47): the true-up part's sections are numbered in three levels ("3.1.3
    Power Purchase Expenses") under "3. … Conclusion on Truing Up for FY 2024-25"; a chapter of
    40 pages or more is split at them, each noting its part (so its year reaches the reader)."""
    from tariff_api.arr.chapters import part_from_note

    mapping = load_mapping("NOSUCH", fallback=True)
    pages: dict[int, list[str]] = {
        p: [f"Paragraph text of page {p} about the matter {p * 7} in hand."] for p in range(1, 61)
    }
    pages[1] = ["2.4  Distribution Loss", *pages[1]]
    pages[3] = ["2.9  Return on Equity", *pages[3]]
    pages[30] = [
        "3. Petitioner’s Submissions, Commission’s Analysis, Scrutiny and",
        "Conclusion on Truing Up for FY 2024-25",
        "3.1.3  Power Purchase Expenses",
        *pages[30],
    ]
    pages[40] = ["3.1.4  Operation and Maintenance (O&M) Expenses", *pages[40]]
    pages[50] = ["3.2.7  Return on Equity", *pages[50]]
    pages[59] = ["4.2  Sales", *pages[59]]
    chs = propose_chapters(pages, mapping, 60)
    got = [(c.branch, c.page_start, c.page_end) for c in chs]
    assert got == [
        ("E", 1, 3),
        ("C.RETURN", 3, 30),  # the 57-page chapter, now ending where its first section begins
        ("C.PP", 30, 40),
        ("C.OM", 40, 50),
        ("C.RETURN", 50, 59),
        ("E", 59, 60),
    ], got
    assert part_from_note(chs[2].note) == (
        "3. Petitioner’s Submissions, Commission’s Analysis, Scrutiny and Conclusion on Truing Up for FY 2024-25"
    )


def test_a_licensee_column_keeps_its_own_voice_and_a_label_names_what_precedes_its_qualifier():
    """MPERC's ARR summary (increment 47), SYNTHETIC figures: "East DISCOM" over "Claimed |
    Admitted" — each licensee's column takes its voice from its own header, never the caption's;
    "Power Purchase Cost including Inter-State Transmission Charges" is the power purchase."""
    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    placer = Placer(tax, mapping, "distribution")
    lic = {"EASTCO": ["East DISCOM"], "WESTCO": ["West DISCOM"]}
    grid = GridIn(
        15,
        0,
        [
            ["Particulars", "East DISCOM", "", "West DISCOM", "", "State", ""],
            ["", "Claimed", "Admitted", "Claimed", "Admitted", "Claimed", "Admitted"],
            [
                "Power Purchase Cost including Inter-State Transmission Charges",
                "110.25",
                "108.55",
                "198.87",
                "176.47",
                "309.12",
                "285.02",
            ],
            ["Depreciation", "4.48", "3.99", "3.44", "1.84", "7.92", "5.83"],
        ],
        1,
        ["Table 3: Aggregate Revenue Requirement admitted by the Commission for FY 2026-27 (Rs. Crore)"],
    )
    out, _ = read_grids(
        [grid], taxonomy=tax, mapping=mapping, placer=placer, source_id="s", utility="EASTCO", licensees=lic
    )
    got = {(c.utility, c.line_code, c.value_type): c.stated_value for c in out.candidates}
    assert got[("EASTCO", "C.PP", "petitioned")] == "110.25"
    assert got[("EASTCO", "C.PP", "approved")] == "108.55"
    assert got[("WESTCO", "C.DEP", "approved")] == "1.84"
    assert not [k for k in got if k[1].startswith("C.TX")]  # the qualifier is not the line
    assert not [k for k in got if k[0] not in lic]  # the State columns are a total


def test_sub_rows_are_read_with_their_heading_row():
    """MPERC's ARR summary (increment 48), SYNTHETIC figures: "Interest & Finance Charges" with
    no values, then "On Project Loans", "On Working Capital Loans", "On Consumer Security
    Deposit"; each sub-row is the heading's interest of that kind, and the total reconciles."""
    tax = load_taxonomy()
    mapping = load_mapping("NOSUCH", fallback=True)
    grid = GridIn(
        15,
        0,
        [
            ["Particulars", "Claimed", "Admitted"],
            ["Power Purchase Cost", "100.00", "90.00"],
            ["Interest & Finance Charges", "", ""],
            ["On Project Loans", "3.43", "3.58"],
            ["On Working Capital Loans", "0.45", "0.71"],
            ["On Consumer Security Deposit", "1.16", "1.08"],
            ["Return on Equity", "3.13", "2.90"],
            ["Total Expenses", "108.17", "98.27"],
        ],
        1,
        ["Table 3: Aggregate Revenue Requirement for FY 2026-27 (Rs. Crore)"],
    )
    out, _ = read_grids(
        [grid], taxonomy=tax, mapping=mapping, placer=Placer(tax, mapping, "distribution"), source_id="s", utility="SYN"
    )
    got = {(c.line_code, c.value_type): c.stated_value for c in out.candidates if c.stated_value}
    assert got[("C.INT.LOAN", "petitioned")] == "3.43"
    assert got[("C.INT.WC", "approved")] == "0.71"
    assert got[("C.INT.CSD", "approved")] == "1.08"
    vals = [
        Value(c.line_code, Decimal(c.canonical_value), c.canonical_unit, "p.15")
        for c in out.candidates
        if c.value_type == "approved" and c.canonical_value is not None
    ]
    group = {"fiscal_year": "FY2026-27", "value_type": "approved"}
    assert not [f for f in evaluate(vals, taxonomy=tax, mapping=mapping, group=group) if f.identity_id == "ARR-I1"]


def test_a_list_of_chapters_on_one_page_is_not_a_structure_and_proposal_headings_stay_flagged():
    """UERC lists its seven chapters in prose on one page; that is not a structure of parts
    (increment 50).  OERC FY2025-26 numbers the paragraph-headings of its proposal summary
    (part B) and heads its decisions (part D here) in Title Case: both are read, part B flagged."""
    from tariff_api.arr.chapters import propose_chapters

    mapping = load_mapping("NOSUCH", fallback=True)

    def prose(n: int, w: str) -> str:
        return f"{n}. The Commission has examined the {w} submission of the licensees in detail."

    listed = {
        1: [
            "Chapter 1 - Background and Procedural History.",
            "Chapter 2 - Stakeholders’ Objections.",
            "Chapter 3 - Analysis.",
        ],
        2: ["2.4  Distribution Loss", prose(1, "loss")],
        3: ["2.6  Power Procurement Cost", prose(2, "power")],
    }
    got = [(c.branch, c.page_start) for c in propose_chapters(listed, mapping, 3)]
    assert got == [("E", 2), ("C.PP", 3)], got  # numbered sections, not paragraphs inside one list

    words = [
        "notice",
        "hearing",
        "sales",
        "purchase",
        "staff",
        "wages",
        "loans",
        "equity",
        "income",
        "assets",
        "meters",
    ]
    pages = {
        1: ["A.   PROCEDURAL HISTORY", prose(2, words[0]), prose(3, words[1])],
        2: ["B.   ARR PROPOSAL OF THE DISCOMs FOR THE FY 2025-26", "22.   Energy Sales", prose(23, words[2])],
        3: ["31.   Power Purchase Expenses", prose(32, words[3]), "37.    Depreciation", prose(38, words[4])],
        4: ["39.   Return on Equity", prose(40, words[5]), "41.    Non-Tariff Income", prose(42, words[6])],
        5: ["C.   OBJECTIONS RAISED DURING THE HEARING", prose(72, words[7]), prose(73, words[8])],
        6: ["D.   OBSERVATIONS AND DIRECTIONS OF THE COMMISSION", "Energy Sales", prose(178, words[9])],
        7: ["Employee Expenses", prose(300, words[10]), prose(301, "audit")],
    }
    # an order numbers many more paragraphs than headings: three more sentences on each page
    for pg in pages:
        pages[pg] += [prose(50 + pg * 3 + k, f"matter {chr(97 + pg)}{chr(97 + k)}") for k in range(3)]
    chs = propose_chapters(pages, mapping, 7)
    decided = [(c.branch, c.page_start) for c in chs if "likely not" not in (c.note or "")]
    assert decided == [("E", 6), ("C.OM", 7)], [(c.branch, c.page_start, c.note) for c in chs]
    assert any(c.cue_text.startswith("22.") and "likely not" in (c.note or "") for c in chs)
