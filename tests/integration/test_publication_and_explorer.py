"""Milestone 5b gate items at the API layer: unapproved facts cannot enter the explorer (the
explorer module never touches candidates, and a pending candidate never appears);
publication fails on missing required items, on undeclared gaps, on a stale source version
and on a stale preview token; a partial release is labelled partial everywhere with its
gaps; citations are derived from published evidence rows; published decisions are no longer
reversible; releases are cumulative and the earlier one is superseded."""

from __future__ import annotations

import inspect
import shutil

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import structure_order_pdf

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(shutil.which("tesseract") is None, reason="tesseract not installed (parse needs it)"),
]
CONFIRM = {"decision": "confirm", "rationale": "Annexure located; pages checked", "pages_viewed": True}
FAMILIES = [
    "wheeling_charge",
    "oa_loss",
    "distribution_loss_approved",
    "cross_subsidy_surcharge",
    "additional_surcharge",
    "banking_rule",
    "green_tariff",
    "transmission_reference",
]


def _upload(client, data: bytes, name: str) -> str:
    r = client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    return r.json()["source"]["id"]


def _run_all(runner) -> int:
    n = 0
    while runner.run_once():
        n += 1
    return n


def _to_review(client, runner, data: bytes, name: str) -> str:
    src_id = _upload(client, data, name)
    assert _run_all(runner) == 4
    assert (
        client.post(f"/sources/{src_id}/localisation/decision", json=CONFIRM, headers=headers(REVIEWER)).status_code
        == 200
    )
    assert _run_all(runner) == 3
    return src_id


def _approve_fully(client, cand: dict) -> None:
    """First reviewer, then a different second reviewer (the fixture is the first order read
    with its profile, so everything needs a second review)."""
    cid, version = cand["id"], cand["version"]
    for user in (REVIEWER, ADMIN):
        r = client.get(f"/candidates/{cid}/evidence/0/image", headers=headers(user))
        assert r.status_code == 200
        r = client.post(
            f"/candidates/{cid}/decision",
            json={
                "outcome": "approve",
                "expected_version": version,
                "evidence_view_ids": [r.headers["x-evidence-view-id"]],
            },
            headers=headers(user),
        )
        assert r.status_code == 200, r.text
        version = r.json()["candidate"]["version"]
    assert r.json()["candidate"]["review_status"] == "approved"


def _clean_categories(queue: dict) -> list[str]:
    by_cat: dict[str, list[dict]] = {}
    for i in queue["items"]:
        c = i["candidate"]
        if c["category_code"]:
            by_cat.setdefault(c["category_code"], []).append(c)
    return sorted(k for k, v in by_cat.items() if all(c["blocking_finding_count"] == 0 for c in v) and len(v) >= 2)


def test_explorer_module_never_reads_candidates():
    from tariff_api.routers import explorer

    src = inspect.getsource(explorer)
    assert "CandidateRecord" not in src and "ReviewDecision" not in src and "EvidenceView" not in src
    assert "PublishedFact" in src and "PublishedEvidence" in src


def test_publication_transaction_and_published_explorer(client, runner):
    src_id = _to_review(client, runner, structure_order_pdf(), "SYNTHETIC_structure.pdf")

    # before any release the explorer is coverage-insufficient, never a candidate preview
    t = client.get(f"/explorer/sources/{src_id}/tariff", headers=headers(ANALYST)).json()
    assert t["status"] == "coverage_insufficient" and t["categories"] == [] and t["release"] is None
    n = client.get(f"/explorer/sources/{src_id}/network", headers=headers(ANALYST)).json()
    assert n["status"] == "coverage_insufficient" and len(n["families"]) == 8
    assert all(f["status"] == "coverage_insufficient" for f in n["families"])
    assert client.get("/explorer/releases", headers=headers(ANALYST)).json()["total"] == 0

    # preview: analysts cannot; the reviewer sees what stands in the way
    assert client.post(f"/sources/{src_id}/publish/preview", json={}, headers=headers(ANALYST)).status_code == 403
    pv = client.post(f"/sources/{src_id}/publish/preview", json={}, headers=headers(REVIEWER)).json()
    assert (
        pv["facts_to_publish"] == 0
        and pv["candidates_in_scope"] > 0
        and len(pv["pending"]) == pv["candidates_in_scope"]
    )
    missing_keys = {m["key"] for m in pv["missing_for_complete"]}
    assert set(FAMILIES) <= missing_keys and pv["checklist"]["inventory_categories"]
    assert set(pv["checklist"]["inventory_categories"]) <= missing_keys
    assert len(pv["preview_token"]) == 64 and pv["prior_release"] is None
    src_version = pv["source_version"]

    base = {
        "rationale": "first release of the fixture order",
        "expected_source_version": src_version,
        "confirm_consequences": True,
    }
    # complete is refused while required items are missing; partial must declare every gap
    r = client.post(
        f"/sources/{src_id}/publish",
        json={**base, "completeness": "complete", "preview_token": pv["preview_token"]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and r.json()["extra"]["missing"]
    r = client.post(
        f"/sources/{src_id}/publish",
        json={**base, "completeness": "partial", "preview_token": pv["preview_token"]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and set(r.json()["extra"]["undeclared_gaps"]) == set(
        pv["gap_keys_required_for_partial"]
    )
    gaps = [{"key": k, "reason": "not reviewed yet"} for k in pv["gap_keys_required_for_partial"]]
    r = client.post(
        f"/sources/{src_id}/publish",
        json={**base, "completeness": "partial", "gaps": gaps, "preview_token": pv["preview_token"]},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 422 and "nothing to publish" in r.json()["detail"]
    # an unconfirmed publication is refused even with a valid token
    assert client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()["state"] == "awaiting_review"

    # approve every candidate of one clean category (two reviewers each), record a disposition
    q = client.get(f"/sources/{src_id}/review/queue", params={"limit": 500}, headers=headers(ANALYST)).json()
    cats = _clean_categories(q)
    assert len(cats) >= 2, cats
    first_cat, second_cat = cats[0], cats[1]
    first_cands = [i["candidate"] for i in q["items"] if i["candidate"]["category_code"] == first_cat]
    for c in first_cands:
        _approve_fully(client, c)
    disp = {
        "family": "banking_rule",
        "disposition": "absent_in_source",
        "rationale": "no banking provision",
        "pages_viewed": True,
    }
    assert client.put(f"/sources/{src_id}/dispositions", json=disp, headers=headers(REVIEWER)).status_code == 200

    # a subset release over that category: the token from before the decisions is stale
    r = client.post(
        f"/sources/{src_id}/publish",
        json={
            **base,
            "scope": "subset",
            "categories": [first_cat],
            "completeness": "partial",
            "gaps": gaps,
            "preview_token": pv["preview_token"],
        },
        headers=headers(REVIEWER),
    )
    assert r.status_code == 409 and r.json()["error_type"] == "conflict_stale_version"
    pv2 = client.post(
        f"/sources/{src_id}/publish/preview",
        json={"scope": "subset", "categories": [first_cat]},
        headers=headers(REVIEWER),
    ).json()
    assert pv2["facts_to_publish"] == len(first_cands) and pv2["pending"] == [] and pv2["blocked_by_findings"] == []
    assert first_cat not in {m["key"] for m in pv2["missing_for_complete"]}
    req2 = {
        **base,
        "scope": "subset",
        "categories": [first_cat],
        "completeness": "partial",
        "gaps": [{"key": k, "reason": "outside this release"} for k in pv2["gap_keys_required_for_partial"]],
        "preview_token": pv2["preview_token"],
    }
    r = client.post(
        f"/sources/{src_id}/publish",
        json={**req2, "expected_source_version": src_version + 99},
        headers=headers(REVIEWER),
    )
    assert r.status_code == 409 and r.json()["error_type"] == "conflict_stale_version"
    r = client.post(
        f"/sources/{src_id}/publish", json={**req2, "confirm_consequences": False}, headers=headers(REVIEWER)
    )
    assert r.status_code == 422 and "confirmed" in r.json()["detail"]
    assert client.post(f"/sources/{src_id}/publish", json=req2, headers=headers(ANALYST)).status_code == 403
    r = client.post(f"/sources/{src_id}/publish", json=req2, headers=headers(REVIEWER))
    assert r.status_code == 201, r.text
    rel = r.json()
    assert rel["release_number"] == 1 and rel["completeness"] == "partial" and rel["scope"] == "subset"
    assert rel["fact_count"] == len(first_cands) and rel["is_current"] and rel["is_fixture"] is True
    assert rel["scope_categories"] == [first_cat] and rel["published_by"] == REVIEWER
    d = client.get(f"/sources/{src_id}", headers=headers(ANALYST)).json()
    assert (
        d["state"] == "published"
        and d["publication"]["release_number"] == 1
        and d["publication"]["completeness"] == "partial"
    )

    # the explorer shows only the published facts, labelled partial, with derived citations
    t = client.get(f"/explorer/sources/{src_id}/tariff", headers=headers(ANALYST)).json()
    assert t["status"] == "published" and [c["category_code"] for c in t["categories"]] == [first_cat]
    assert t["completeness"]["completeness"] == "partial" and t["completeness"]["is_fixture"] is True
    assert t["completeness"]["gaps"] and set(t["unresolved_items"]) == {g["key"] for g in req2["gaps"]}
    facts = [f for c in t["categories"] for fs in c["components"].values() for f in fs]
    assert len(facts) == len(first_cands) and {f["candidate_id"] for f in facts} == {c["id"] for c in first_cands}
    by_cand = {c["id"]: c for c in first_cands}
    for f in facts:
        assert f["review_status"] == "approved" and f["citations"], f
        c0 = f["citations"][0]
        ev0 = by_cand[f["candidate_id"]]["record"]["evidence"][0]
        assert c0["pdf_page"] == ev0["page_index"] and c0["excerpt"] == ev0["excerpt"] and c0["source_id"] == src_id
        if ev0["kind"] == "cell":
            assert (
                c0["table_id"] == f"p{ev0['page_index']}-g{ev0['grid_ordinal']}"
                and c0["cell"] == f"r{ev0['row']}c{ev0['col']}"
            )
    pending_ids = {i["candidate"]["id"] for i in q["items"] if i["candidate"]["category_code"] != first_cat}
    assert not ({f["candidate_id"] for f in facts} & pending_ids)
    fact = client.get(f"/explorer/facts/{facts[0]['fact_id']}", headers=headers(ANALYST)).json()
    assert (
        fact["value"] == facts[0]["value"]
        and fact["citations"][0]["evidence_id"] == facts[0]["citations"][0]["evidence_id"]
    )
    img = client.get(f"/explorer/facts/{facts[0]['fact_id']}/evidence/0/image", headers=headers(ANALYST))
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    n = client.get(f"/explorer/sources/{src_id}/network", headers=headers(ANALYST)).json()
    assert n["status"] == "published" and n["completeness"]["completeness"] == "partial"
    banking = next(f for f in n["families"] if f["family"] == "banking_rule")
    assert banking["status"] == "coverage_insufficient" and banking["disposition"] == "absent_in_source"
    assert all(f["status"] == "coverage_insufficient" for f in n["families"])
    rl = client.get("/explorer/releases", headers=headers(ANALYST)).json()
    assert rl["total"] == 1 and rl["fixture"] == 1 and rl["real"] == 0
    assert (
        client.get("/explorer/releases", params={"dataset_kind": "real"}, headers=headers(ANALYST)).json()["total"] == 0
    )

    # published decisions are frozen; remaining candidates can still be decided
    pub_c = first_cands[0]
    hist = client.get(f"/candidates/{pub_c['id']}/decisions", headers=headers(ANALYST)).json()
    last = [dd for dd in hist["decisions"] if not dd["undone"]][-1]
    r = client.post(f"/review/decisions/{last['id']}/undo", headers=headers(ADMIN))
    assert r.status_code == 409 and "published" in r.json()["detail"]
    second_cands = [i["candidate"] for i in q["items"] if i["candidate"]["category_code"] == second_cat]
    for c in second_cands:
        _approve_fully(client, c)

    # the second release is cumulative and supersedes the first
    pv3 = client.post(
        f"/sources/{src_id}/publish/preview",
        json={"scope": "subset", "categories": [first_cat, second_cat]},
        headers=headers(REVIEWER),
    ).json()
    assert pv3["prior_release"]["release_number"] == 1 and pv3["facts_to_publish"] == len(first_cands) + len(
        second_cands
    )
    r = client.post(
        f"/sources/{src_id}/publish",
        json={
            **base,
            "scope": "subset",
            "categories": [first_cat, second_cat],
            "completeness": "partial",
            "gaps": [{"key": k, "reason": "outside this release"} for k in pv3["gap_keys_required_for_partial"]],
            "expected_source_version": pv3["source_version"],
            "preview_token": pv3["preview_token"],
            "rationale": "second release adds a category",
        },
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    rel2 = r.json()
    assert rel2["release_number"] == 2 and rel2["fact_count"] == len(first_cands) + len(second_cands)
    releases = client.get(f"/sources/{src_id}/releases", headers=headers(ANALYST)).json()
    assert releases["total"] == 2
    assert releases["releases"][0]["is_current"] is False and releases["releases"][0]["superseded_by_id"] == rel2["id"]
    assert releases["releases"][1]["is_current"] is True
    t2 = client.get(f"/explorer/sources/{src_id}/tariff", headers=headers(ANALYST)).json()
    assert [c["category_code"] for c in t2["categories"]] == sorted([first_cat, second_cat])
    assert t2["release"]["release_number"] == 2
    assert client.get("/explorer/releases", headers=headers(ANALYST)).json()["total"] == 1
    audit = client.get("/audit", params={"entity_type": "data_release"}, headers=headers(ADMIN)).json()
    assert sorted(a["action"] for a in audit) == ["source.publish", "source.publish"]
    assert {a["actor"] for a in audit} == {REVIEWER, ADMIN}
