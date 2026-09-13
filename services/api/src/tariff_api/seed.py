"""Seed the identity registry for the three supplied orders (Section 1.1).

Only identities are seeded - never tariff values.  Idempotent.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Commission, DatasetKind, Jurisdiction, JurisdictionKind, Utility
from .services.sources import get_or_create_dataset

REGISTRY = {
    "jurisdictions": [
        {"code": "UP", "name": "Uttar Pradesh", "kind": "state", "aliases": ["Uttar Pradesh", "U.P."]},
        {"code": "KA", "name": "Karnataka", "kind": "state", "aliases": ["Karnataka"]},
        {"code": "GJ", "name": "Gujarat", "kind": "state", "aliases": ["Gujarat"]},
    ],
    "commissions": [
        {
            "code": "UPERC",
            "name": "Uttar Pradesh Electricity Regulatory Commission",
            "jurisdiction": "UP",
            "aliases": ["UPERC"],
        },
        {
            "code": "KERC",
            "name": "Karnataka Electricity Regulatory Commission",
            "jurisdiction": "KA",
            "aliases": ["KERC", "K.E.R.C."],
        },
        {
            "code": "GERC",
            "name": "Gujarat Electricity Regulatory Commission",
            "jurisdiction": "GJ",
            "aliases": ["GERC"],
        },
    ],
    "utilities": [
        {
            "code": "NPCL",
            "name": "Noida Power Company Limited",
            "commission": "UPERC",
            "licensed_area": "Greater Noida",
            "aliases": ["NPCL", "Noida Power"],
            "profile": "uperc-npcl",
        },
        {
            "code": "BESCOM",
            "name": "Bangalore Electricity Supply Company Limited",
            "commission": "KERC",
            "aliases": ["BESCOM"],
            "profile": "kerc-escoms",
        },
        {
            "code": "MESCOM",
            "name": "Mangalore Electricity Supply Company Limited",
            "commission": "KERC",
            "aliases": ["MESCOM"],
            "profile": "kerc-escoms",
        },
        {
            "code": "CESC",
            "name": "Chamundeshwari Electricity Supply Corporation Limited",
            "commission": "KERC",
            "aliases": ["CESC", "CESCOM"],
            "profile": "kerc-escoms",
        },
        {
            "code": "HESCOM",
            "name": "Hubli Electricity Supply Company Limited",
            "commission": "KERC",
            "aliases": ["HESCOM"],
            "profile": "kerc-escoms",
        },
        {
            "code": "GESCOM",
            "name": "Gulbarga Electricity Supply Company Limited",
            "commission": "KERC",
            "aliases": ["GESCOM"],
            "profile": "kerc-escoms",
        },
        {
            "code": "MGVCL",
            "name": "Madhya Gujarat Vij Company Limited",
            "commission": "GERC",
            "aliases": ["MGVCL"],
            "profile": "gerc-discoms",
        },
        {
            "code": "DGVCL",
            "name": "Dakshin Gujarat Vij Company Limited",
            "commission": "GERC",
            "aliases": ["DGVCL"],
            "profile": "gerc-discoms",
        },
        {
            "code": "PGVCL",
            "name": "Paschim Gujarat Vij Company Limited",
            "commission": "GERC",
            "aliases": ["PGVCL"],
            "profile": "gerc-discoms",
        },
        {
            "code": "UGVCL",
            "name": "Uttar Gujarat Vij Company Limited",
            "commission": "GERC",
            "aliases": ["UGVCL"],
            "profile": "gerc-discoms",
        },
    ],
}


def seed_registry(session: Session) -> dict[str, int]:
    created = {"jurisdictions": 0, "commissions": 0, "utilities": 0}
    real = get_or_create_dataset(session, DatasetKind.real)
    get_or_create_dataset(session, DatasetKind.fixture)
    jmap: dict[str, Jurisdiction] = {}
    for j in REGISTRY["jurisdictions"]:
        row = session.execute(select(Jurisdiction).where(Jurisdiction.code == j["code"])).scalar_one_or_none()
        if row is None:
            row = Jurisdiction(code=j["code"], name=j["name"], kind=JurisdictionKind(j["kind"]), aliases=j["aliases"])
            session.add(row)
            session.flush()
            created["jurisdictions"] += 1
        jmap[j["code"]] = row
    cmap: dict[str, Commission] = {}
    for c in REGISTRY["commissions"]:
        row = session.execute(select(Commission).where(Commission.code == c["code"])).scalar_one_or_none()
        if row is None:
            row = Commission(
                code=c["code"], name=c["name"], jurisdiction_id=jmap[c["jurisdiction"]].id, aliases=c["aliases"]
            )
            session.add(row)
            session.flush()
            created["commissions"] += 1
        cmap[c["code"]] = row
    for u in REGISTRY["utilities"]:
        row = session.execute(select(Utility).where(Utility.code == u["code"])).scalar_one_or_none()
        if row is None:
            row = Utility(
                code=u["code"],
                name=u["name"],
                commission_id=cmap[u["commission"]].id,
                dataset_id=real.id,
                licensed_area=u.get("licensed_area"),
                aliases=u["aliases"],
                active_reading_profile=u.get("profile"),
                active_reading_profile_version=None,
            )
            session.add(row)
            created["utilities"] += 1
    session.flush()
    return created
