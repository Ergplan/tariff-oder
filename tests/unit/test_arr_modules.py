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
