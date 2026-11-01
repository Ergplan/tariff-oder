#!/usr/bin/env python3
"""Download a reference filing (a licensee's filed ARR petition) and record each document's hash.

Reads `packages/reference-filings/<id>.json`, downloads every document into a cache directory,
computes its SHA-256 and size from the bytes, and writes them back into the JSON (a document
whose recorded hash differs from the bytes is reported and left unchanged — a changed file is
never silently accepted).  With `--register`, each PDF is also registered with a running API as
a real source of the licensee (spreadsheets and Word files stay in the cache: the source
pipeline reads PDFs).

Run on a machine with open egress (the VM): the documents are served from a non-443 port.
Or, when the package was downloaded already (the licensee's zip, unpacked), point at the
folder: each listed document is found by its file name anywhere under it, and files in the
folder that the listing does not name are reported (they may be documents the page omits).

    uv run python scripts/fetch_reference_filing.py uperc-npcl-fy2026-27
    uv run python scripts/fetch_reference_filing.py uperc-npcl-fy2026-27 --from-dir ~/npcl-fy2026-27
    uv run python scripts/fetch_reference_filing.py uperc-npcl-fy2026-27 --from-dir ~/npcl-fy2026-27 --register

Then commit the updated JSON so the hashes are on record.  Downloading is idempotent: a cached
file whose hash matches is not fetched again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages" / "reference-filings"


def fetch(url: str, dest: Path) -> bytes | None:
    for attempt in range(4):
        try:
            headers = {"User-Agent": "tariff-order-studio/0.1"}
            with httpx.Client(follow_redirects=True, timeout=600, headers=headers) as c:
                r = c.get(url)
            if r.status_code == 200 and r.content:
                dest.write_bytes(r.content)
                return r.content
            print(f"    answered {r.status_code}")
            return None
        except httpx.HTTPError as e:
            print(f"    {type(e).__name__} (attempt {attempt + 1} of 4)")
            time.sleep(5 * (attempt + 1))
    return None


def _norm(name: str) -> str:
    """A file name compared loosely: case, whitespace runs and mis-decoded apostrophes ignored."""
    return " ".join(name.replace("â€™", "'").replace("\u2019", "'").lower().split())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package", help="the reference filing id, e.g. uperc-npcl-fy2026-27")
    ap.add_argument("--cache", default=str(Path.home() / ".cache" / "tariff-reference-filings"))
    ap.add_argument("--from-dir", help="use already-downloaded files under this folder instead of downloading")
    ap.add_argument("--register", action="store_true", help="also register each PDF with the API as a real source")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--user", default="admin@example.com")
    args = ap.parse_args()

    path = PACKAGES / f"{args.package}.json"
    pkg = json.loads(path.read_text())
    cache = Path(args.cache) / pkg["id"]
    cache.mkdir(parents=True, exist_ok=True)
    api = httpx.Client(base_url=args.api, timeout=600, headers={"X-Local-User": args.user}, trust_env=False)

    local: dict[str, Path] = {}
    if args.from_dir:
        base = Path(args.from_dir).expanduser()
        local = {_norm(f.name): f for f in base.rglob("*") if f.is_file()}
        print(f"{len(local)} files under {base}")
    used: set[str] = set()

    ok = failed = changed = 0
    for d in pkg["documents"]:
        if args.from_dir:
            f = local.get(_norm(d["name"]))
            if f is None:
                print(f"  not in the folder: {d['name']}")
                failed += 1
                continue
            used.add(_norm(d["name"]))
            data = f.read_bytes()
        else:
            dest = cache / d["name"]
            data = dest.read_bytes() if dest.exists() else None
            if data is None or (d["sha256"] and hashlib.sha256(data).hexdigest() != d["sha256"]):
                print(f"  {d['name']}")
                data = fetch(d["url"], dest)
        if data is None:
            failed += 1
            continue
        digest = hashlib.sha256(data).hexdigest()
        if d["sha256"] and d["sha256"] != digest:
            print(f"    differs from the recorded hash ({digest[:12]}… vs {d['sha256'][:12]}…): left unchanged")
            changed += 1
            continue
        d["sha256"], d["bytes"] = digest, len(data)
        ok += 1
        if args.register and d["name"].lower().endswith(".pdf"):
            r = api.post(
                "/sources",
                files={"file": (d["name"], data, "application/pdf")},
                data={"dataset_kind": "real", "utility_code": pkg["licensee"], "provenance_url": d["url"]},
            )
            if r.status_code not in (200, 201, 409):
                print(f"    registration refused ({r.status_code}): {r.text[:160]}")

    extra = sorted(f.name for k, f in local.items() if k not in used)
    if extra:
        print(f"\n{len(extra)} files in the folder the listing does not name (open them; add the real ones):")
        for name in extra:
            print(f"  + {name}")

    pkg["status"] = (
        f"downloaded {time.strftime('%Y-%m-%d')}: {ok} documents hashed, {failed} not fetched, "
        f"{changed} differing from a recorded hash"
    )
    path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n")
    print(f"\n{ok} hashed, {failed} not fetched, {changed} changed.  Commit {path.relative_to(ROOT)}.")
    return 0 if not failed and not changed else 1


if __name__ == "__main__":
    sys.exit(main())
