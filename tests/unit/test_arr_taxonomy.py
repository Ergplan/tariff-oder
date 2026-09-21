"""The ARR taxonomy and the commission mappings are data; this keeps them coherent before a
loader exists: unique codes, parents that exist, identities that name real codes, each
mapping written for the taxonomy version on file, and canonical units as agreed."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "packages" / "arr-taxonomy"
TAX = json.loads((ROOT / "taxonomy.json").read_text())
CODES = {i["code"] for i in TAX["line_items"]}
_CODE = re.compile(r"\b(?:[ELCRKTX])(?:\.[A-Z0-9_]+)+\b")


def test_codes_are_unique_well_formed_and_parented():
    codes = [i["code"] for i in TAX["line_items"]]
    assert len(codes) == len(set(codes))
    for item in TAX["line_items"]:
        assert re.fullmatch(r"[A-Z][A-Z0-9_.]*", item["code"]), item["code"]
        if item["parent"] is not None:
            assert item["parent"] in CODES, f"{item['code']} has unknown parent {item['parent']}"
            assert item["code"].startswith(item["parent"].split(".")[0]), item["code"]
        else:
            assert item["kind"] == "group", f"{item['code']} has no parent but is not a group"
        assert item["kind"] in ("group", "printed", "computed", "detail")
        assert item["branch"] in ("shared", "distribution", "transmission")
        if item["kind"] in ("printed", "computed"):
            assert item["unit"] is not None or item["code"] in ("E.BALANCE", "T.TARIFF.RATE"), item["code"]


def test_identities_name_real_codes_and_are_numbered_once():
    ids = [x["id"] for x in TAX["identities"]]
    assert len(ids) == len(set(ids))
    for ident in TAX["identities"]:
        named = set(_CODE.findall(ident["expression"]))
        assert named or ident.get("cross_order"), ident["id"]
        unknown = {c for c in named if c not in CODES and not any(k.startswith(c + ".") for k in CODES)}
        assert not unknown, f"{ident['id']} names unknown codes {unknown}"
        assert ident["severity"] in ("blocking", "advisory")


def test_canonical_units_and_value_types_are_the_agreed_ones():
    assert TAX["canonical_units"]["money"] == "INR_crore"
    assert TAX["canonical_units"]["energy"] == "MU"
    assert {v["code"] for v in TAX["value_types"]} >= {"petitioned", "approved", "provisional_true_up", "final_true_up"}
    assert all(0 < v <= 1 for v in TAX["unit_conversions"].values())


def test_each_mapping_targets_the_taxonomy_on_file_and_names_only_known_branches():
    files = sorted((ROOT / "mappings").glob("*.v*.json"))
    assert {f.name for f in files} >= {"uperc-arr.v1.json", "kerc-arr.v1.json", "gerc-arr.v1.json"}
    for f in files:
        m = json.loads(f.read_text())
        assert m["taxonomy_version"] == TAX["version"], f.name
        assert m["id"] == f.name.split(".")[0], f.name
        for ch in m["chapter_map"]:
            # a chapter maps to a code or to a prefix shared by several ("C.INT" covers C.INT.*)
            assert ch["branch"] in CODES or any(c.startswith(ch["branch"] + ".") for c in CODES), (
                f"{f.name}: chapter branch {ch['branch']}"
            )
        for e in m["label_aliases"]["entries"]:
            assert e["code"] in CODES, f"{f.name}: alias to unknown {e['code']}"
        for e in m["regulation_clauses"]["entries"]:
            assert e["code"] in CODES, f"{f.name}: clause for unknown {e['code']}"
        assert m["return_basis"]["value"] in (None, "roe", "roce")
        assert m["licensees"]["distribution"] and m["licensees"]["transmission"], f.name
        for o in m["orders_expected"]:
            for d in o["decides"]:
                assert re.fullmatch(r"FY\d{4}-\d{2}", d["fy"]), d
                assert d["value_type"] in {v["code"] for v in TAX["value_types"]}, d
