"""The rule engine (ADR-0021; R-RULE-1..4, R-NUM-1..4).  SYNTHETIC rules except the last two
tests, which check the real UPERC drafts in packages/arr-rules and their worked examples."""

from __future__ import annotations

from decimal import Decimal

import pytest

from tariff_api.arr.rules import Q, Rule, RuleError, RuleSet, check_all, load_rules, parse


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
