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
    for commission in ("SYNTHERC", "UPERC"):
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
