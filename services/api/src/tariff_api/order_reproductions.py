"""Commission orders reproduced from their own figures, read-only for the desk.

Beside the reference filing (a licensee's petition reproduced from its formats), the build
reproduces commission orders of other states from the figures the orders print: each order's
folder in `packages/order-reproductions/` holds a manifest (the order's URL and SHA-256), records
read from its text layer with page and quote, bindings that evaluate the commission's draft rules
on those records against the order's printed results, and findings.  This module evaluates the
bindings on request and serves what matched, what differed and why — so that a reviewer sees the
engine on a commission other than UPERC.  Nothing here verifies, approves or decides.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

from .arr.reproduce import load_binding_rates, reproduce_cells
from .arr.rules import load_rules
from .errors import AppError


def _root() -> Path:
    here = Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "packages" / "order-reproductions").is_dir():
            return p / "packages" / "order-reproductions"
    return Path("packages/order-reproductions")


def _folder(reproduction_id: str) -> Path:
    folder = _root() / reproduction_id
    if "/" in reproduction_id or ".." in reproduction_id or not (folder / "manifest.json").exists():
        raise AppError("not_found", f"order reproduction {reproduction_id} not found")
    return folder


def _bindings(folder: Path, commission: str) -> list[dict[str, Any]]:
    rules = load_rules(commission)
    out = []
    for path in sorted((folder / "bindings").glob("*.json")):
        binding = json.loads(path.read_text())
        checks = reproduce_cells(None, binding, rules, rates=load_binding_rates(folder, binding))
        out.append(
            {
                "binding": path.name,
                "note": binding.get("note"),
                "years": sorted({e["fiscal_year"] for e in binding["evaluations"]}),
                "counts": dict(Counter(c.result for c in checks)),
                "checks": [_check(c) for c in checks],
            }
        )
    return out


def _findings(folder: Path) -> list[dict[str, Any]]:
    path = folder / "findings.json"
    return json.loads(path.read_text())["findings"] if path.exists() else []


def _check(c: Any) -> dict[str, Any]:
    """A check with its gap: how far the unrounded computation is from the printed figure — the
    measure a reviewer weighs against the printed precision of the inputs."""
    d = asdict(c)
    if c.exact is not None and c.filed is not None:
        d["gap"] = str((Decimal(c.exact) - Decimal(c.filed)).quantize(Decimal("0.0001")))
    return d


def _records(folder: Path) -> list[dict[str, Any]]:
    out = []
    for path in sorted((folder / "order").glob("*.json")):
        d = json.loads(path.read_text())
        pages = sorted({f["page"] for f in d.get("figures", {}).values()})
        out.append(
            {
                "record": path.name,
                "title": d["document"]["title"],
                "sha256": d["document"]["sha256"],
                "figures": len(d.get("figures", {})),
                "pages": [pages[0], pages[-1]] if pages else [],
                "status": d.get("status"),
            }
        )
    return out


def reproductions() -> list[dict[str, Any]]:
    out = []
    for manifest in sorted(_root().glob("*/manifest.json")):
        m = json.loads(manifest.read_text())
        folder = manifest.parent
        counts: Counter[str] = Counter()
        for b in _bindings(folder, m["commission"]):
            counts.update(b["counts"])
        findings = _findings(folder)
        out.append(
            {
                "id": m["id"],
                "commission": m["commission"],
                "licensees": m.get("licensees") or [m.get("licensee")],
                "fiscal_year": m["fiscal_year"],
                "title": m["order"]["title"],
                "checks": dict(counts),
                "findings": len(findings),
            }
        )
    return out


def reproduction(reproduction_id: str) -> dict[str, Any]:
    folder = _folder(reproduction_id)
    m = json.loads((folder / "manifest.json").read_text())
    rules = load_rules(m["commission"])
    bindings = _bindings(folder, m["commission"])
    counts: Counter[str] = Counter()
    for b in bindings:
        counts.update(b["counts"])
    findings = _findings(folder)
    return {
        **m,
        "rules": {
            "file": m.get("rules"),
            "count": len(rules),
            "approved": sum(1 for r in rules if r.status == "approved"),
            "clauses_verified": sum(1 for r in rules if r.clause.verified),
        },
        "records": _records(folder),
        "bindings": bindings,
        "counts": dict(counts),
        "findings": findings,
    }
