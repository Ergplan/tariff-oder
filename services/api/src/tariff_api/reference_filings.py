"""Reference filings and the rules that reproduce them (milestone 13), read-only for the desk.

A reference filing is a licensee's filed petition kept as the target a reproduction is measured
against (`packages/reference-filings/`); its reproduction report is written by
`scripts/reproduce_formats.py`.  This module serves them, with the commission's calculation
rules and their status, so a reviewer can see what is reproduced, what is given, what differs
and why — and what the rules still lack (approval, verified clauses).  Nothing here decides.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from .arr.rules import load_rules
from .errors import AppError


def _root() -> Path:
    here = Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "packages" / "reference-filings").is_dir():
            return p / "packages" / "reference-filings"
    return Path("packages/reference-filings")


def filings() -> list[dict[str, Any]]:
    out = []
    for f in sorted(_root().glob("*.json")):
        d = json.loads(f.read_text())
        docs = d.get("documents", [])
        out.append(
            {
                "id": d["id"],
                "commission": d["commission"],
                "licensee": d["licensee"],
                "title": d["title"],
                "proceedings": d.get("proceedings", []),
                "documents": len(docs),
                "hashed": sum(1 for x in docs if x.get("sha256")),
                "reproduced": (_root() / d["id"] / "reproduction.json").exists(),
            }
        )
    return out


def filing(filing_id: str) -> dict[str, Any]:
    path = _root() / f"{filing_id}.json"
    if not path.exists() or "/" in filing_id:
        raise AppError("not_found", f"reference filing {filing_id} not found")
    d = json.loads(path.read_text())
    folder = _root() / filing_id
    roles = Counter(x["role"] for x in d.get("documents", []))
    out: dict[str, Any] = {
        "id": d["id"],
        "commission": d["commission"],
        "licensee": d["licensee"],
        "title": d["title"],
        "status": d.get("status"),
        "proceedings": d.get("proceedings", []),
        "resulting_order": d.get("resulting_order"),
        "documents": {
            "total": len(d.get("documents", [])),
            "hashed": sum(1 for x in d.get("documents", []) if x.get("sha256")),
            "by_role": dict(roles),
            "missing": [x["name"] for x in d.get("documents", []) if x.get("note") and "absent" in x["note"]],
        },
        "formats": [],
        "records": [],
        "chain": None,
        "coverage": None,
        "pipeline": [],
        "findings": [],
    }
    rep_path = folder / "reproduction.json"
    if rep_path.exists():
        rep = json.loads(rep_path.read_text())
        for f in rep.get("formats", []):
            entry = {"binding": f["binding"], "sheet": f["sheet"], "columns": f["columns"], "counts": f["counts"]}
            if f["binding"] == "chain-arr.json":
                cols: dict[str, Counter] = {}
                for c in f["checks"]:
                    key = f"{c['fiscal_year']} · {c['words'].strip().replace(chr(10), ' ')}"
                    cols.setdefault(key, Counter())[c["result"]] += 1
                entry["by_column"] = {k: dict(v) for k, v in cols.items()}
                entry["computed"] = [
                    {k: c[k] for k in ("fiscal_year", "words", "output", "label", "filed", "computed", "result")}
                    for c in f["checks"]
                    if c["fiscal_year"] == "FY2026-27"
                ]
                out["chain"] = entry
            else:
                entry["not_matching"] = [
                    {
                        k: c.get(k)
                        for k in ("fiscal_year", "voice", "words", "output", "filed", "computed", "result", "why")
                    }
                    for c in f["checks"]
                    if c["result"] in ("differs", "blocked")
                ][:40]
                out["formats"].append(entry)
        for r in rep.get("records", []):
            if "counts" in r:
                out["records"].append({"binding": r["binding"], "sheet": r.get("sheet"), "counts": r["counts"]})
            elif "tie" in r:
                out["records"].append(
                    {
                        "tie": r["tie"],
                        "fiscal_year": r["fiscal_year"],
                        "working": r["working"],
                        "filed": r["filed"],
                        "result": r["result"],
                    }
                )
            elif "checks" in r:
                out["records"].append(
                    {"binding": r["binding"], "counts": dict(Counter(c["result"] for c in r["checks"]))}
                )
        # the petition's columns computed end to end: the chain fed by the schedules' results
        out["pipeline"] = [
            {k: col[k] for k in ("fiscal_year", "voice", "counts", "fed", "not_fed", "records")}
            | {"checks": [{k: c[k] for k in ("output", "label", "filed", "computed", "result")} for c in col["checks"]]}
            for p in rep.get("pipeline", [])
            for col in p["columns"]
        ]
        if rep.get("coverage"):
            # how each figure of the ARR format is established, by column (computed / tied /
            # given / differs / record) — what the reproduction covers and what it takes on trust
            out["coverage"] = rep["coverage"]
    fpath = folder / "findings.json"
    if fpath.exists():
        out["findings"] = json.loads(fpath.read_text())["findings"]
    return out


def rules(commission: str) -> dict[str, Any]:
    rs = load_rules(commission)
    if not rs:
        raise AppError("not_found", f"no calculation rules for {commission}")
    return {
        "commission": commission.upper(),
        "rules": [
            {
                "id": r.id,
                "version": r.version,
                "status": r.status,
                "title": r.title,
                "output": r.output,
                "unit": r.unit,
                "line_code": r.line_code,
                "schedule": r.schedule,
                "per": r.per,
                "formula": r.formula,
                "inputs": {k: {"source": v.source, "unit": v.unit, "value": v.value} for k, v in r.inputs.items()},
                "regulation": r.clause.regulation,
                "clause": r.clause.clause,
                "page": r.clause.page,
                "verified": r.clause.verified,
                "from_fy": r.applies.from_fy,
                "to_fy": r.applies.to_fy,
                "examples": len(r.examples),
                "note": r.note,
            }
            for r in rs
        ],
        "summary": {
            "rules": len(rs),
            "approved": sum(1 for r in rs if r.status == "approved"),
            "clauses_verified": sum(1 for r in rs if r.clause.verified),
        },
    }
