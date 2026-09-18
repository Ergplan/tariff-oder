"""Milestone 1 gate: upload -> register -> inventory -> authorized reopen -> deduplicate."""

from __future__ import annotations

import hashlib

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import mixed_text_and_image_pdf, not_a_pdf, plain_text_bytes, text_only_pdf

pytestmark = pytest.mark.integration


def _upload(client, data: bytes, user=ADMIN, name="SYNTHETIC.pdf", dataset="fixture", **hdrs):
    return client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": dataset},
        headers=headers(user, **hdrs),
    )


def test_upload_inventory_reopen_and_dedup(client, runner):
    data = mixed_text_and_image_pdf()
    sha = hashlib.sha256(data).hexdigest()

    r = _upload(client, data)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["deduplicated"] is False
    src = body["source"]
    assert src["sha256"] == sha
    assert src["state"] == "uploaded"
    assert src["dataset_kind"] == "fixture"
    assert src["page_count"] is None  # no inventory yet - never guessed
    assert body["job"]["job_type"] == "inventory_source"
    assert body["job"]["status"] == "queued"

    # Worker processes the inventory job with page-level checkpoints (every 2 pages); inventory
    # chains the triage stage automatically, which we also run so the queue ends up empty.
    assert runner.run_once() is True  # inventory
    assert runner.run_once() is True  # triage (Milestone 2a)
    assert runner.run_once() is True  # parse (Milestone 2b)
    assert runner.run_once() is True  # localise (Milestone 3a): no profile detectable, halts visibly
    assert runner.run_once() is False  # queue empty

    d = client.get(f"/sources/{src['id']}", headers=headers(REVIEWER)).json()
    assert d["state"] == "localised"  # inventory -> triage -> parse -> localise, all chained
    assert d["localisation"]["status"] == "ambiguous"  # a fixture with no schedule headings: no profile, no guess
    assert d["page_count"] == 6
    assert d["pages_with_text"] == 4
    assert d["pages_without_text"] == 2
    assert d["text_layer_summary"]["pages_without_text_layer"] == ["5-6"]
    assert d["text_layer_summary"]["rotated_pages"] == 1
    assert d["inventory_tool"] == "pymupdf"
    assert d["inventory_tool_version"]
    assert d["latest_job"]["status"] == "succeeded"
    assert d["latest_job"]["progress"]["pages_done"] == 6
    assert d["producer"] == "synthetic-fixture-generator"

    pages = client.get(f"/sources/{src['id']}/pages", headers=headers(ANALYST)).json()
    assert pages["total"] == 6
    by_index = {p["page_index"]: p for p in pages["pages"]}
    assert [by_index[i]["printed_label"] for i in range(1, 7)] == ["i", "ii", "1", "2", "3", "4"]
    assert by_index[3]["rotation"] == 90
    assert all(by_index[i]["has_text_layer"] for i in (1, 2, 3, 4))
    assert all(not by_index[i]["has_text_layer"] for i in (5, 6))
    assert by_index[5]["image_count"] == 1
    assert all(p["page_role"] == "unknown" for p in pages["pages"])  # localisation is Milestone 3

    # Authorized reopen returns the identical bytes
    f = client.get(f"/sources/{src['id']}/file", headers=headers(ANALYST))
    assert f.status_code == 200
    assert f.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(f.content).hexdigest() == sha

    # Identical second upload is deduplicated, not re-registered
    r2 = _upload(client, data, name="different-name.pdf")
    assert r2.status_code == 200
    assert r2.json()["deduplicated"] is True
    assert r2.json()["source"]["id"] == src["id"]
    listing = client.get("/sources", headers=headers(ANALYST)).json()
    assert listing["total"] == 1

    audit = client.get(
        "/audit", params={"entity_type": "source_document", "entity_id": src["id"]}, headers=headers(ADMIN)
    ).json()
    actions = [a["action"] for a in audit]
    assert "source.registered" in actions
    assert "source.deduplicated" in actions
    assert "source.transition" in actions

    # Job events show the checkpoint trail (of the inventory job)
    job = client.get(f"/jobs/{body['job']['id']}", headers=headers(ANALYST)).json()
    events = [e["event"] for e in job["events"]]
    assert events[0] == "enqueued"
    assert "claimed" in events
    assert events.count("checkpoint") >= 3
    assert events[-1] == "succeeded"


def test_unauthenticated_and_role_enforcement(client):
    data = text_only_pdf(seed="roles")
    assert client.get("/sources").status_code == 401
    assert client.get("/sources", headers={"X-Local-User": "stranger@example.com"}).status_code == 401
    r = _upload(client, data, user=ANALYST)
    assert r.status_code == 403
    assert r.json()["error_type"] == "permission_denied"
    assert r.json()["request_id"]
    r = _upload(client, data, user=REVIEWER)
    assert r.status_code == 403
    assert _upload(client, data, user=ADMIN).status_code == 201
    src_id = client.get("/sources", headers=headers(ANALYST)).json()["items"][0]["id"]
    assert client.get(f"/sources/{src_id}/file").status_code == 401
    assert client.get(f"/sources/{src_id}/file", headers=headers(ANALYST)).status_code == 200
    assert client.get("/users", headers=headers(REVIEWER)).status_code == 403
    assert client.get("/audit", headers=headers(ANALYST)).status_code == 403
    me = client.get("/me", headers=headers(REVIEWER)).json()
    assert me == {"email": REVIEWER, "role": "reviewer", "provider": "local"}


def test_idempotent_upload(client):
    data = text_only_pdf(seed="idem")
    r1 = _upload(client, data, **{"Idempotency-Key": "k-1"})
    assert r1.status_code == 201
    r2 = _upload(client, data, **{"Idempotency-Key": "k-1"})
    assert r2.status_code == 201  # replayed original status
    assert r2.json()["idempotent_replay"] is True
    assert r2.json()["source"]["id"] == r1.json()["source"]["id"]
    # same key, different bytes -> conflict, nothing registered
    r3 = _upload(client, text_only_pdf(seed="other"), **{"Idempotency-Key": "k-1"})
    assert r3.status_code == 409
    assert r3.json()["error_type"] == "idempotency_conflict"
    assert client.get("/sources", headers=headers(ANALYST)).json()["total"] == 1
    # exactly one inventory job for the source
    jobs = client.get("/jobs", headers=headers(ANALYST)).json()
    assert jobs["total"] == 1


def test_unreadable_and_non_pdf_are_typed_failures(client):
    r = _upload(client, plain_text_bytes())
    assert r.status_code == 422
    assert r.json()["error_type"] == "source_unreadable"
    r = _upload(client, not_a_pdf())
    assert r.status_code == 422
    assert r.json()["error_type"] == "source_unreadable"
    assert client.get("/sources", headers=headers(ANALYST)).json()["total"] == 0


def test_fixture_and_real_datasets_are_separate(client):
    _upload(client, text_only_pdf(seed="fx"), dataset="fixture")
    _upload(client, text_only_pdf(seed="real"), dataset="real")
    assert client.get("/sources", params={"dataset_kind": "fixture"}, headers=headers(ANALYST)).json()["total"] == 1
    assert client.get("/sources", params={"dataset_kind": "real"}, headers=headers(ANALYST)).json()["total"] == 1
    items = client.get("/sources", headers=headers(ANALYST)).json()["items"]
    assert {i["dataset_kind"] for i in items} == {"fixture", "real"}
    status = client.get("/status", headers=headers(ANALYST)).json()
    assert status["datasets"] == {"fixture": 1, "real": 1}
    assert status["deployment_profile"] == "local"
    assert status["adapters"] == {"storage": "filesystem", "secrets": "env", "identity": "local"}
    assert status["database"]["migration_head"]  # whatever alembic's head is; replay is tested elsewhere
    assert status["database"]["pgvector_version"]


def test_health_and_readiness(client):
    assert client.get("/healthz").json()["status"] == "ok"
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"
    assert r.json()["database"]["ok"] and r.json()["storage"]["ok"]


def test_registry_seed_and_utility_creation(client):
    from tariff_api.db import session_scope
    from tariff_api.seed import seed_registry

    with session_scope() as s:
        created = seed_registry(s)
    from tariff_api.seed import REGISTRY

    assert created == {k: len(REGISTRY[k]) for k in ("jurisdictions", "commissions", "utilities")}
    assert created["commissions"] == 29 and created["utilities"] >= 60
    with session_scope() as s:
        assert seed_registry(s) == {"jurisdictions": 0, "commissions": 0, "utilities": 0}
    reg = client.get("/registry", headers=headers(ANALYST)).json()
    assert {u["code"] for u in reg["utilities"]} >= {"NPCL", "BESCOM", "MGVCL"}
    assert all(u["dataset_kind"] == "real" for u in reg["utilities"])
    r = client.post(
        "/utilities",
        json={"code": "FIXCO", "name": "Fixture Utility", "commission_code": "UPERC", "dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201 and r.json()["dataset_kind"] == "fixture"
    assert (
        client.post(
            "/utilities", json={"code": "X2", "name": "x", "commission_code": "NOPE"}, headers=headers(ADMIN)
        ).status_code
        == 422
    )


def test_reprocess_and_cancel(client, runner):
    r = _upload(client, text_only_pdf(seed="rp"))
    src_id = r.json()["source"]["id"]
    job_id = r.json()["job"]["id"]
    c = client.post(f"/jobs/{job_id}/cancel", headers=headers(ADMIN))
    assert c.json()["result"] == "cancelled"
    assert runner.run_once() is False
    assert client.post(f"/jobs/{job_id}/cancel", headers=headers(ADMIN)).status_code == 409
    # reprocess is not allowed while still 'uploaded' with a cancelled job? It is: state is uploaded.
    # The transition table forbids uploaded->uploaded, so reprocess requires failed/needs_reprocessing/inventoried.
    rp = client.post(f"/sources/{src_id}/reprocess", headers=headers(ADMIN))
    assert rp.status_code == 409
    assert rp.json()["error_type"] == "invalid_transition"
