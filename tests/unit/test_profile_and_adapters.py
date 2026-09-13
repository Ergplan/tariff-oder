"""Portability contract: the local identity adapter refuses the gcp profile; the gcp profile
refuses local-only adapters; the error taxonomy is complete."""

from __future__ import annotations

import pytest


def test_local_identity_refuses_gcp_profile():
    from tariff_api.adapters.identity import LocalIdentityProvider

    with pytest.raises(RuntimeError, match="refuses to run under DEPLOYMENT_PROFILE=gcp"):
        LocalIdentityProvider(profile="gcp", allowlist={"a@b.c": "analyst"})
    with pytest.raises(RuntimeError, match="allow-list"):
        LocalIdentityProvider(profile="local", allowlist={})


def test_local_identity_requires_allowlisted_email():
    from tariff_api.adapters.identity import LocalIdentityProvider

    p = LocalIdentityProvider(profile="local", allowlist={"Admin@Example.com": "administrator"})
    assert p.authenticate({}, lambda e: None) is None
    assert p.authenticate({"x-local-user": "nobody@example.com"}, lambda e: None) is None
    principal = p.authenticate({"x-local-user": "ADMIN@example.com"}, lambda e: None)
    assert principal is not None and principal.role.value == "administrator"


def test_gcp_profile_rejects_local_adapters():
    from tariff_api.config import Settings

    s = Settings(
        deployment_profile="gcp", identity_backend="local", object_store_backend="filesystem", secrets_backend="env"
    )
    with pytest.raises(RuntimeError) as e:
        s.validate_profile()
    msg = str(e.value)
    assert "identity_backend=local" in msg and "filesystem" in msg and "secrets_backend=env" in msg
    ok = Settings(
        deployment_profile="gcp",
        identity_backend="iap",
        iap_audience="/projects/1/global/backendServices/2",
        object_store_backend="gcs",
        secrets_backend="secret_manager",
        gcp_project_id="p",
        source_bucket="s",
        artefact_bucket="a",
    )
    ok.validate_profile()


def test_error_taxonomy_covers_spec_types():
    from tariff_api.errors import ERROR_TAXONOMY, AppError

    required = {
        "source_unreadable",
        "page_low_quality",
        "localisation_ambiguous",
        "reader_disagreement",
        "provider_unavailable",
        "budget_exceeded",
        "validation_failed",
        "permission_denied",
        "conflict_stale_version",
        "coverage_insufficient",
        "idempotency_conflict",
        "retries_exhausted",
    }
    assert required <= set(ERROR_TAXONOMY)
    for spec in ERROR_TAXONOMY.values():
        assert spec.user_message and spec.next_step and spec.severity in {"info", "warning", "error", "critical"}
    with pytest.raises(ValueError):
        AppError("not_a_real_type")


def test_filesystem_store_is_immutable_and_safe(tmp_path):
    from tariff_api.adapters.storage import FilesystemObjectStore, ObjectNotFound

    st = FilesystemObjectStore(str(tmp_path))
    st.put("sources", "abc.pdf", b"one", "application/pdf")
    st.put("sources", "abc.pdf", b"two", "application/pdf")  # ignored: content-addressed keys never change
    assert st.get("sources", "abc.pdf") == b"one"
    assert b"".join(st.stream("sources", "abc.pdf", chunk_size=1)) == b"one"
    assert st.exists("sources", "abc.pdf") and not st.exists("sources", "nope")
    with pytest.raises(ObjectNotFound):
        st.get("sources", "nope")
    with pytest.raises(ValueError):
        st.get("sources", "../escape")
    assert st.health()["ok"] is True


def test_golden_manifest_compare():
    from tariff_api import golden

    entry = {"id": "x", "expected": {"page_count": 423, "size_bytes": 10, "pages_without_text_layer": 22}}
    res = golden.compare_inventory(entry, {"page_count": 423, "size_bytes": 10, "pages_without_text": 21})
    assert res["checks"]["page_count"]["match"] is True
    assert res["checks"]["pages_without_text_layer"]["match"] is False
    assert res["all_match"] is False


def test_manifest_file_lists_three_supplied_orders():
    import json
    from pathlib import Path

    m = json.loads((Path(__file__).resolve().parents[1] / "golden" / "manifest.json").read_text())
    ids = {e["id"] for e in m["entries"]}
    assert ids == {"npcl-fy2026-27", "kerc-fy2025-28", "gerc-mgvcl-fy2026-27"}
    assert all(len(e["sha256"]) == 64 and e["bytes_present"] is False for e in m["entries"])


def test_inventory_of_synthetic_fixture_direct():
    from fixtures.synthetic_pdfs import mixed_text_and_image_pdf
    from tariff_api.inventory import document_inventory, open_document, page_inventory

    doc = open_document(mixed_text_and_image_pdf())
    info = document_inventory(doc)
    assert info.page_count == 6 and info.is_encrypted is False and info.tool == "pymupdf"
    pages = [page_inventory(doc, i) for i in range(6)]
    assert [p.has_text_layer for p in pages] == [True, True, True, True, False, False]
    assert [p.printed_label for p in pages] == ["i", "ii", "1", "2", "3", "4"]
    assert pages[2].rotation == 90
