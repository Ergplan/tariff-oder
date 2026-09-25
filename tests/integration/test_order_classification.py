"""Increment 24: an order says what it is and which years it decides (ARR spec section 5);
the registry knows transmission licensees; both are stated by a person, audited, and never
inferred from the file."""

from __future__ import annotations

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import structure_order_pdf


def _seed(app):
    from tariff_api.db import session_scope
    from tariff_api.seed import seed_registry

    with session_scope() as s:
        seed_registry(s)


def test_upload_carries_the_order_type_and_decided_years_and_an_admin_can_change_them(client, app):
    _seed(app)
    r = client.post(
        "/sources",
        files={"file": ("SYNTHETIC_myt.pdf", structure_order_pdf() + b"\n%classification-test\n", "application/pdf")},
        data={
            "dataset_kind": "fixture",
            "utility_code": "NPCL",
            "order_type": "tariff_order",
            "decides": "FY2024-25:final_true_up, FY2025-26:provisional_true_up, FY2026-27:approved",
        },
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    src = r.json()["source"]
    assert src["order_type"] == "tariff_order"
    assert [d["fiscal_year"] for d in src["decides"]] == ["FY2024-25", "FY2025-26", "FY2026-27"]
    assert src["decides"][0]["value_type"] == "final_true_up"

    # a malformed year is refused, not silently dropped
    bad = client.post(
        "/sources",
        files={"file": ("SYNTHETIC_bad.pdf", structure_order_pdf() + b"\n%classification-bad\n", "application/pdf")},
        data={"dataset_kind": "fixture", "decides": "2026-27:approved"},
        headers=headers(ADMIN),
    )
    assert bad.status_code == 422 and bad.json()["error_type"] == "validation_failed"
    unknown = client.post(
        "/sources",
        files={"file": ("SYNTHETIC_bad2.pdf", structure_order_pdf() + b"\n%classification-bad2\n", "application/pdf")},
        data={"dataset_kind": "fixture", "order_type": "press_release"},
        headers=headers(ADMIN),
    )
    assert unknown.status_code == 422

    # reclassify: administrators only, audited
    body = {"order_type": "myt_order", "decides": [{"fiscal_year": "FY2025-26", "value_type": "control_period"}]}
    assert client.put(f"/sources/{src['id']}/classification", json=body, headers=headers(REVIEWER)).status_code == 403
    r = client.put(f"/sources/{src['id']}/classification", json=body, headers=headers(ADMIN))
    assert r.status_code == 200, r.text
    assert r.json()["order_type"] == "myt_order"
    assert r.json()["decides"] == body["decides"]
    d = client.get(f"/sources/{src['id']}", headers=headers(ANALYST)).json()
    assert d["order_type"] == "myt_order" and d["decides"] == body["decides"]
    audit = client.get("/audit", params={"entity_id": src["id"]}, headers=headers(ADMIN)).json()
    assert any(a["action"] == "source.classify" for a in audit)

    # clearing is explicit
    r = client.put(f"/sources/{src['id']}/classification", json={}, headers=headers(ADMIN))
    assert r.status_code == 200 and r.json()["order_type"] is None and r.json()["decides"] is None


def test_registry_seeds_the_three_transmission_licensees_and_exposes_the_kind(client, app):
    _seed(app)
    reg = client.get("/registry", headers=headers(ANALYST)).json()
    by_code = {u["code"]: u for u in reg["utilities"]}
    for code in ("UPPTCL", "KPTCL", "GETCO"):
        assert by_code[code]["licensee_kind"] == "transmission", code
    assert by_code["NPCL"]["licensee_kind"] == "distribution"
    cl = client.get("/commissions", headers=headers(ANALYST)).json()
    gerc = next(c for c in cl["commissions"] if c["code"] == "GERC")
    assert any(u["code"] == "GETCO" and u["licensee_kind"] == "transmission" for u in gerc["utilities"])

    r = client.post(
        "/utilities",
        json={
            "code": "TESTTX",
            "name": "Test Transmission Co",
            "commission_code": "GERC",
            "licensee_kind": "transmission",
        },
        headers=headers(ADMIN),
    )
    assert r.status_code == 201 and r.json()["licensee_kind"] == "transmission"
