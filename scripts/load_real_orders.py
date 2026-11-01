#!/usr/bin/env python3
"""Load the real tariff orders read in the build session into a running local stack.

For each order: download it from the commission's own website, check its SHA-256 against
the hash recorded in docs/BUILD_STATE.md (a different file is skipped, never loaded), register
it as a real source with its licensees, wait for it to be parsed, and start its ARR reading,
which proposes chapters with a reading preview.  Every later decision — confirming chapters,
approving values, confirming a mapping — is a reviewer's, in the app.

Run on the machine where the stack runs (the API on port 8000):

    docker compose -f infra/local/docker-compose.yml exec api tariff-api seed   # licensee aliases
    uv run python scripts/load_real_orders.py               # all ten orders
    uv run python scripts/load_real_orders.py --only OERC   # one commission

An order whose website does not answer is reported and skipped; run the script again later
(it is idempotent: an order already registered is found by its hash and not uploaded twice).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

import httpx

ORDERS = [
    {
        "key": "UPERC-NPCL-FY2026-27",
        "commission": "UPERC",
        "url": "https://www.uperc.org/App_File/NPCL_TariffOrder-pdf72202631759PM.pdf",
        "sha256": "ff36813e2671e0498b78784afec73f548626d9779af8d1c1bb79585a4e174b1a",
        "name": "NPCL_TariffOrder_FY2026-27_UPERC.pdf",
        "licensees": ["NPCL"],
    },
    {
        "key": "BERC-DISCOMs-FY2026-27",
        "commission": "BERC",
        "url": "https://berc.co.in/images/pdf/tariff-order/2026-27/DISCOMs_FO_TARIFF_CN_50_51_DT_180326.pdf",
        "sha256": "a247053b586fd8909e14b00280d24e0d39357b94bdb36e7b670f21e5aa794537",
        "name": "BERC_DISCOMs_TariffOrder_FY2026-27.pdf",
        "licensees": ["NBPDCL", "SBPDCL"],
    },
    {
        "key": "HPERC-HPSEBL-FY2026-27",
        "commission": "HPERC",
        "url": "https://hperc.org/wp-content/uploads/2026/03/fto2627.pdf",
        "sha256": "0f3d9e9df0eced38ed2e85df25be55da47f55b071a8f568f6d49d0268e50ec74",
        "name": "HPERC_HPSEBL_TariffOrder_FY2026-27.pdf",
        "licensees": ["HPSEBL"],
    },
    {
        "key": "JSERC-JBVNL-2026",
        "commission": "JSERC",
        "url": "https://jserc.org/pdf/tariff_order/JBVNL-2026.pdf",
        "sha256": "0391dd2701c7bbb7a962923212ef5a8ed6c9cdfbfea601df692d7ce4aa119108",
        "name": "JSERC_JBVNL_MYT_TrueUp_APR_Order_2026.pdf",
        "licensees": ["JBVNL"],
    },
    {
        "key": "OERC-DISCOMs-FY2026-27",
        "commission": "OERC",
        "url": "https://www.orierc.org/CuteSoft_Client/writereaddata/upload/DISCOM_TARIFF_ORDER_FY_2026-27.pdf",
        "sha256": "d58d281787d4dd34e7b895add2e7cb37dbf3b9e8d5f1a1ea208dc57ceffde0ab",
        "name": "OERC_DISCOM_TARIFF_ORDER_FY_2026-27.pdf",
        "licensees": ["TPCODL", "TPWODL", "TPSODL", "TPNODL"],
    },
    {
        "key": "OERC-DISCOMs-FY2025-26",
        "commission": "OERC",
        "url": "https://www.orierc.org/CuteSoft_Client/writereaddata/upload/DISCOM_TARIFF_ORDER_FY_2025-26.pdf",
        "sha256": "de53fe6fc5afb70f9f45e2eb94a977bcbd2c791fe63eb9f713f8b9ab2fc069fb",
        "name": "OERC_DISCOM_TARIFF_ORDER_FY_2025-26.pdf",
        "licensees": ["TPCODL", "TPWODL", "TPSODL", "TPNODL"],
    },
    {
        "key": "MPERC-DISCOMs-FY2026-27",
        "commission": "MPERC",
        "url": "https://mperc.in/uploads/petition_order_document/MPERC_Pno_140_2025_State_DISCOMs_ARR_RST__ORDER_FY_2026_27_FINAL_ORDER.pdf",
        "sha256": "77ffe9d2e48277354348b32ab3a90d74639a4b406757ae8e658197bd79f91afb",
        "name": "MPERC_State_DISCOMs_ARR_RST_Order_FY2026-27.pdf",
        "licensees": ["MPPKVVCL", "MPMKVVCL", "MPPaKVVCL"],
    },
    {
        "key": "MPERC-DISCOMs-FY2025-26",
        "commission": "MPERC",
        "url": "https://mperc.in/uploads/petition_order_document/Final_State_DISCOMs_ARR_and_Retail_Supply_Tariff_Order_FY_2025-26_29_03_2025_3.pdf",
        "sha256": "66254f461e5d360d42d6216aaf824e0baa8bdab943248aeb241c34940b2693c2",
        "name": "MPERC_State_DISCOMs_ARR_RST_Order_FY2025-26.pdf",
        "licensees": ["MPPKVVCL", "MPMKVVCL", "MPPaKVVCL"],
    },
    {
        "key": "UERC-UPCL-FY2026-27",
        "commission": "UERC",
        "url": "https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2026/03/202603311394829151.pdf",
        "sha256": "1a9299178035d9e9460733256419710b2c3d5d7cc98b3703be60130aea99eb91",
        "name": "UERC_UPCL_TariffOrder_FY2026-27.pdf",
        "licensees": ["UPCL"],
    },
    {
        "key": "UERC-UPCL-FY2025-26",
        "commission": "UERC",
        "url": "https://cdnbbsr.s3waas.gov.in/s3cf05968255451bdefe3c5bc64d550517/uploads/2025/04/20250428261984844.pdf",
        "sha256": "5fc2d18f3b19793e67ecba4fe5bfc60b3e6b9401e20c418dc89255eb273bc41e",
        "name": "UERC_UPCL_MYT_TariffOrder_FY2025-26.pdf",
        "licensees": ["UPCL"],
    },
]

PARSED = {"localised", "structured", "extracted", "awaiting_review", "published"}
STUCK = {"failed", "quarantined", "rejected"}


def download(order: dict, cache: Path) -> bytes | None:
    path = cache / order["name"]
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == order["sha256"]:
        return path.read_bytes()
    for attempt in range(4):
        try:
            with httpx.Client(
                follow_redirects=True, timeout=300, headers={"User-Agent": "tariff-order-studio/0.1"}
            ) as c:
                r = c.get(order["url"])
            if r.status_code != 200:
                print(f"  {order['key']}: the website answered {r.status_code}")
                return None
            data = r.content
            digest = hashlib.sha256(data).hexdigest()
            if digest != order["sha256"]:
                print(f"  {order['key']}: the file differs from the one read (sha256 {digest[:12]}…); skipped")
                return None
            path.write_bytes(data)
            return data
        except httpx.HTTPError as e:
            print(f"  {order['key']}: {type(e).__name__} (attempt {attempt + 1} of 4)")
            time.sleep(5 * (attempt + 1))
    return None


def find_by_hash(api: httpx.Client, sha: str) -> dict | None:
    r = api.get("/sources", params={"limit": 500})
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    return next((s for s in items if s.get("sha256") == sha), None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin@example.com", help="an administrator of the local identity allow-list")
    ap.add_argument("--only", help="a commission code (UPERC, BERC, HPERC, JSERC, OERC, MPERC, UERC)")
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "tariff-real-orders"))
    ap.add_argument("--no-read", action="store_true", help="register and parse only; do not start the ARR readings")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    api = httpx.Client(base_url=args.api, timeout=600, headers={"X-Local-User": args.user}, trust_env=False)
    todo = [o for o in ORDERS if not args.only or o["commission"] == args.only.upper()]

    registered: list[tuple[dict, str]] = []
    for o in todo:
        print(f"{o['key']}: downloading {o['url']}")
        data = download(o, cache)
        if data is None:
            continue
        r = api.post(
            "/sources",
            files={"file": (o["name"], data, "application/pdf")},
            data={"dataset_kind": "real", "utility_code": o["licensees"][0], "provenance_url": o["url"]},
        )
        if r.status_code in (200, 201):
            sid = r.json()["source"]["id"]
            print(f"  registered as {sid}")
        elif r.status_code == 409 and (existing := find_by_hash(api, o["sha256"])):
            sid = existing["id"]
            print(f"  already registered as {sid}")
        else:
            print(f"  registration refused ({r.status_code}): {r.text[:200]}")
            continue
        if len(o["licensees"]) > 1:
            r = api.put(f"/sources/{sid}/licensees", json={"codes": o["licensees"]})
            if r.status_code != 200:
                print(f"  licensees not set ({r.status_code}): {r.text[:200]} — run `tariff-api seed` and retry")
        registered.append((o, sid))

    if args.no_read:
        return 0
    print("\nWaiting for each order to be parsed (several minutes per order), then starting its ARR reading.")
    for o, sid in registered:
        for _ in range(240):
            s = api.get(f"/sources/{sid}").json()
            if s.get("state") in PARSED or s.get("state") in STUCK:
                break
            time.sleep(15)
        state = s.get("state")
        if state not in PARSED:
            print(f"  {o['key']}: not parsed ({state}); see /sources/{sid}")
            continue
        arr = api.get(f"/sources/{sid}/arr").json()
        if arr.get("arr_state"):
            print(f"  {o['key']}: ARR reading already {arr['arr_state']}")
            continue
        r = api.post(f"/sources/{sid}/arr/read")
        outcome = "started" if r.status_code == 202 else f"refused ({r.status_code}) {r.text[:160]}"
        print(f"  {o['key']}: ARR reading {outcome}")
    print("\nOpen /arr/readings in the app: each order's chapters are proposed there with a reading preview.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
