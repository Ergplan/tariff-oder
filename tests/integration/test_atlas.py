"""The atlas (increment 52): every state with its commissions and licensees, one state's
licensees with what is on record, and a commission's ARR norms as the application holds them.
SYNTHETIC fixture data, labelled as such."""

from __future__ import annotations

import shutil

import pytest
from arr_helpers import read_and_publish

from conftest import CLIENT_A, headers

pytestmark = [pytest.mark.integration]


@pytest.fixture()
def seeded(app):
    from tariff_api.db import session_scope
    from tariff_api.seed import seed_registry

    with session_scope() as s:
        seed_registry(s)


def test_atlas_lists_states_with_commissions_and_counts(client, seeded):
    r = client.get("/atlas", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    a = r.json()
    codes = {s["code"] for s in a["states"]}
    assert {"UP", "MP", "OD"} <= codes  # the seeded registry
    up = next(s for s in a["states"] if s["code"] == "UP")
    assert any(c["code"] == "UPERC" for c in up["commissions"])
    assert {"licensees", "documents", "orders_reading", "reviewed_facts", "fixture"} <= set(up)
    assert "reviewer approves" in a["note"]
    assert client.get("/atlas").status_code in (401, 403)


def test_state_page_lists_licensees_and_unknown_state_is_404(client, seeded):
    r = client.get("/atlas/states/up", headers=headers(CLIENT_A))  # case-insensitive
    assert r.status_code == 200, r.text
    st = r.json()
    (com,) = [c for c in st["commissions"] if c["code"] == "UPERC"]
    assert any(lic["code"] == "NPCL" for lic in com["licensees"])
    assert client.get("/atlas/states/ZZ", headers=headers(CLIENT_A)).status_code == 404
    lic = client.get("/atlas/licensees/npcl", headers=headers(CLIENT_A)).json()
    assert lic["code"] == "NPCL" and lic["commission"] == "UPERC" and lic["state"] == "UP"
    assert client.get("/atlas/licensees/NOPE", headers=headers(CLIENT_A)).status_code == 404


def test_norms_describe_methods_without_inventing_values(client, seeded):
    r = client.get("/arr/norms/uperc", headers=headers(CLIENT_A))
    assert r.status_code == 200, r.text
    n = r.json()
    assert n["commission"] == "UPERC" and n["plan"]["id"] == "uperc-plan"
    assert n["plan_confirmed"] is False  # a skeleton plan is never presented as confirmed
    assert n["lines"] and all(ln["method_words"] for ln in n["lines"])
    # parameters are named, never valued
    for ln in n["lines"]:
        for p in ln["parameters"]:
            assert set(p) == {"key", "words"}
    assert {"return_basis", "gap_convention", "loss_basis", "decided_by_reviewer"} <= set(n["conventions"])
    # a commission without its own plan falls back to the generic plan, and says so by its id
    g = client.get("/arr/norms/OERC", headers=headers(CLIENT_A)).json()
    assert g["plan"]["id"] == "generic-plan" and g["mapping"]["id"] == "generic-arr"
    assert client.get("/arr/norms/NOPE", headers=headers(CLIENT_A)).status_code == 404


@pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)")
def test_reviewed_facts_are_counted_per_licensee(client, runner, object_store_root):
    read_and_publish(client, runner, "SYNTH-ATLAS")
    a = client.get("/atlas", headers=headers(CLIENT_A)).json()
    syn = next(s for s in a["states"] if any(c["code"] == "SYNTHERC" for c in s["commissions"]))
    assert syn["reviewed_facts"] >= 1 and syn["orders_reading"] >= 1
    st = client.get(f"/atlas/states/{syn['code']}", headers=headers(CLIENT_A)).json()
    lic = next(x for c in st["commissions"] for x in c["licensees"] if x["code"] == "SYNTH-ATLAS")
    assert lic["reviewed_facts"] >= 1 and lic["latest_reviewed_year"]
    assert lic["dataset"] == "fixture"
    # the norms as the commission applied them: reviewed figures only, each with order and page
    n = client.get("/arr/norms/SYNTHERC", headers=headers(CLIENT_A)).json()
    assert n["applied"], n["applied"]
    for a in n["applied"]:
        assert a["voice"] in ("final_true_up", "provisional_true_up", "approved")
        assert a["order"] and a["source_id"] and a["is_fixture"] is True
