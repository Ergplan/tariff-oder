"""Deterministic validators (Section 6.9): run after extraction and before review, each with
an id, a severity and a fixture.  Findings attach to candidates (or to the source when they
are about coverage) and are visible to reviewers.  A validator flags; it never corrects.

Severities: ``blocking`` (the record cannot be published until reviewed and resolved),
``warning`` (routes to individual review), ``info`` (recorded).  Bump ``VALIDATORS_VERSION``
when a rule changes."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from .tariff_schema import FAMILIES, NETWORK_FAMILIES, Candidate

VALIDATORS_VERSION = "2"

_TIME = re.compile(r"^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$")

# Per-profile plausible ranges (VAL-17): never a correction, only a flag.
PLAUSIBLE: dict[str, dict[tuple[str, str], tuple[float, float]]] = {
    "default": {
        ("energy", "rupees/kWh"): (0.5, 30),
        ("energy", "rupees/kVAh"): (0.5, 30),
        ("energy", "rupees/unit"): (0.5, 30),
        ("energy", "paise/unit"): (50, 3000),
        ("energy", "paise/kWh"): (50, 3000),
        ("fixed", "rupees/kW"): (1, 3000),
        ("fixed", "rupees/kVA"): (1, 3000),
        ("fixed", "rupees/HP"): (1, 3000),
        ("fixed", "rupees/BHP"): (1, 3000),
        ("fixed", "rupees/connection"): (1, 5000),
        ("demand", "rupees/kVA"): (1, 3000),
        ("demand", "rupees/kW"): (1, 3000),
        ("tod_adjustment", "percent"): (0, 100),
        ("tod_adjustment", "paise/unit"): (0, 500),
    }
}


@dataclass
class Finding:
    validator_id: str
    severity: str  # blocking | warning | info
    message: str
    candidate_keys: list[str] = field(default_factory=list)  # empty = source-level
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ValidationContext:
    candidates: list[Candidate]
    region_roles_by_page: dict[int, set[str]]  # localisation roles that cover each page
    cells: dict[tuple[int, int, int, int], str]  # (page, grid, row, col) -> raw text
    clause_lines: dict[tuple[int, int], str]  # (page, line_no) -> line text
    inventory_codes: list[str]  # schedule headings from the document inventory
    dispositions: dict[str, str] = field(default_factory=dict)  # family or code -> reviewed disposition
    utilities: list[str] = field(default_factory=list)
    periods: list[str] = field(default_factory=list)
    profile_id: str = "default"
    secondary_authoritative: bool = False
    # Milestone 4b
    approved_page_texts: dict[int, str] = field(default_factory=dict)  # consolidated schedule text
    amendment_rows: list[dict[str, Any]] = field(default_factory=list)  # {page, row, existing, modified}
    condition_texts: list[str] = field(default_factory=list)  # condition records + footnotes


def _dec(v: str | None) -> Decimal | None:
    try:
        return Decimal(v) if v is not None else None
    except Exception:  # noqa: BLE001 - a non-decimal is reported by VAL-01, not here
        return None


def run_all(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for fn in (
        val_01_field_types,
        val_02_unit_consistency,
        val_03_slab_bounds,
        val_04_option_groups,
        val_06_network_completeness,
        val_08_loss_role_separation,
        val_09_unit_sanity_per_family,
        val_10_time_bands,
        val_11_evidence_existence,
        val_13_conflicting_duplicates,
        val_15_inventory_reconciliation,
        val_17_magnitude_plausibility,
        val_18_region_provenance,
        val_05_amendment_consistency,
        val_07_derivation_checks,
        val_12_condition_links,
        val_16_cross_representation,
    ):
        findings.extend(fn(ctx))
    return findings


def val_01_field_types(ctx: ValidationContext) -> list[Finding]:
    """VAL-01 field types, decimal precision and value_state legality."""
    out = []
    for c in ctx.candidates:
        k = c.key()
        nil_word = bool(re.fullmatch(r"nil", c.original_text.strip(), re.I))
        if c.value_state == "value" and c.value is None:
            out.append(Finding("VAL-01", "blocking", "value_state value without a value", [k]))
        if c.value_state == "zero" and c.value is None and not nil_word:
            out.append(Finding("VAL-01", "blocking", "value_state zero without a value and not a printed Nil", [k]))
        if c.value_state not in ("value", "zero") and c.value is not None:
            out.append(Finding("VAL-01", "blocking", f"value present with value_state {c.value_state}", [k]))
        if c.value is not None and _dec(c.value) is None:
            out.append(Finding("VAL-01", "blocking", f"value {c.value!r} is not a decimal", [k]))
        if c.value_state == "zero" and c.value is not None and _dec(c.value) != 0:
            out.append(Finding("VAL-01", "blocking", f"value_state zero with non-zero value {c.value}", [k]))
        if c.family in NETWORK_FAMILIES and c.decision_status is None:
            out.append(Finding("VAL-01", "blocking", f"{c.family} candidate without a decision_status", [k]))
        if c.value_state == "cross_reference" and not c.reference_target:
            out.append(Finding("VAL-01", "warning", "cross_reference without a target", [k]))
        if not c.evidence:
            out.append(Finding("VAL-01", "blocking", "candidate without evidence", [k]))
    return out


def val_02_unit_consistency(ctx: ValidationContext) -> list[Finding]:
    """VAL-02 unit consistency within a component type across a category."""
    out = []
    groups: dict[tuple[str | None, str], set[tuple[str | None, str | None]]] = {}
    for c in ctx.candidates:
        if (
            c.family != "retail_tariff"
            or c.value_state not in ("value", "zero")
            or c.component_type == "tod_adjustment"
        ):
            continue
        groups.setdefault((c.category_code, c.component_type), set()).add((c.currency, c.per_unit))
    for (cat, comp), units in groups.items():
        if len(units) > 1:
            keys = [c.key() for c in ctx.candidates if c.category_code == cat and c.component_type == comp]
            out.append(
                Finding(
                    "VAL-02",
                    "warning",
                    f"{cat or '?'} {comp}: {len(units)} unit bindings {sorted(str(u) for u in units)}",
                    keys,
                )
            )
    return out


def val_03_slab_bounds(ctx: ValidationContext) -> list[Finding]:
    """VAL-03 slab bounds contiguous, non-overlapping, inclusivity recorded; telescopic
    First/Next/Above sequences get cumulative bounds derived and stored; gaps and overlaps
    flagged, never corrected."""
    out = []
    groups: dict[tuple, list[Candidate]] = {}
    for c in ctx.candidates:
        s = c.applicability.slab or c.applicability.load_band
        if s and c.family == "retail_tariff":
            a = c.applicability
            groups.setdefault(
                (c.category_code, c.component_type, a.metering_type, a.alternative, a.description), []
            ).append(c)
    for key, cands in groups.items():
        slabs = [(c, c.applicability.slab or c.applicability.load_band) for c in cands]
        keys = [c.key() for c in cands]
        if any(s.inclusivity == "ambiguous" for _, s in slabs):
            out.append(Finding("VAL-03", "warning", f"{key[0]} {key[1]}: slab inclusivity ambiguous", keys))
        kinds = {s.kind for _, s in slabs}
        if kinds & {"telescopic_first", "telescopic_next"}:
            # derive cumulative bounds: first N -> [0, N]; next M -> (N, N+M]; ...
            cum = Decimal(0)
            derived = []
            for c, s in slabs:
                if s.kind == "telescopic_first":
                    cum = _dec(s.upper) or Decimal(0)
                    derived.append((c.key(), "0", str(cum)))
                elif s.kind == "telescopic_next":
                    width = _dec(s.upper) or Decimal(0)
                    derived.append((c.key(), str(cum), str(cum + width)))
                    cum += width
                elif s.kind == "open":
                    derived.append((c.key(), s.lower or str(cum), None))
            out.append(
                Finding(
                    "VAL-03",
                    "info",
                    f"{key[0]} {key[1]}: telescopic sequence, cumulative bounds derived",
                    keys,
                    {"cumulative": derived},
                )
            )
            continue
        bounded = [(c, s) for c, s in slabs if s.kind == "absolute" and s.upper is not None]
        bounded.sort(key=lambda cs: _dec(cs[1].upper) or Decimal(0))
        for (c1, s1), (c2, s2) in zip(bounded, bounded[1:], strict=False):
            u1, l2 = _dec(s1.upper), _dec(s2.lower)
            if u1 is None or l2 is None:
                continue
            if l2 < u1 or (l2 == u1 and s1.upper_inclusive and s2.lower_inclusive):
                out.append(
                    Finding(
                        "VAL-03",
                        "warning",
                        f"{key[0]} {key[1]}: overlapping slabs {s1.original_text!r} / {s2.original_text!r}",
                        [c1.key(), c2.key()],
                    )
                )
            elif l2 > u1 + 1:
                out.append(
                    Finding(
                        "VAL-03",
                        "warning",
                        f"{key[0]} {key[1]}: gap between {s1.original_text!r} and {s2.original_text!r}",
                        [c1.key(), c2.key()],
                    )
                )
    return out


def val_04_option_groups(ctx: ValidationContext) -> list[Finding]:
    """VAL-04 every option group has at least two complete alternatives; a category with a
    group cannot publish a single default rate."""
    out = []
    by_cat: dict[str | None, set[int]] = {}
    for c in ctx.candidates:
        if c.applicability.alternative is not None:
            by_cat.setdefault(c.category_code, set()).add(c.applicability.alternative)
    for cat, alts in by_cat.items():
        keys = [c.key() for c in ctx.candidates if c.category_code == cat and c.applicability.alternative is not None]
        if len(alts) < 2:
            out.append(Finding("VAL-04", "blocking", f"{cat}: option group with a single alternative", keys))
        else:
            out.append(
                Finding("VAL-04", "info", f"{cat}: option group with {len(alts)} alternatives; no default rate", keys)
            )
    return out


def val_06_network_completeness(ctx: ValidationContext) -> list[Finding]:
    """VAL-06 for every utility and year the order covers, each family has a fact, a typed
    decision status, or a reviewer-confirmed absent_in_source disposition."""
    out = []
    present = {c.family for c in ctx.candidates}
    for fam in FAMILIES:
        if fam in present or fam in ctx.dispositions:
            continue
        out.append(
            Finding(
                "VAL-06",
                "blocking",
                f"family {fam}: no candidate, no decision status and no reviewed disposition; "
                "coverage cannot be complete",
                [],
                {"family": fam},
            )
        )
    return out


def val_08_loss_role_separation(ctx: ValidationContext) -> list[Finding]:
    """VAL-08 an oa_loss cites an open-access/CSS region; a distribution_loss_approved cites
    an ARR/true-up region; one evidence span never supports both."""
    out = []
    seen: dict[tuple[int, str], set[str]] = {}
    for c in ctx.candidates:
        if c.family not in ("oa_loss", "distribution_loss_approved"):
            continue
        for e in c.evidence:
            roles = ctx.region_roles_by_page.get(e.page_index, set())
            ok = ("network_charges" in roles) if c.family == "oa_loss" else ("loss_trajectory" in roles)
            if not ok:
                out.append(
                    Finding(
                        "VAL-08",
                        "blocking",
                        f"{c.family} cites page {e.page_index} outside its role's region",
                        [c.key()],
                    )
                )
            seen.setdefault((e.page_index, e.excerpt), set()).add(c.family)
    for (page, excerpt), fams in seen.items():
        if len(fams) > 1:
            out.append(
                Finding("VAL-08", "blocking", f"page {page} span {excerpt[:40]!r} supports both {sorted(fams)}", [])
            )
    return out


def val_09_unit_sanity_per_family(ctx: ValidationContext) -> list[Finding]:
    """VAL-09 CSS and wheeling in paise/unit or Rs/kWh; losses in percent; banking in
    percent in kind or money with the basis stated."""
    out = []
    for c in ctx.candidates:
        if c.value_state not in ("value", "zero"):
            continue
        k = c.key()
        if c.family in ("wheeling_charge", "cross_subsidy_surcharge") and c.per_unit not in ("kWh", "unit", "kVAh"):
            out.append(
                Finding("VAL-09", "warning", f"{c.family} unit {c.currency}/{c.per_unit} is not per unit energy", [k])
            )
        if c.family in ("oa_loss", "distribution_loss_approved") and c.per_unit != "percent":
            out.append(Finding("VAL-09", "blocking", f"{c.family} must be a percentage, got {c.per_unit}", [k]))
        if c.family == "banking_rule" and c.per_unit not in ("percent", "kWh", "unit", None):
            out.append(Finding("VAL-09", "warning", f"banking charge unit {c.per_unit} needs a stated basis", [k]))
    return out


def val_10_time_bands(ctx: ValidationContext) -> list[Finding]:
    """VAL-10 time bands cover the day or are explicitly partial; seasons have dates."""
    out = []
    groups: dict[tuple, list[Candidate]] = {}
    for c in ctx.candidates:
        if c.component_type == "tod_adjustment" and c.applicability.time_band:
            groups.setdefault((c.category_code, c.applicability.season, c.applicability.alternative), []).append(c)
    for key, cands in groups.items():
        minutes = 0
        for c in cands:
            m = _TIME.match(c.applicability.time_band or "")
            if not m:
                out.append(
                    Finding("VAL-10", "warning", f"unparseable time band {c.applicability.time_band!r}", [c.key()])
                )
                continue
            a = int(m.group(1)) * 60 + int(m.group(2))
            b = int(m.group(3)) * 60 + int(m.group(4))
            minutes += (b - a) if b > a else (24 * 60 - a + b)
        keys = [c.key() for c in cands]
        if minutes != 24 * 60:
            out.append(
                Finding(
                    "VAL-10",
                    "warning",
                    f"{key[0]}: time bands cover {minutes} of 1440 minutes (partial)",
                    keys,
                    {"minutes": minutes},
                )
            )
        if key[1] and not re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", key[1], re.I):
            out.append(Finding("VAL-10", "info", f"{key[0]}: season {key[1]!r} has no month bounds", keys))
    return out


def val_11_evidence_existence(ctx: ValidationContext) -> list[Finding]:
    """VAL-11 every cited cell / clause exists in the artefacts and contains the cited text."""
    out = []
    for c in ctx.candidates:
        for e in c.evidence:
            if e.kind == "cell":
                raw = ctx.cells.get((e.page_index, e.grid_ordinal or 0, e.row or 0, e.col or 0))
                if raw is None:
                    out.append(
                        Finding(
                            "VAL-11",
                            "blocking",
                            f"cited cell p{e.page_index} g{e.grid_ordinal} r{e.row} c{e.col} does not exist",
                            [c.key()],
                        )
                    )
                elif e.excerpt.strip() not in raw and raw.strip() not in e.excerpt:
                    out.append(
                        Finding(
                            "VAL-11",
                            "blocking",
                            f"cited cell text {e.excerpt!r} differs from the artefact {raw!r}",
                            [c.key()],
                        )
                    )
            elif e.kind == "clause":
                line = ctx.clause_lines.get((e.page_index, e.line_no or 0))
                if line is None:
                    out.append(
                        Finding(
                            "VAL-11",
                            "blocking",
                            f"cited clause p{e.page_index} line {e.line_no} does not exist",
                            [c.key()],
                        )
                    )
                elif e.excerpt.strip() not in line:
                    out.append(Finding("VAL-11", "blocking", "cited clause text differs from the artefact", [c.key()]))
    return out


def val_13_conflicting_duplicates(ctx: ValidationContext) -> list[Finding]:
    """VAL-13 the same category/component/period with different values."""
    out = []
    by_key: dict[str, set[tuple]] = {}
    for c in ctx.candidates:
        by_key.setdefault(c.key(), set()).add((c.value, c.value_state, c.currency, c.per_unit))
    for k, vals in by_key.items():
        if len(vals) > 1:
            out.append(Finding("VAL-13", "blocking", f"conflicting duplicates: {sorted(str(v) for v in vals)}", [k]))
    return out


def val_15_inventory_reconciliation(ctx: ValidationContext) -> list[Finding]:
    """VAL-15 every category heading in the inventory has candidates or a disposition."""
    out = []
    covered = {c.category_code for c in ctx.candidates if c.category_code}
    for code in ctx.inventory_codes:
        if code not in covered and code not in ctx.dispositions:
            out.append(
                Finding(
                    "VAL-15",
                    "warning",
                    f"inventory category {code} has no candidates and no disposition",
                    [],
                    {"code": code},
                )
            )
    for code in sorted(covered - set(ctx.inventory_codes)):
        out.append(
            Finding(
                "VAL-15",
                "warning",
                f"candidates cite category {code} which is not in the inventory",
                [c.key() for c in ctx.candidates if c.category_code == code],
            )
        )
    return out


def val_17_magnitude_plausibility(ctx: ValidationContext) -> list[Finding]:
    """VAL-17 currency and magnitude plausibility per profile (an energy charge of 580 rupees
    per unit, a fixed charge of 145 paise): flagged, never corrected."""
    out = []
    ranges = PLAUSIBLE.get(ctx.profile_id, PLAUSIBLE["default"])
    for c in ctx.candidates:
        if c.family != "retail_tariff" or c.value_state != "value" or c.value is None:
            continue
        unit = f"{c.currency}/{c.per_unit}" if c.per_unit != "percent" else "percent"
        rng = ranges.get((c.component_type, unit))
        v = _dec(c.value)
        if rng and v is not None and not (Decimal(rng[0]) <= abs(v) <= Decimal(rng[1])):
            out.append(
                Finding(
                    "VAL-17",
                    "warning",
                    f"{c.category_code} {c.component_type} {c.value} {unit} outside the plausible range {rng}",
                    [c.key()],
                )
            )
    return out


def val_18_region_provenance(ctx: ValidationContext) -> list[Finding]:
    """VAL-18 a retail candidate must cite an approved region; a value that exists only in a
    proposed or existing table must not become a candidate (Section 6.9, cross-table)."""
    out = []
    for c in ctx.candidates:
        if c.family != "retail_tariff":
            continue
        for e in c.evidence:
            roles = ctx.region_roles_by_page.get(e.page_index, set())
            if not roles & {"approved_schedule", "approved_summary"}:
                out.append(
                    Finding(
                        "VAL-18",
                        "blocking",
                        f"retail candidate cites page {e.page_index} outside the approved regions "
                        f"({sorted(roles) or 'none'})",
                        [c.key()],
                    )
                )
    return out


# ------------------------------------------------------------------ Milestone 4b validators


def _norm_text(t: str) -> str:
    return re.sub(r"[^a-z0-9%.:]+", " ", t.lower()).strip()


def val_05_amendment_consistency(ctx: ValidationContext) -> list[Finding]:
    """VAL-05 every `Modified description` in an amendment table must appear in the
    consolidated schedule; a mismatch is a finding (the left column is superseded text)."""
    out = []
    consolidated = _norm_text(" ".join(ctx.approved_page_texts.values()))
    for r in ctx.amendment_rows:
        modified = _norm_text(r.get("modified") or "")
        if not modified:
            continue
        if modified in consolidated:
            out.append(
                Finding(
                    "VAL-05",
                    "info",
                    f"amendment row {r.get('row')} on page {r.get('page')}: modified text present in the "
                    "consolidated schedule",
                    [],
                    r,
                )
            )
        else:
            out.append(
                Finding(
                    "VAL-05",
                    "blocking",
                    f"amendment row {r.get('row')} on page {r.get('page')}: modified description {r.get('modified')!r} "
                    "not found in the consolidated schedule",
                    [],
                    r,
                )
            )
        existing = _norm_text(r.get("existing") or "")
        if existing and existing != modified and existing in consolidated and modified not in consolidated:
            out.append(
                Finding(
                    "VAL-05",
                    "blocking",
                    "the superseded (existing) text is what the consolidated schedule carries",
                    [],
                    r,
                )
            )
    return out


def val_07_derivation_checks(ctx: ValidationContext) -> list[Finding]:
    """VAL-07 where the order prints the arithmetic, recompute from the printed inputs and
    compare with the printed result; mismatch flags, never corrects.  Rules: wheeling =
    ARR (Rs Cr) ÷ sales (MU) → Rs/kWh; CSS approved = lower of the two printed columns;
    cap = printed cap column bounds the approved value."""
    out = []
    for c in ctx.candidates:
        d = c.derivation
        if not d or c.value is None:
            continue
        k = c.key()
        rule = d.get("rule")
        inputs = d.get("inputs") or {}
        printed = _dec(c.value)
        f = d.get("formula")
        if isinstance(f, dict) and f.get("rule") == "css_formula":
            out.extend(_css_formula_findings(k, f, printed))
        if rule == "arr_over_sales" and printed is not None:
            arr = _dec((inputs.get("arr") or {}).get("value"))
            sales = _dec((inputs.get("sales") or {}).get("value"))
            if arr is None or sales is None or sales == 0:
                out.append(
                    Finding("VAL-07", "warning", "wheeling derivation inputs incomplete; not recomputed", [k], d)
                )
                continue
            computed = (arr * Decimal(10_000_000)) / (sales * Decimal(1_000_000))  # Rs Cr / MU → Rs/kWh
            places = max(0, -printed.as_tuple().exponent)
            if abs(computed - printed) > Decimal(1).scaleb(-places):
                out.append(
                    Finding(
                        "VAL-07",
                        "blocking",
                        f"wheeling charge printed {printed} but ARR/sales gives {computed:.4f}",
                        [k],
                        {**d, "computed": str(round(computed, 4))},
                    )
                )
            else:
                out.append(
                    Finding(
                        "VAL-07",
                        "info",
                        f"wheeling charge {printed} agrees with ARR/sales ({computed:.4f})",
                        [k],
                        {**d, "computed": str(round(computed, 4))},
                    )
                )
        elif rule == "lower_of" and printed is not None:
            vals = [_dec(v) for v in inputs.values() if _dec(v) is not None]
            if len(vals) < 2:
                out.append(Finding("VAL-07", "warning", "lower-of rule with fewer than two printed inputs", [k], d))
                continue
            expected = min(vals)
            if printed != expected:
                out.append(
                    Finding(
                        "VAL-07",
                        "blocking",
                        f"approved {printed} is not the lower of the printed inputs (expected {expected})",
                        [k],
                        d,
                    )
                )
            else:
                out.append(
                    Finding(
                        "VAL-07", "info", f"approved {printed} is the lower of {sorted(str(v) for v in vals)}", [k], d
                    )
                )
        elif rule == "cap" and printed is not None:
            cap = next((_dec(v) for h, v in inputs.items() if "cap" in h.lower() and _dec(v) is not None), None)
            tariff = next((_dec(v) for h, v in inputs.items() if "tariff" in h.lower() and _dec(v) is not None), None)
            if cap is not None and tariff is not None and abs(cap - tariff * Decimal("0.2")) > Decimal("0.01"):
                out.append(
                    Finding(
                        "VAL-07", "blocking", f"printed cap {cap} is not 20% of the printed tariff {tariff}", [k], d
                    )
                )
            if cap is not None and printed > cap:
                out.append(Finding("VAL-07", "blocking", f"approved {printed} exceeds the printed cap {cap}", [k], d))
            elif cap is not None:
                out.append(Finding("VAL-07", "info", f"approved {printed} within the cap {cap}", [k], d))
    return out


def _css_formula_findings(k: str, f: dict[str, Any], approved: Decimal | None) -> list[Finding]:
    """S = T − [C/(1 − L/100) + D + R] recomputed from the printed inputs (css_formula
    module) against the printed computed value, the printed cap against 20% of T, and the
    approved value against the cap.  Every mismatch is a finding for the reviewer; the
    order's numbers are never rewritten."""
    out: list[Finding] = []
    lvl = f.get("level")
    if f.get("computed") is None:
        why = f.get("error") or f"inputs missing: {', '.join(f.get('missing') or [])}"
        out.append(Finding("VAL-07", "warning", f"CSS formula at {lvl}: not recomputed ({why})", [k], f))
        return out
    computed = _dec(f["computed"])
    printed_s = _dec(f.get("printed_computed"))
    if printed_s is not None and computed is not None:
        places = max(0, -printed_s.as_tuple().exponent)
        tol = Decimal(1).scaleb(-places)  # printed rounding
        if abs(computed - printed_s) > tol:
            out.append(
                Finding(
                    "VAL-07",
                    "blocking",
                    f"CSS at {lvl}: order prints computed {printed_s} but its own inputs give {computed}",
                    [k],
                    f,
                )
            )
        else:
            out.append(
                Finding(
                    "VAL-07",
                    "info",
                    f"CSS at {lvl}: printed computed {printed_s} agrees with S = T - [C/(1-L/100) + D + R] ({computed})"
                    + (f"; {'; '.join(f['assumed'])}" if f.get("assumed") else ""),
                    [k],
                    f,
                )
            )
    cap = _dec(f.get("cap_20pct_of_T"))
    printed_cap = _dec(f.get("printed_cap"))
    if printed_cap is not None and cap is not None and abs(printed_cap - cap) > Decimal("0.01"):
        out.append(
            Finding("VAL-07", "blocking", f"CSS at {lvl}: printed cap {printed_cap} is not 20% of T ({cap})", [k], f)
        )
    effective_cap = printed_cap if printed_cap is not None else cap
    if approved is not None and effective_cap is not None:
        if approved > effective_cap + Decimal("0.005"):
            out.append(
                Finding(
                    "VAL-07",
                    "blocking",
                    f"CSS at {lvl}: approved {approved} exceeds the 20% cap {effective_cap}",
                    [k],
                    f,
                )
            )
        else:
            out.append(
                Finding(
                    "VAL-07", "info", f"CSS at {lvl}: approved {approved} is within the 20% cap {effective_cap}", [k], f
                )
            )
    return out


def val_12_condition_links(ctx: ValidationContext) -> list[Finding]:
    """VAL-12 a component that references a condition must link to an existing condition
    record: every condition text on a candidate must be a recorded condition or footnote."""
    out = []
    known = [_norm_text(t) for t in ctx.condition_texts]
    for c in ctx.candidates:
        for cond in c.conditions:
            n = _norm_text(cond)
            # a candidate may cite a provision in full or the clause of it that binds the rate
            if not any(n == k or (len(n) >= 12 and n in k) for k in known):
                out.append(
                    Finding(
                        "VAL-12",
                        "warning",
                        f"condition text not found among condition records: {cond[:80]!r}",
                        [c.key()],
                    )
                )
    return out


def val_16_cross_representation(ctx: ValidationContext) -> list[Finding]:
    """VAL-16 where two authoritative representations exist (schedule and summary), every
    category/component/period must match after normalisation; mismatches block."""
    out = []
    if not ctx.secondary_authoritative:
        return out
    by_role: dict[str, dict[tuple, Candidate]] = {"approved_schedule": {}, "approved_summary": {}}
    for c in ctx.candidates:
        if c.family != "retail_tariff" or c.value is None:
            continue
        roles = set()
        for e in c.evidence:
            roles |= ctx.region_roles_by_page.get(e.page_index, set())
        role = (
            "approved_summary"
            if "approved_summary" in roles
            else ("approved_schedule" if "approved_schedule" in roles else None)
        )
        if role is None:
            continue
        by_role[role][(c.category_code, c.component_type, c.period)] = c
    if not by_role["approved_summary"]:
        out.append(
            Finding(
                "VAL-16",
                "warning",
                "profile declares a secondary authoritative table but no summary candidates exist",
                [],
            )
        )
        return out
    for key, sc in by_role["approved_summary"].items():
        pc = by_role["approved_schedule"].get(key)
        if pc is None:
            out.append(
                Finding(
                    "VAL-16", "warning", f"summary has {key} but the schedule has no matching candidate", [sc.key()]
                )
            )
            continue
        same = _dec(sc.value) == _dec(pc.value) and (sc.currency == pc.currency or None in (sc.currency, pc.currency))
        if same:
            out.append(
                Finding("VAL-16", "info", f"{key}: schedule and summary agree ({pc.value})", [pc.key(), sc.key()])
            )
        else:
            out.append(
                Finding(
                    "VAL-16",
                    "blocking",
                    f"{key}: schedule {pc.value} {pc.currency} vs summary {sc.value} {sc.currency} disagree; "
                    "publication of both blocked until reviewed",
                    [pc.key(), sc.key()],
                )
            )
    return out
