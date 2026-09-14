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


def test_synthetic_fixtures_are_byte_reproducible():
    """Dedup, golden manifests and the ingest path all key on SHA-256: a generator whose bytes
    change between calls would make those tests assert nothing."""
    import hashlib

    from fixtures.synthetic_pdfs import mixed_text_and_image_pdf, text_only_pdf

    def sha(b: bytes) -> str:
        return hashlib.sha256(b).hexdigest()

    assert sha(mixed_text_and_image_pdf()) == sha(mixed_text_and_image_pdf())
    assert sha(text_only_pdf(seed="a")) == sha(text_only_pdf(seed="a"))
    assert sha(text_only_pdf(seed="a")) != sha(text_only_pdf(seed="b"))
    # MuPDF writes the regenerated /ID half as a literal string in about one file in fifty;
    # the normaliser must catch that form too, or the hash flickers (seen once in CI order)
    assert len({sha(text_only_pdf(seed="a")) for _ in range(150)}) == 1


def test_fixture_id_normalisation_handles_hex_and_literal_forms():
    from fixtures.synthetic_pdfs import _ZERO_ID, _normalise_id, text_only_pdf

    base = text_only_pdf()
    assert base.count(_ZERO_ID) == 1
    literal = base.replace(_ZERO_ID, b"/ID[<C3A309550C1CC3B9C3BE452270C28CC3>(89$\\005l\\)BIfJ=\\tx(\\\\\\177)]", 1)
    assert literal != base
    assert _normalise_id(literal) == base  # escaped `\)`, `\\` and nested `(` inside the literal
    spaced = base.replace(_ZERO_ID, b"/ID [ <ab> <cd> ]", 1)
    assert _normalise_id(spaced) == base


def test_object_store_listing(tmp_path):
    from tariff_api.adapters.storage import FilesystemObjectStore

    st = FilesystemObjectStore(str(tmp_path))
    st.put("sources", "inbox/order.pdf", b"%PDF-1", "application/pdf")
    st.put("sources", "a" * 64 + ".pdf", b"%PDF-2", "application/pdf")
    keys = [o.key for o in st.list("sources")]
    assert keys == ["a" * 64 + ".pdf", "inbox/order.pdf"]  # sorted, no temp files
    assert [o.key for o in st.list("sources", prefix="inbox/")] == ["inbox/order.pdf"]
    assert st.list("sources", limit=1) == st.list("sources")[:1]
    assert st.list("artefacts") == []
    info = st.list("sources", prefix="inbox/")[0]
    assert info.size_bytes == 6 and info.updated_at is not None


def test_iap_without_an_audience_starts_but_refuses_everything():
    """No domain means no load balancer, so no assertion can be verified.  The service must
    still start (health probes, migrations) and refuse every authenticated request — failing
    closed and saying so, rather than crash-looping or silently letting requests through."""
    from tariff_api.adapters.identity import IapIdentityProvider

    provider = IapIdentityProvider(audience="")
    assert provider.configured is False
    assert "UNCONFIGURED" in provider.description
    assert provider.authenticate({}, lambda e: None) is None
    assert provider.authenticate({"x-goog-iap-jwt-assertion": "anything"}, lambda e: None) is None

    configured = IapIdentityProvider(
        audience=" /projects/1/global/backendServices/2 , /projects/1/global/backendServices/3 "
    )
    assert configured.configured is True
    assert configured.audiences == [
        "/projects/1/global/backendServices/2",
        "/projects/1/global/backendServices/3",
    ]
    assert configured.description == "iap"


def test_processes_that_serve_no_requests_get_no_identity_provider():
    """The worker and the CLI must not be able to authenticate anyone, and must not require an
    identity provider to be configurable at all."""
    from tariff_api.adapters import build_adapters
    from tariff_api.config import Settings

    settings = Settings(deployment_profile="local", identity_backend="local", local_user_allowlist="")
    adapters = build_adapters(settings, include_identity=False)
    assert adapters.identity is None
    assert adapters.describe()["identity"] == "not built (no request path)"
    assert adapters.storage.name == "filesystem"


def test_google_id_token_identity_verifies_audience_issuer_and_email(monkeypatch):
    """No domain (ADR-0015): the API accepts a Google-signed ID token naming one of our own
    service URLs, forwarded by the web app or sent directly.  Unverified emails, foreign
    audiences and unregistered users never become a usable principal; verification itself
    is delegated to google-auth and substituted here."""
    from tariff_api.adapters.identity import GoogleIdTokenIdentityProvider
    from tariff_api.models import UserRole

    unconfigured = GoogleIdTokenIdentityProvider(audiences="")
    assert unconfigured.configured is False and "UNCONFIGURED" in unconfigured.description
    assert unconfigured.authenticate({"authorization": "Bearer x"}, lambda e: UserRole.reviewer) is None

    p = GoogleIdTokenIdentityProvider(
        audiences="https://tariff-web-1.asia-south1.run.app/, https://tariff-api-1.asia-south1.run.app"
    )
    assert p.audiences == ["https://tariff-web-1.asia-south1.run.app", "https://tariff-api-1.asia-south1.run.app"]
    seen: list[str] = []
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "https://tariff-web-1.asia-south1.run.app",
        "email": "Reviewer@Example.com",
        "email_verified": True,
        "name": "R",
    }

    def fake_verify(token: str):
        seen.append(token)
        return dict(claims) if token == "good" else None

    monkeypatch.setattr(p, "verify", fake_verify)
    roles = {"reviewer@example.com": UserRole.reviewer}
    lookup = roles.get
    # the forwarded user header wins over the bearer used for the call itself
    pr = p.authenticate({"x-user-id-token": "good", "authorization": "Bearer service"}, lookup)
    assert pr is not None and pr.email == "reviewer@example.com" and pr.role == UserRole.reviewer
    assert pr.provider == "google_id_token" and seen == ["good"]
    # a direct call uses the bearer
    assert p.authenticate({"authorization": "Bearer good"}, lookup).email == "reviewer@example.com"
    # a token google-auth rejects (wrong audience, expired, bad signature) is unauthenticated
    assert p.authenticate({"authorization": "Bearer bad"}, lookup) is None
    # unverified email, wrong issuer
    claims["email_verified"] = False
    assert p.authenticate({"x-user-id-token": "good"}, lookup) is None
    claims["email_verified"] = True
    claims["iss"] = "https://evil.example"
    assert p.authenticate({"x-user-id-token": "good"}, lookup) is None
    claims["iss"] = "accounts.google.com"
    # verified but not registered: flagged so the API answers permission_denied, not analyst access
    pr = p.authenticate({"x-user-id-token": "good"}, lambda e: None)
    assert pr is not None and pr.provider.endswith(":unregistered")
    assert p.authenticate({}, lookup) is None


def test_gcp_profile_accepts_google_id_token_backend():
    from tariff_api.config import IdentityBackend, Settings

    s = Settings(
        deployment_profile="gcp",
        identity_backend="google_id_token",
        object_store_backend="gcs",
        secrets_backend="secret_manager",
        gcp_project_id="p",
        source_bucket="s",
        artefact_bucket="a",
        id_token_audiences="https://x.run.app",
    )
    s.validate_profile()
    assert s.identity_backend == IdentityBackend.google_id_token
