"""Seed the identity registry: every commission in India and the distribution licensees.

Only identities are seeded - never tariff values.  Idempotent.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Commission, DatasetKind, Jurisdiction, JurisdictionKind, Utility
from .services.sources import get_or_create_dataset

REGISTRY = {
    # Identities only — never tariff values.  Every state and joint commission, and the
    # distribution licensees an operator will upload orders for; names are as commonly used
    # in 2026 and can be corrected on the Registry page.  Idempotent: existing rows are kept.
    "jurisdictions": [
        {"code": "AP", "name": "Andhra Pradesh", "kind": "state", "aliases": ["Andhra Pradesh"]},
        {"code": "AR", "name": "Arunachal Pradesh", "kind": "state", "aliases": ["Arunachal Pradesh"]},
        {"code": "AS", "name": "Assam", "kind": "state", "aliases": ["Assam"]},
        {"code": "BR", "name": "Bihar", "kind": "state", "aliases": ["Bihar"]},
        {"code": "CG", "name": "Chhattisgarh", "kind": "state", "aliases": ["Chhattisgarh"]},
        {"code": "DL", "name": "Delhi", "kind": "union_territory", "aliases": ["Delhi"]},
        {"code": "GJ", "name": "Gujarat", "kind": "state", "aliases": ["Gujarat"]},
        {"code": "HR", "name": "Haryana", "kind": "state", "aliases": ["Haryana"]},
        {"code": "HP", "name": "Himachal Pradesh", "kind": "state", "aliases": ["Himachal Pradesh"]},
        {
            "code": "JKL",
            "name": "Jammu & Kashmir and Ladakh",
            "kind": "union_territory",
            "aliases": ["Jammu & Kashmir and Ladakh"],
        },
        {"code": "JH", "name": "Jharkhand", "kind": "state", "aliases": ["Jharkhand"]},
        {"code": "KA", "name": "Karnataka", "kind": "state", "aliases": ["Karnataka"]},
        {"code": "KL", "name": "Kerala", "kind": "state", "aliases": ["Kerala"]},
        {"code": "MP", "name": "Madhya Pradesh", "kind": "state", "aliases": ["Madhya Pradesh"]},
        {"code": "MH", "name": "Maharashtra", "kind": "state", "aliases": ["Maharashtra"]},
        {"code": "MNMZ", "name": "Manipur and Mizoram", "kind": "state", "aliases": ["Manipur and Mizoram"]},
        {"code": "ML", "name": "Meghalaya", "kind": "state", "aliases": ["Meghalaya"]},
        {"code": "NL", "name": "Nagaland", "kind": "state", "aliases": ["Nagaland"]},
        {"code": "OD", "name": "Odisha", "kind": "state", "aliases": ["Odisha"]},
        {"code": "PB", "name": "Punjab", "kind": "state", "aliases": ["Punjab"]},
        {"code": "RJ", "name": "Rajasthan", "kind": "state", "aliases": ["Rajasthan"]},
        {"code": "SK", "name": "Sikkim", "kind": "state", "aliases": ["Sikkim"]},
        {"code": "TN", "name": "Tamil Nadu", "kind": "state", "aliases": ["Tamil Nadu"]},
        {"code": "TG", "name": "Telangana", "kind": "state", "aliases": ["Telangana"]},
        {"code": "TR", "name": "Tripura", "kind": "state", "aliases": ["Tripura"]},
        {"code": "UP", "name": "Uttar Pradesh", "kind": "state", "aliases": ["Uttar Pradesh"]},
        {"code": "UK", "name": "Uttarakhand", "kind": "state", "aliases": ["Uttarakhand"]},
        {"code": "WB", "name": "West Bengal", "kind": "state", "aliases": ["West Bengal"]},
        {
            "code": "GOAUT",
            "name": "Goa and Union Territories",
            "kind": "union_territory",
            "aliases": ["Goa and Union Territories"],
        },
    ],
    "commissions": [
        {
            "code": "APERC",
            "name": "Andhra Pradesh Electricity Regulatory Commission",
            "jurisdiction": "AP",
            "aliases": ["APERC"],
        },
        {
            "code": "APSERC",
            "name": "Arunachal Pradesh State Electricity Regulatory Commission",
            "jurisdiction": "AR",
            "aliases": ["APSERC", "Arunachal Pradesh ERC"],
        },
        {"code": "AERC", "name": "Assam Electricity Regulatory Commission", "jurisdiction": "AS", "aliases": ["AERC"]},
        {"code": "BERC", "name": "Bihar Electricity Regulatory Commission", "jurisdiction": "BR", "aliases": ["BERC"]},
        {
            "code": "CSERC",
            "name": "Chhattisgarh State Electricity Regulatory Commission",
            "jurisdiction": "CG",
            "aliases": ["CSERC"],
        },
        {"code": "DERC", "name": "Delhi Electricity Regulatory Commission", "jurisdiction": "DL", "aliases": ["DERC"]},
        {
            "code": "GERC",
            "name": "Gujarat Electricity Regulatory Commission",
            "jurisdiction": "GJ",
            "aliases": ["GERC"],
        },
        {
            "code": "HERC",
            "name": "Haryana Electricity Regulatory Commission",
            "jurisdiction": "HR",
            "aliases": ["HERC"],
        },
        {
            "code": "HPERC",
            "name": "Himachal Pradesh Electricity Regulatory Commission",
            "jurisdiction": "HP",
            "aliases": ["HPERC"],
        },
        {
            "code": "JERC-JKL",
            "name": "Joint Electricity Regulatory Commission for Jammu & Kashmir and Ladakh",
            "jurisdiction": "JKL",
            "aliases": ["JERC (J&K and Ladakh)", "JKERC"],
        },
        {
            "code": "JSERC",
            "name": "Jharkhand State Electricity Regulatory Commission",
            "jurisdiction": "JH",
            "aliases": ["JSERC"],
        },
        {
            "code": "KERC",
            "name": "Karnataka Electricity Regulatory Commission",
            "jurisdiction": "KA",
            "aliases": ["KERC", "K.E.R.C."],
        },
        {
            "code": "KSERC",
            "name": "Kerala State Electricity Regulatory Commission",
            "jurisdiction": "KL",
            "aliases": ["KSERC"],
        },
        {
            "code": "MPERC",
            "name": "Madhya Pradesh Electricity Regulatory Commission",
            "jurisdiction": "MP",
            "aliases": ["MPERC"],
        },
        {
            "code": "MERC",
            "name": "Maharashtra Electricity Regulatory Commission",
            "jurisdiction": "MH",
            "aliases": ["MERC"],
        },
        {
            "code": "JERC-MM",
            "name": "Joint Electricity Regulatory Commission for Manipur and Mizoram",
            "jurisdiction": "MNMZ",
            "aliases": ["JERC (Manipur & Mizoram)"],
        },
        {
            "code": "MSERC",
            "name": "Meghalaya State Electricity Regulatory Commission",
            "jurisdiction": "ML",
            "aliases": ["MSERC"],
        },
        {
            "code": "NERC",
            "name": "Nagaland Electricity Regulatory Commission",
            "jurisdiction": "NL",
            "aliases": ["NERC"],
        },
        {"code": "OERC", "name": "Odisha Electricity Regulatory Commission", "jurisdiction": "OD", "aliases": ["OERC"]},
        {
            "code": "PSERC",
            "name": "Punjab State Electricity Regulatory Commission",
            "jurisdiction": "PB",
            "aliases": ["PSERC"],
        },
        {
            "code": "RERC",
            "name": "Rajasthan Electricity Regulatory Commission",
            "jurisdiction": "RJ",
            "aliases": ["RERC"],
        },
        {
            "code": "SSERC",
            "name": "Sikkim State Electricity Regulatory Commission",
            "jurisdiction": "SK",
            "aliases": ["SSERC", "Sikkim ERC"],
        },
        {
            "code": "TNERC",
            "name": "Tamil Nadu Electricity Regulatory Commission",
            "jurisdiction": "TN",
            "aliases": ["TNERC"],
        },
        {
            "code": "TGERC",
            "name": "Telangana Electricity Regulatory Commission",
            "jurisdiction": "TG",
            "aliases": ["TGERC", "TSERC"],
        },
        {
            "code": "TERC",
            "name": "Tripura Electricity Regulatory Commission",
            "jurisdiction": "TR",
            "aliases": ["TERC"],
        },
        {
            "code": "UPERC",
            "name": "Uttar Pradesh Electricity Regulatory Commission",
            "jurisdiction": "UP",
            "aliases": ["UPERC"],
        },
        {
            "code": "UERC",
            "name": "Uttarakhand Electricity Regulatory Commission",
            "jurisdiction": "UK",
            "aliases": ["UERC"],
        },
        {
            "code": "WBERC",
            "name": "West Bengal Electricity Regulatory Commission",
            "jurisdiction": "WB",
            "aliases": ["WBERC"],
        },
        {
            "code": "JERC-GOA-UT",
            "name": "Joint Electricity Regulatory Commission for the State of Goa and Union Territories",
            "jurisdiction": "GOAUT",
            "aliases": ["JERC (Goa & UTs)"],
        },
    ],
    "utilities": [
        {
            "code": "APEPDCL",
            "name": "Eastern Power Distribution Company of Andhra Pradesh Limited",
            "commission": "APERC",
            "aliases": ["APEPDCL"],
        },
        {
            "code": "APSPDCL",
            "name": "Southern Power Distribution Company of Andhra Pradesh Limited",
            "commission": "APERC",
            "aliases": ["APSPDCL"],
        },
        {
            "code": "APCPDCL",
            "name": "Central Power Distribution Company of Andhra Pradesh Limited",
            "commission": "APERC",
            "aliases": ["APCPDCL"],
        },
        {
            "code": "DOP-AR",
            "name": "Department of Power, Government of Arunachal Pradesh",
            "commission": "APSERC",
            "aliases": ["DOP-AR"],
        },
        {
            "code": "APDCL",
            "name": "Assam Power Distribution Company Limited",
            "commission": "AERC",
            "aliases": ["APDCL"],
        },
        {
            "code": "NBPDCL",
            "name": "North Bihar Power Distribution Company Limited",
            "commission": "BERC",
            "aliases": ["NBPDCL"],
        },
        {
            "code": "SBPDCL",
            "name": "South Bihar Power Distribution Company Limited",
            "commission": "BERC",
            "aliases": ["SBPDCL"],
        },
        {
            "code": "CSPDCL",
            "name": "Chhattisgarh State Power Distribution Company Limited",
            "commission": "CSERC",
            "aliases": ["CSPDCL"],
        },
        {"code": "BRPL", "name": "BSES Rajdhani Power Limited", "commission": "DERC", "aliases": ["BRPL"]},
        {"code": "BYPL", "name": "BSES Yamuna Power Limited", "commission": "DERC", "aliases": ["BYPL"]},
        {"code": "TPDDL", "name": "Tata Power Delhi Distribution Limited", "commission": "DERC", "aliases": ["TPDDL"]},
        {
            "code": "NDMC",
            "name": "New Delhi Municipal Council (electricity)",
            "commission": "DERC",
            "aliases": ["NDMC"],
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
        {
            "code": "TPL-AHM",
            "name": "Torrent Power Limited (Ahmedabad, Gandhinagar, Surat, Dahej)",
            "commission": "GERC",
            "aliases": ["TPL-AHM"],
        },
        {
            "code": "UHBVN",
            "name": "Uttar Haryana Bijli Vitran Nigam Limited",
            "commission": "HERC",
            "aliases": ["UHBVN"],
        },
        {
            "code": "DHBVN",
            "name": "Dakshin Haryana Bijli Vitran Nigam Limited",
            "commission": "HERC",
            "aliases": ["DHBVN"],
        },
        {
            "code": "HPSEBL",
            "name": "Himachal Pradesh State Electricity Board Limited",
            "commission": "HPERC",
            "aliases": ["HPSEBL"],
        },
        {
            "code": "JPDCL",
            "name": "Jammu Power Distribution Corporation Limited",
            "commission": "JERC-JKL",
            "aliases": ["JPDCL"],
        },
        {
            "code": "KPDCL",
            "name": "Kashmir Power Distribution Corporation Limited",
            "commission": "JERC-JKL",
            "aliases": ["KPDCL"],
        },
        {
            "code": "LADAKH-PDD",
            "name": "Power Development Department, Ladakh",
            "commission": "JERC-JKL",
            "aliases": ["LADAKH-PDD"],
        },
        {"code": "JBVNL", "name": "Jharkhand Bijli Vitran Nigam Limited", "commission": "JSERC", "aliases": ["JBVNL"]},
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
            "aliases": ["CESC"],
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
            "code": "KSEBL",
            "name": "Kerala State Electricity Board Limited",
            "commission": "KSERC",
            "aliases": ["KSEBL"],
        },
        {
            "code": "MPPKVVCL",
            "name": "Madhya Pradesh Poorv Kshetra Vidyut Vitaran Company Limited (Jabalpur)",
            "commission": "MPERC",
            "aliases": ["MPPKVVCL"],
        },
        {
            "code": "MPMKVVCL",
            "name": "Madhya Pradesh Madhya Kshetra Vidyut Vitaran Company Limited (Bhopal)",
            "commission": "MPERC",
            "aliases": ["MPMKVVCL"],
        },
        {
            "code": "MPPaKVVCL",
            "name": "Madhya Pradesh Paschim Kshetra Vidyut Vitaran Company Limited (Indore)",
            "commission": "MPERC",
            "aliases": ["MPPaKVVCL"],
        },
        {
            "code": "MSEDCL",
            "name": "Maharashtra State Electricity Distribution Company Limited",
            "commission": "MERC",
            "aliases": ["MSEDCL"],
        },
        {"code": "AEML", "name": "Adani Electricity Mumbai Limited", "commission": "MERC", "aliases": ["AEML"]},
        {
            "code": "TPC-D",
            "name": "Tata Power Company Limited (Distribution, Mumbai)",
            "commission": "MERC",
            "aliases": ["TPC-D"],
        },
        {
            "code": "BEST",
            "name": "Brihanmumbai Electric Supply and Transport Undertaking",
            "commission": "MERC",
            "aliases": ["BEST"],
        },
        {
            "code": "MSPDCL",
            "name": "Manipur State Power Distribution Company Limited",
            "commission": "JERC-MM",
            "aliases": ["MSPDCL"],
        },
        {
            "code": "PED-MZ",
            "name": "Power & Electricity Department, Government of Mizoram",
            "commission": "JERC-MM",
            "aliases": ["PED-MZ"],
        },
        {
            "code": "MEPDCL",
            "name": "Meghalaya Power Distribution Corporation Limited",
            "commission": "MSERC",
            "aliases": ["MEPDCL"],
        },
        {
            "code": "DOP-NL",
            "name": "Department of Power, Government of Nagaland",
            "commission": "NERC",
            "aliases": ["DOP-NL"],
        },
        {
            "code": "TPCODL",
            "name": "TP Central Odisha Distribution Limited",
            "commission": "OERC",
            "aliases": ["TPCODL"],
        },
        {
            "code": "TPSODL",
            "name": "TP Southern Odisha Distribution Limited",
            "commission": "OERC",
            "aliases": ["TPSODL"],
        },
        {
            "code": "TPWODL",
            "name": "TP Western Odisha Distribution Limited",
            "commission": "OERC",
            "aliases": ["TPWODL"],
        },
        {
            "code": "TPNODL",
            "name": "TP Northern Odisha Distribution Limited",
            "commission": "OERC",
            "aliases": ["TPNODL"],
        },
        {
            "code": "PSPCL",
            "name": "Punjab State Power Corporation Limited",
            "commission": "PSERC",
            "aliases": ["PSPCL"],
        },
        {"code": "JVVNL", "name": "Jaipur Vidyut Vitran Nigam Limited", "commission": "RERC", "aliases": ["JVVNL"]},
        {"code": "AVVNL", "name": "Ajmer Vidyut Vitran Nigam Limited", "commission": "RERC", "aliases": ["AVVNL"]},
        {"code": "JDVVNL", "name": "Jodhpur Vidyut Vitran Nigam Limited", "commission": "RERC", "aliases": ["JDVVNL"]},
        {
            "code": "EPD-SK",
            "name": "Energy & Power Department, Government of Sikkim",
            "commission": "SSERC",
            "aliases": ["EPD-SK"],
        },
        {
            "code": "TNPDCL",
            "name": "Tamil Nadu Power Distribution Corporation Limited (formerly TANGEDCO)",
            "commission": "TNERC",
            "aliases": ["TNPDCL"],
        },
        {
            "code": "TGSPDCL",
            "name": "Southern Power Distribution Company of Telangana Limited",
            "commission": "TGERC",
            "aliases": ["TGSPDCL"],
        },
        {
            "code": "TGNPDCL",
            "name": "Northern Power Distribution Company of Telangana Limited",
            "commission": "TGERC",
            "aliases": ["TGNPDCL"],
        },
        {
            "code": "TSECL",
            "name": "Tripura State Electricity Corporation Limited",
            "commission": "TERC",
            "aliases": ["TSECL"],
        },
        {
            "code": "NPCL",
            "name": "Noida Power Company Limited",
            "commission": "UPERC",
            "aliases": ["NPCL"],
            "licensed_area": "Greater Noida",
            "profile": "uperc-npcl",
        },
        {
            "code": "PVVNL",
            "name": "Paschimanchal Vidyut Vitran Nigam Limited",
            "commission": "UPERC",
            "aliases": ["PVVNL"],
        },
        {
            "code": "PUVVNL",
            "name": "Purvanchal Vidyut Vitran Nigam Limited",
            "commission": "UPERC",
            "aliases": ["PUVVNL"],
        },
        {
            "code": "MVVNL",
            "name": "Madhyanchal Vidyut Vitran Nigam Limited",
            "commission": "UPERC",
            "aliases": ["MVVNL"],
        },
        {
            "code": "DVVNL",
            "name": "Dakshinanchal Vidyut Vitran Nigam Limited",
            "commission": "UPERC",
            "aliases": ["DVVNL"],
        },
        {
            "code": "KESCO",
            "name": "Kanpur Electricity Supply Company Limited",
            "commission": "UPERC",
            "aliases": ["KESCO"],
        },
        {"code": "UPCL", "name": "Uttarakhand Power Corporation Limited", "commission": "UERC", "aliases": ["UPCL"]},
        {
            "code": "WBSEDCL",
            "name": "West Bengal State Electricity Distribution Company Limited",
            "commission": "WBERC",
            "aliases": ["WBSEDCL"],
        },
        {"code": "CESC-KOL", "name": "CESC Limited (Kolkata)", "commission": "WBERC", "aliases": ["CESC-KOL"]},
        {
            "code": "GOA-ED",
            "name": "Electricity Department, Government of Goa",
            "commission": "JERC-GOA-UT",
            "aliases": ["GOA-ED"],
        },
        {
            "code": "CHD-ED",
            "name": "Electricity Department, Chandigarh",
            "commission": "JERC-GOA-UT",
            "aliases": ["CHD-ED"],
        },
        {
            "code": "DNHDD-PDCL",
            "name": "DNH DD Power Distribution Corporation Limited",
            "commission": "JERC-GOA-UT",
            "aliases": ["DNHDD-PDCL"],
        },
        {
            "code": "PED-PY",
            "name": "Electricity Department, Puducherry",
            "commission": "JERC-GOA-UT",
            "aliases": ["PED-PY"],
        },
        {
            "code": "AN-ED",
            "name": "Electricity Department, Andaman & Nicobar Islands",
            "commission": "JERC-GOA-UT",
            "aliases": ["AN-ED"],
        },
        {
            "code": "LK-ED",
            "name": "Electricity Department, Lakshadweep",
            "commission": "JERC-GOA-UT",
            "aliases": ["LK-ED"],
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
