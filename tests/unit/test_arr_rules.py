"""The rule engine (ADR-0021; R-RULE-1..4, R-NUM-1..4).  SYNTHETIC rules except the last two
tests, which check the real UPERC drafts in packages/arr-rules and their worked examples."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from tariff_api.arr.rules import Q, Rule, RuleError, RuleSet, check_all, load_rules, parse

ROOT_SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def rule(id, output, unit, formula, inputs, **kw) -> Rule:  # noqa: A002
    return Rule.model_validate(
        {
            "id": id,
            "version": 1,
            "title": id,
            "output": output,
            "unit": unit,
            "formula": formula,
            "inputs": inputs,
            "clause": {"regulation": "Synthetic Regulations, 2030"},
            "applies": {"commission": "SYNTHERC", **kw.pop("applies", {})},
            **kw,
        }
    )


def test_units_convert_exactly_and_refuse_wrong_dimensions():
    assert Q.of("1", "INR_crore").to("INR_lakh") == Decimal(100)
    assert Q.of("15", "percent").to("fraction") == Decimal("0.15")
    with pytest.raises(RuleError, match="cannot be expressed"):
        Q.of("1", "MU").to("INR_crore")


@pytest.mark.parametrize(
    "bad", ["__import__('os')", "a.b", "a[0]", "a if b else c", "a ** 2", "a < b", "open(a)", "avg(x=a)"]
)
def test_the_language_is_arithmetic_only(bad):
    with pytest.raises(RuleError):
        parse(bad)


def test_acos_needs_no_hand_written_factor():
    # Rs crore / MU in Rs/kWh: the units carry the 10
    r = rule(
        "acos",
        "acos",
        "INR_per_kWh",
        "arr / sales",
        {"arr": {"unit": "INR_crore", "source": "fact:R.ARR"}, "sales": {"unit": "MU", "source": "fact:E.SALES"}},
    )
    ev = RuleSet([r]).evaluate("FY2030-31", {"fact:R.ARR": ("3481.83", "INR_crore"), "fact:E.SALES": ("4399.84", "MU")})
    assert ev.results["acos"].rounded == Decimal("7.91")


def test_adding_money_to_energy_is_refused_at_load():
    bad = rule(
        "bad",
        "x",
        "INR_crore",
        "a + b",
        {"a": {"unit": "INR_crore", "source": "record:a"}, "b": {"unit": "MU", "source": "record:b"}},
    )
    with pytest.raises(RuleError, match="cannot add"):
        RuleSet([bad])


def test_literals_are_decimal_not_float():
    r = rule(
        "third",
        "x",
        "INR_crore",
        "a * 0.1 + a * 0.2",
        {"a": {"unit": "INR_crore", "source": "record:a"}},
        rounding={"places": 20},
    )
    ev = RuleSet([r]).evaluate("FY2030-31", {"record:a": ("1", "INR_crore")})
    assert ev.results["x"].value == Decimal("0.3")  # 0.30000000000000004 in binary float


def test_dependency_order_cycles_and_missing_producers():
    a = rule(
        "a",
        "a",
        "INR_crore",
        "b + x",
        {"b": {"unit": "INR_crore", "source": "rule:b"}, "x": {"unit": "INR_crore", "source": "record:x"}},
    )
    b = rule("b", "b", "INR_crore", "y * 2", {"y": {"unit": "INR_crore", "source": "record:y"}})
    assert RuleSet([a, b]).order == ["b", "a"]
    c = rule("b", "b", "INR_crore", "a2 * 2", {"a2": {"unit": "INR_crore", "source": "rule:a"}})
    with pytest.raises(RuleError, match="cycle"):
        RuleSet([a, c])
    with pytest.raises(RuleError, match="no rule produces"):
        RuleSet([a])


def test_a_missing_input_blocks_and_never_defaults():
    a = rule(
        "a",
        "a",
        "INR_crore",
        "b + x",
        {"b": {"unit": "INR_crore", "source": "rule:b"}, "x": {"unit": "INR_crore", "source": "record:x"}},
    )
    b = rule("b", "b", "INR_crore", "y * 2", {"y": {"unit": "INR_crore", "source": "record:y"}})
    ev = RuleSet([a, b]).evaluate("FY2030-31", {"record:x": ("1", "INR_crore")})
    assert ev.blocked == {"b": "input y (record:y) has no value", "a": "needs b, which is blocked"}
    assert not ev.results and not ev.filing_ready


def test_rules_are_chosen_per_year_and_overlaps_refused():
    old = rule(
        "old", "r", "INR_crore", "x", {"x": {"unit": "INR_crore", "source": "record:x"}}, applies={"to_fy": "FY2024-25"}
    )
    new = rule(
        "new",
        "r",
        "INR_crore",
        "x * 2",
        {"x": {"unit": "INR_crore", "source": "record:x"}},
        applies={"from_fy": "FY2025-26"},
    )
    vals = {"record:x": ("10", "INR_crore")}
    assert RuleSet([old, new], "FY2024-25").evaluate("FY2024-25", vals).results["r"].rounded == Decimal("10.00")
    assert RuleSet([old, new], "FY2026-27").evaluate("FY2026-27", vals).results["r"].rounded == Decimal("20.00")
    both = rule("both", "r", "INR_crore", "x", {"x": {"unit": "INR_crore", "source": "record:x"}})
    with pytest.raises(RuleError, match="several rules apply"):
        RuleSet([old, both], "FY2024-25")


def test_rounding_policy_and_what_feeds_dependants():
    half = rule(
        "h",
        "h",
        "INR_crore",
        "x / 2",
        {"x": {"unit": "INR_crore", "source": "record:x"}},
        rounding={"places": 0, "feeds": "rounded"},
    )
    dbl = rule("d", "d", "INR_crore", "h * 2", {"h": {"unit": "INR_crore", "source": "rule:h"}}, rounding={"places": 2})
    ev = RuleSet([half, dbl]).evaluate("FY2030-31", {"record:x": ("5", "INR_crore")})
    assert ev.results["h"].rounded == Decimal("3")  # half-up: 2.5 → 3
    assert ev.results["d"].rounded == Decimal("6.00")  # fed the rounded 3, as the rule says


def test_filing_ready_needs_approved_rules_on_verified_clauses():
    r = rule("a", "a", "INR_crore", "x", {"x": {"unit": "INR_crore", "source": "record:x"}})
    ev = RuleSet([r]).evaluate("FY2030-31", {"record:x": ("1", "INR_crore")})
    assert not ev.filing_ready  # a draft on an unverified clause
    ok = rule(
        "a",
        "a",
        "INR_crore",
        "x",
        {"x": {"unit": "INR_crore", "source": "record:x"}},
        status="approved",
        approved_by="reviewer@example.com",
        approved_at="2030-01-01",
        clause={"regulation": "Synthetic Regulations, 2030", "clause": "5.1", "verified": True},
    )
    assert RuleSet([ok]).evaluate("FY2030-31", {"record:x": ("1", "INR_crore")}).filing_ready


def test_the_uperc_drafts_check_and_their_examples_pass():
    assert check_all("UPERC") == []
    rules = load_rules("UPERC")
    assert rules and all(r.status == "draft" and not r.clause.verified for r in rules)  # nothing approved by the build


def test_the_npcl_chain_reproduces_the_filed_formats_from_records():
    """FY2026-27, from the openings and the year's capital records only (F14: capitalisation,
    consumer contribution, assets retired): the chain — 70:30 split, retirement, roll-forwards —
    reproduces NPCL's filed return on equity (F26) and interest on the normative loan (F25)."""
    rs = RuleSet(load_rules("UPERC"), "FY2026-27")
    ev = rs.evaluate(
        "FY2026-27",
        {
            "prior:equity_closing": ("709.6218015004636", "INR_crore"),
            "prior:normative_loan_closing": ("757.768934543932", "INR_crore"),
            # the year's capital records (F14 column FY2026-27): additions and reductions follow
            "record:capitalisation": ("493.69077628216064", "INR_crore"),
            "record:consumer_contribution": ("64.28609536119946", "INR_crore"),
            "record:retired_gross": ("15", "INR_crore"),
            "record:retired_grants": ("0", "INR_crore"),
            "record:retired_acc_dep": ("8.319944985254537", "INR_crore"),
            "record:retired_acc_dep_adjustment": ("0", "INR_crore"),
            "record:depreciation": ("106.75180844074569", "INR_crore"),
            "assumption:loan_interest_rate": ("0.0982616438356164", "fraction"),
        },
    )
    chain = {
        "equity_closing",
        "equity_average",
        "return_on_equity",
        "normative_loan_closing",
        "normative_loan_average",
        "interest_on_loan",
    }
    assert chain <= set(ev.results) and not chain & set(ev.blocked)
    # the year's other rules (the energy balance) are blocked for want of their inputs, and say so
    assert ev.blocked["dist_loss_mu"] == "input sales (fact:E.SALES) has no value"
    assert ev.results["return_on_equity"].rounded == Decimal("115.77")
    assert ev.results["interest_on_loan"].rounded == Decimal("83.88")
    assert not ev.filing_ready  # drafts


def test_rules_per_category_sum_and_block_honestly():
    per = rule(
        "dep",
        "dep",
        "INR_crore",
        "avg_gfa * rate",
        {
            "avg_gfa": {"unit": "INR_crore", "source": "record:avg"},
            "rate": {"unit": "fraction", "source": "record:rate"},
        },
        per="asset_class",
    )
    total = rule("total", "total", "INR_crore", "parts", {"parts": {"unit": "INR_crore", "source": "sum:dep"}})
    rs = RuleSet([per, total])
    cats = {
        "Lines": {"record:avg": ("100", "INR_crore"), "record:rate": ("0.0528", "fraction")},
        "Vehicles": {"record:avg": ("10", "INR_crore"), "record:rate": ("0.095", "fraction")},
    }
    ev = rs.evaluate("FY2030-31", {}, cats)
    assert ev.by_category["Lines"]["dep"].rounded == Decimal("5.28") and ev.results["total"].rounded == Decimal("6.23")
    del cats["Vehicles"]["record:rate"]
    ev = rs.evaluate("FY2030-31", {}, cats)
    assert "total" in ev.blocked and "Vehicles" in ev.blocked["total"]  # one class missing blocks the sum, by name
    with pytest.raises(RuleError, match="not computed per category"):
        RuleSet([rule("s", "s", "INR_crore", "x", {"x": {"unit": "INR_crore", "source": "sum:total"}}), total, per])
    with pytest.raises(RuleError, match="sum it"):
        RuleSet([per, rule("t", "t", "INR_crore", "x", {"x": {"unit": "INR_crore", "source": "rule:dep"}})])


def test_division_by_zero_blocks_the_output_and_never_prints_zero():
    r = rule(
        "rate",
        "rate",
        "INR_per_kWh",
        "amount / mu",
        {"amount": {"unit": "INR_crore", "source": "record:a"}, "mu": {"unit": "MU", "source": "record:m"}},
    )
    ev = RuleSet([r]).evaluate("FY2030-31", {"record:a": ("5", "INR_crore"), "record:m": ("0", "MU")})
    assert ev.blocked == {"rate": "division by zero"} and not ev.results


def test_a_category_can_be_given_and_is_labelled_so():
    """A filed figure can stand in for one category's computation (F24 types the projection years'
    depreciation by class): labelled "given", it feeds the sum like a computed one."""
    per = rule(
        "dep",
        "dep",
        "INR_crore",
        "avg_gfa * rate",
        {
            "avg_gfa": {"unit": "INR_crore", "source": "record:avg"},
            "rate": {"unit": "fraction", "source": "record:rate"},
        },
        per="asset_class",
    )
    total = rule("total", "total", "INR_crore", "parts", {"parts": {"unit": "INR_crore", "source": "sum:dep"}})
    cats = {
        "Lines": {"record:avg": ("100", "INR_crore"), "record:rate": ("0.0528", "fraction")},
        "Vehicles": {"rule:dep": ("0.9", "INR_crore")},  # no rate needed: given
    }
    ev = RuleSet([per, total]).evaluate("FY2030-31", {}, cats)
    assert ev.by_category["Vehicles"]["dep"].status == "given"
    assert ev.by_category["Lines"]["dep"].status != "given"
    assert ev.results["total"].value == Decimal("6.18")


def test_clause_candidates_propose_pages_and_never_verify(tmp_path):
    """A regulation's pages ranked for a rule: the page printing the rule's words and its value
    first; a page with the value but none of the words is never proposed.  The CLI writes
    proposals with the PDF's hash; the rules stay unverified."""
    import fitz

    from tariff_api.arr.clauses import rank, terms

    r = rule(
        "css",
        "css",
        "INR_per_kWh",
        "t * cap",
        {
            "t": {"unit": "INR_per_kWh", "source": "record:t"},
            "cap": {"unit": "percent", "source": "regulation", "value": "20"},
        },
        title="Cross-subsidy surcharge, capped",
    )
    words, values = terms(r)
    assert "surcharge" in words and "20%" in values and "20 per cent" in values
    pages = [
        "Definitions.  Surcharge means ...",
        "The cross subsidy surcharge shall not exceed 20 % of the tariff applicable.",
        "Interest at 20% per annum on arrears.",  # the value, none of the words
    ]
    got = rank(pages, r)
    # page 2 states the value with the words; page 1 has one word only (weak — not proposed);
    # page 3 has the value without the words (a bare number — never proposed)
    assert [c.page for c in got] == [2] and got[0].values == ["20 %"]
    assert "20 % of the tariff" in got[0].snippet
    # the CLI end to end on a real PDF (made here), proposals only
    import importlib.util
    import json

    pdf = tmp_path / "reg.pdf"
    doc = fitz.open()
    for t in pages:
        doc.new_page().insert_text((72, 72), t)
    doc.save(pdf)
    spec = importlib.util.spec_from_file_location("cc", ROOT_SCRIPTS / "clause_candidates.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = mod.candidates(pdf, "UPERC", "Tariff Policy")
    assert out["pages"] == 3 and len(out["sha256"]) == 64 and "none verified" in out["status"]
    css = out["rules"]["uperc.oa.css"]
    assert css and css[0]["page"] == 2
    assert all(not x.clause.verified for x in load_rules("UPERC"))
    json.dumps(out)


def test_clause_candidates_from_the_notified_2025_regulations():
    """Real document: the UPERC MYT Distribution Regulations 2025 (English text, hashed in the
    manifest).  The candidates file proposes, for the rules whose value the clause states, the
    page that states it — and verifies nothing."""
    import hashlib
    import json

    pkg = ROOT_SCRIPTS.parent / "packages"
    man = json.loads((pkg / "regulations" / "uperc" / "manifest.json").read_text())
    (doc,) = man["documents"]
    pdf = pkg / "regulations" / "uperc" / doc["file"]
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == doc["sha256"]
    cands = json.loads((pkg / "arr-rules" / "uperc" / "candidates" / "myt-2025.json").read_text())
    assert cands["sha256"] == doc["sha256"] and "none verified" in cands["status"]
    first = {rid: (c[0]["page"], c[0]["values"]) for rid, c in cands["rules"].items() if c}
    assert first["uperc.myt2025.roe"] == (31, ["15%"])
    assert first["uperc.rm2025.total"] == (43, ["3%", "5%"])
    assert first["uperc.baddebts.cap"] == (45, ["2%"])
    assert first["uperc.oa.css"] == (48, ["20%"])
    assert "uperc.myt2019.roe" not in cands["rules"]  # a 2019-only rule is not offered the 2025 text
    assert all(not r.clause.verified for r in load_rules("UPERC"))


def test_an_amended_clause_applies_only_from_its_effective_year():
    """R-APP-3 (synthetic): an amendment is a new version of the same rule from its effective
    year; the earlier version keeps the years before.  Each year is computed under the version in
    force that year, a superseded version is never chosen, and two different rules claiming the
    same output in one year are refused.  Effective dates resolve to the fiscal year — a mid-year
    amendment is not modelled."""
    inputs = {
        "equity": {"unit": "INR_crore", "source": "record:equity"},
        "rate": {"unit": "percent", "source": "record:rate"},
    }
    v1 = rule("syn.roe", "roe", "INR_crore", "rate * equity", inputs, applies={"to_fy": "FY2025-26"})
    v2 = rule(
        "syn.roe",
        "roe",
        "INR_crore",
        "rate * equity * (1 - haircut)",
        {**inputs, "haircut": {"unit": "percent", "source": "regulation", "value": "10"}},
        version=2,
        applies={"from_fy": "FY2026-27"},
    )
    values = {"record:equity": ("100", "INR_crore"), "record:rate": ("15", "percent")}
    before = RuleSet([v1, v2], "FY2025-26").evaluate("FY2025-26", values)
    after = RuleSet([v1, v2], "FY2026-27").evaluate("FY2026-27", values)
    assert before.results["roe"].value == Decimal("15") and before.results["roe"].version == 1
    assert after.results["roe"].value == Decimal("13.5") and after.results["roe"].version == 2
    # a version withdrawn (superseded) is never chosen, whatever its years
    gone = v2.model_copy(update={"status": "superseded"})
    assert "roe" not in RuleSet([v1, gone], "FY2026-27").rules
    # two different rules for one output in one year: refused, not silently picked
    rival = rule("syn.roe_other", "roe", "INR_crore", "rate * equity", inputs, applies={"from_fy": "FY2026-27"})
    with pytest.raises(RuleError, match="several rules apply to roe"):
        RuleSet([v2, rival], "FY2026-27")


def test_root_gives_a_compound_growth_rate_and_refuses_what_has_no_root():
    """root(x, n): the n-th root of a pure, non-negative number, n a whole-number literal — the
    seven-year CAGR of a sales forecast is root(end / start, 7) - 1 (increment 145)."""
    from decimal import Decimal

    import pytest

    from tariff_api.arr.rules import Q, RuleError, evaluate, parse

    src = "root(end / start, 7) - 1"
    got = evaluate(parse(src), {"end": Q(Decimal(321)), "start": Q(Decimal(149))}, src).value
    assert abs(got - Decimal("0.1158786447")) < Decimal("1e-10")  # ESR2's HV-1 consumers, AG14
    assert evaluate(parse("root(x, 7)"), {"x": Q(Decimal(128))}, "root(x, 7)").value == 2
    for bad, why in (
        ("root(x, 1.5)", "whole-number literal"),
        ("root(x, n)", "whole-number literal"),
        ("root(x)", "takes"),
    ):
        with pytest.raises(RuleError, match=why):
            evaluate(parse(bad), {"x": Q(Decimal(2)), "n": Q(Decimal(2))}, bad)
    with pytest.raises(RuleError, match="negative"):
        evaluate(parse("root(x, 2)"), {"x": Q(Decimal(-4))}, "root(x, 2)")
    with pytest.raises(RuleError, match="pure number"):
        evaluate(parse("root(x, 2)"), {"x": Q(Decimal(4), (("money", 1),))}, "root(x, 2)")
