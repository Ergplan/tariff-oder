"""Bucket ingest: registering tariff orders that an operator placed in the source bucket.

This is the cloud ingestion route (the PDFs are copied into `tarifforderstudio_sources`,
not uploaded through a browser).  The object's name is never trusted as identity: the bytes
are re-read and hashed, so dedup, the golden-manifest check and the inventory job behave
exactly as they do for an upload.
"""

from __future__ import annotations

import hashlib

import pytest

from conftest import ADMIN, ANALYST, REVIEWER, headers
from fixtures.synthetic_pdfs import mixed_text_and_image_pdf, plain_text_bytes, text_only_pdf

pytestmark = pytest.mark.integration


def _put(storage, key: str, data: bytes) -> None:
    """Simulate the operator's `gcloud storage cp` into the source bucket."""
    storage.put("sources", key, data, "application/pdf")


def test_inbox_lists_objects_and_registration_state(client, storage):
    _put(storage, "inbox/NPCL_TariffOrder.pdf", mixed_text_and_image_pdf())
    _put(storage, "inbox/notes.txt.pdf", text_only_pdf(seed="notes"))

    inbox = client.get("/sources/inbox", headers=headers(ADMIN)).json()
    assert inbox["bucket_role"] == "sources"
    assert inbox["total"] == 2
    keys = {o["object_key"]: o for o in inbox["objects"]}
    assert set(keys) == {"inbox/NPCL_TariffOrder.pdf", "inbox/notes.txt.pdf"}
    assert all(o["registered"] is False and o["source_id"] is None for o in keys.values())
    assert keys["inbox/NPCL_TariffOrder.pdf"]["size_bytes"] > 0
    assert keys["inbox/NPCL_TariffOrder.pdf"]["is_content_addressed_copy"] is False

    # Only administrators may see or ingest from the bucket
    assert client.get("/sources/inbox", headers=headers(REVIEWER)).status_code == 403
    assert client.get("/sources/inbox").status_code == 401


def test_ingest_registers_hashes_and_inventories(client, storage, runner):
    data = mixed_text_and_image_pdf()
    sha = hashlib.sha256(data).hexdigest()
    _put(storage, "inbox/NPCL_TariffOrder.pdf", data)

    r = client.post(
        "/sources/ingest",
        json={"object_key": "inbox/NPCL_TariffOrder.pdf", "dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["deduplicated"] is False
    src = body["source"]
    assert src["sha256"] == sha  # hashed from the bytes, not taken from the object name
    assert src["original_filename"] == "NPCL_TariffOrder.pdf"
    assert src["state"] == "uploaded"
    assert src["page_count"] is None
    assert body["job"]["job_type"] == "inventory_source"

    assert runner.run_once() is True
    detail = client.get(f"/sources/{src['id']}", headers=headers(ANALYST)).json()
    assert detail["state"] == "inventoried"
    assert detail["page_count"] == 6
    assert detail["pages_without_text"] == 2
    # The registered copy lives under its content-addressed key; the inbox object stays put
    assert detail["object_key"] == f"{sha}.pdf"

    inbox = client.get("/sources/inbox", headers=headers(ADMIN)).json()
    by_key = {o["object_key"]: o for o in inbox["objects"]}
    assert by_key["inbox/NPCL_TariffOrder.pdf"]["registered"] is False  # the operator's copy
    assert by_key[f"{sha}.pdf"]["registered"] is True
    assert by_key[f"{sha}.pdf"]["source_id"] == src["id"]
    assert by_key[f"{sha}.pdf"]["is_content_addressed_copy"] is True


def test_ingesting_the_same_bytes_twice_deduplicates(client, storage):
    data = text_only_pdf(seed="dup")
    _put(storage, "inbox/first.pdf", data)
    _put(storage, "inbox/second-copy-of-the-same-order.pdf", data)

    first = client.post(
        "/sources/ingest", json={"object_key": "inbox/first.pdf", "dataset_kind": "fixture"}, headers=headers(ADMIN)
    )
    assert first.status_code == 201
    second = client.post(
        "/sources/ingest",
        json={"object_key": "inbox/second-copy-of-the-same-order.pdf", "dataset_kind": "fixture"},
        headers=headers(ADMIN),
    )
    assert second.status_code == 200
    assert second.json()["deduplicated"] is True
    assert second.json()["source"]["id"] == first.json()["source"]["id"]
    assert client.get("/sources", headers=headers(ANALYST)).json()["total"] == 1


def test_console_folder_placeholder_is_not_a_candidate(client, storage):
    """Making the `inbox` folder in the Cloud console creates a zero-byte object named
    `inbox/`.  The listing must not offer it and ingest must refuse it before touching bytes."""
    from datetime import UTC, datetime

    from tariff_api.adapters.storage import ObjectInfo
    from tariff_api.db import session_scope
    from tariff_api.services import sources as svc

    class BucketWithPlaceholder:
        def list(self, bucket, prefix="", limit=1000):
            rows = [ObjectInfo("inbox/", 0, datetime.now(UTC)), ObjectInfo("inbox/order.pdf", 5, datetime.now(UTC))]
            return [o for o in rows if o.key.startswith(prefix)][:limit]

    with session_scope() as s:
        listed = svc.list_inbox(s, BucketWithPlaceholder())
    assert [o["object_key"] for o in listed] == ["inbox/order.pdf"]

    r = client.post("/sources/ingest", json={"object_key": "inbox/"}, headers=headers(ADMIN))
    assert r.status_code == 422 and r.json()["error_type"] == "validation_failed"
    assert client.get("/sources", headers=headers(ANALYST)).json()["total"] == 0


def test_ingest_idempotency_and_missing_or_unreadable_objects(client, storage):
    _put(storage, "inbox/a.pdf", text_only_pdf(seed="idem-a"))
    _put(storage, "inbox/b.pdf", text_only_pdf(seed="idem-b"))
    _put(storage, "inbox/not-a-pdf.pdf", plain_text_bytes())

    hdr = {**headers(ADMIN), "Idempotency-Key": "ing-1"}
    r1 = client.post("/sources/ingest", json={"object_key": "inbox/a.pdf", "dataset_kind": "fixture"}, headers=hdr)
    assert r1.status_code == 201
    r2 = client.post("/sources/ingest", json={"object_key": "inbox/a.pdf", "dataset_kind": "fixture"}, headers=hdr)
    assert r2.status_code == 201 and r2.json()["idempotent_replay"] is True
    r3 = client.post("/sources/ingest", json={"object_key": "inbox/b.pdf", "dataset_kind": "fixture"}, headers=hdr)
    assert r3.status_code == 409 and r3.json()["error_type"] == "idempotency_conflict"

    missing = client.post("/sources/ingest", json={"object_key": "inbox/nope.pdf"}, headers=headers(ADMIN))
    assert missing.status_code == 404 and missing.json()["error_type"] == "not_found"

    bad = client.post("/sources/ingest", json={"object_key": "inbox/not-a-pdf.pdf"}, headers=headers(ADMIN))
    assert bad.status_code == 422 and bad.json()["error_type"] == "source_unreadable"

    assert client.get("/sources", headers=headers(ANALYST)).json()["total"] == 1


def test_cli_ingest_and_user_commands(storage, runner, client):
    """The operational CLI is how sources are registered in the cloud, where the API has no
    public ingress: it runs as a Cloud Run Job inside the VPC."""
    from tariff_api.cli import main as cli_main

    _put(storage, "inbox/KERC_order.pdf", text_only_pdf(seed="cli"))

    assert cli_main(["inbox"]) == 0
    assert cli_main(["ingest", "inbox/KERC_order.pdf", "--dataset", "fixture", "--actor", "ops@example.com"]) == 0
    # A non-email actor is refused: the audit trail must name a person, not a process
    assert cli_main(["ingest", "inbox/KERC_order.pdf", "--dataset", "fixture", "--actor", "root"]) == 2

    listing = client.get("/sources", headers=headers(ANALYST)).json()
    assert listing["total"] == 1
    assert listing["items"][0]["uploaded_by"] == "ops@example.com"

    assert runner.run_once() is True
    detail = client.get(f"/sources/{listing['items'][0]['id']}", headers=headers(ANALYST)).json()
    assert detail["state"] == "inventoried"

    assert cli_main(["users", "add", "--email", "Ops@Example.com", "--role", "administrator", "--actor", "cli"]) == 0
    assert cli_main(["users", "list"]) == 0
    users = client.get("/users", headers=headers(ADMIN)).json()
    assert [(u["email"], u["role"]) for u in users] == [("ops@example.com", "administrator")]
    audit = client.get("/audit", params={"entity_type": "user"}, headers=headers(ADMIN)).json()
    assert audit[0]["action"] == "user.created"
