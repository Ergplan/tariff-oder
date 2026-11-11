"""The reference seed: states, commissions, utilities (DISCOMs and TRANSCOs), heads and the key
parameters.  ``python -m arrnet.reference [--dry-run DIR]`` posts them.

DISCOMs and commission names are read from ``tools/arrdb/registry.json`` and heads from
``arrdb.heads`` so that there is one source for each; ``reference.json`` holds the rest.
"""

from __future__ import annotations

import argparse
import json
from functools import lru_cache
from typing import Any

from . import config
from .arrdb_bridge import HEAD_NAMES, HEADS

KIND_ORDER = ("states", "commissions", "utilities", "heads", "parameter_defs")


@lru_cache(maxsize=1)
def registry() -> dict[str, Any]:
    return json.loads((config.ARRDB / "registry.json").read_text())


@lru_cache(maxsize=1)
def reference() -> dict[str, Any]:
    return json.loads((config.HERE / "reference.json").read_text())


def rows() -> dict[str, list[dict[str, Any]]]:
    reg, ref = registry(), reference()
    cs = ref["commission_states"]
    commissions = []
    for c in reg["commissions"]:
        if c["code"] not in cs:
            raise ValueError(f"commission {c['code']} has no state codes in reference.json")
        commissions.append(
            {
                "code": c["code"],
                "name": c["name"],
                "website": c.get("website"),
                # what the registry's build session observed, not a statement about the site
                "website_reachable": c.get("website_reachable"),
                "checked_on": "2026-11-11" if c.get("website_reachable") is not None else None,
                "states": cs[c["code"]],
            }
        )
    utilities = []
    for d in reg["discoms"]:
        states = cs[d["commission"]]
        state = ref["utility_states"].get(d["code"]) or (states[0] if len(states) == 1 else None)
        if state is None:
            raise ValueError(f"utility {d['code']}: its commission serves several states; set utility_states")
        own = ref["ownership_overrides"].get(d["code"], {}).get("ownership", d["ownership"])
        utilities.append(
            {
                "code": d["code"],
                "name": d["name"],
                "kind": "discom",
                "commission": d["commission"],
                "state": state,
                "ownership": own,
                "aliases": d.get("aliases", []),
            }
        )
    seen = {u["code"] for u in utilities}
    for t in ref["transcos"]:
        if t["code"] in seen:
            raise ValueError(f"duplicate utility code {t['code']}")
        utilities.append(dict(t))
    sort = {c: (i + 1) * 10 for i, (c, _, _) in enumerate(HEADS)}
    heads = [{"code": c, "name": n, "sort": sort.get(c, 1000)} for c, n in HEAD_NAMES.items()]
    return {
        "states": ref["states"],
        "commissions": commissions,
        "utilities": utilities,
        "heads": heads,
        "parameter_defs": ref["parameter_defs"],
    }


def known_codes() -> dict[str, set[str]]:
    r = rows()
    return {
        "heads": {h["code"] for h in r["heads"]},
        "parameter_defs": {p["code"] for p in r["parameter_defs"]},
        "utilities": {u["code"] for u in r["utilities"]},
    }


def aliases() -> dict[str, list[str]]:
    return {d["code"]: d.get("aliases", []) for d in registry()["discoms"]}


def seed(sink) -> dict[str, Any]:
    out: dict[str, Any] = {}
    r = rows()
    for kind in KIND_ORDER:
        res = sink.post(kind, r[kind])
        out[kind] = {"written": res.written, "rejected": [x["reason"] for x in res.rejected]}
    return out


def main() -> int:
    from .ingest import make_sink

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", metavar="DIR")
    a = ap.parse_args()
    print(json.dumps(seed(make_sink(a.dry_run, known_codes())), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
