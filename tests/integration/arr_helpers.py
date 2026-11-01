"""Shared steps for ARR integration tests: a SYNTHETIC licensee in the SYNTHETIC commission,
and its synthetic ARR order read, reviewed by the test harness's reviewers and published.
Fixture data only; never a real licensee."""

from __future__ import annotations

from sqlalchemy import select

from conftest import ADMIN, REVIEWER, headers
from fixtures.synthetic_pdfs import arr_order_pdf, arr_regulation_pdf

COMMISSION = "SYNTHERC"


def run_all(runner) -> int:
    n = 0
    while runner.run_once():
        n += 1
    return n


def ensure_licensee(code: str) -> None:
    from tariff_api.db import session_scope
    from tariff_api.models import Commission, DatasetKind, Jurisdiction, JurisdictionKind, Utility
    from tariff_api.services.sources import get_or_create_dataset

    with session_scope() as s:
        if s.execute(select(Utility).where(Utility.code == code)).scalar_one_or_none():
            return
        c = s.execute(select(Commission).where(Commission.code == COMMISSION)).scalar_one_or_none()
        if c is None:
            j = s.execute(select(Jurisdiction).where(Jurisdiction.code == "SYN")).scalar_one_or_none()
            if j is None:
                j = Jurisdiction(code="SYN", name="SYNTHETIC jurisdiction", kind=JurisdictionKind.state)
                s.add(j)
                s.flush()
            c = Commission(code=COMMISSION, name="SYNTHETIC Electricity Regulatory Commission", jurisdiction_id=j.id)
            s.add(c)
            s.flush()
        s.add(
            Utility(
                code=code,
                name=f"SYNTHETIC licensee {code}",
                commission_id=c.id,
                dataset_id=get_or_create_dataset(s, DatasetKind.fixture).id,
                licensee_kind="distribution",
            )
        )


def upload(client, data: bytes, name: str, **form: str) -> str:
    r = client.post(
        "/sources",
        files={"file": (name, data, "application/pdf")},
        data={"dataset_kind": "fixture", **form},
        headers=headers(ADMIN),
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["source"]["id"]


def decide(client, cand: dict, outcome: str, user: str, rationale: str | None = None) -> dict:
    r = client.get(f"/candidates/{cand['id']}/evidence/0/image", headers=headers(user))
    assert r.status_code == 200, r.text
    body = {
        "outcome": outcome,
        "expected_version": cand["version"],
        "evidence_view_ids": [r.headers["x-evidence-view-id"]],
    }
    if rationale:
        body["rationale"] = rationale
    r = client.post(f"/candidates/{cand['id']}/decision", json=body, headers=headers(user))
    assert r.status_code == 200, r.text
    return client.get(f"/candidates/{cand['id']}", headers=headers(user)).json()


def read_and_publish(client, runner, licensee: str) -> tuple[str, str]:
    """(order source id, regulation source id) with the order's ARR published for the licensee."""
    ensure_licensee(licensee)
    order = upload(client, arr_order_pdf(licensee), f"SYNTHETIC_arr_order_{licensee}.pdf", utility_code=licensee)
    regulation = upload(client, arr_regulation_pdf(), "SYNTHETIC_arr_regulation.pdf", order_type="regulation")
    run_all(runner)
    assert client.post(f"/sources/{order}/arr/read", headers=headers(ADMIN)).status_code == 202
    run_all(runner)
    r = client.post(
        f"/sources/{order}/arr/chapters/decision", json={"rationale": "chapters checked"}, headers=headers(REVIEWER)
    )
    assert r.status_code == 200, r.text
    run_all(runner)
    reading = client.get(f"/sources/{order}/arr", headers=headers(REVIEWER)).json()
    bad = {i for f in reading["findings"] if f["severity"] == "blocking" for i in f["candidate_ids"]}
    for c in client.get(f"/sources/{order}/arr/candidates", headers=headers(REVIEWER)).json()["candidates"]:
        if c["id"] in bad and c["record"]["line_code"] == "C.TOTAL":
            decide(client, c, "reject", REVIEWER, "printed total does not add up")
            continue
        c = decide(client, c, "approve", REVIEWER)
        if c["review_status"] == "awaiting_second_review":
            decide(client, c, "approve", ADMIN)
    run_all(runner)
    r = client.post(f"/sources/{order}/arr/publish", headers=headers(REVIEWER))
    assert r.status_code == 200, r.text
    return order, regulation
